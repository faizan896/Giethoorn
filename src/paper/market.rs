//! Offline, source-traceable marks from a finalized schema-2 recording.
//! File I/O stays here; PaperEngine still has only deterministic transitions.
use super::*;
use crate::engine::{Quote, Report};
use crate::event::{Event, FEED_SCHEMA_VERSION, FeedKind, FeedPolicy, Network, Record};
use crate::feeds::{FeedStates, FeedStatus, Observation};
use crate::journal::replay_path_observed;
use crate::segments::{INDEX_NAME, RecordingInput, StorageSummary};
use anyhow::{Context, Result, ensure};
use sha2::{Digest, Sha256};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::Path;

const MAX_SOURCE_BYTES: u64 = 16 * 1024 * 1024;
const MAX_SOURCE_FILES: usize = 1024;
const MAX_DERIVED_BYTES: usize = 32 * 1024 * 1024;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct SourceFile {
    pub file: String,
    pub bytes: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct SourceManifest {
    pub manifest_version: u16,
    /// Operator-declared origin. A checksum does not authenticate the exchange.
    pub origin: RecordingOrigin,
    pub files: Vec<SourceFile>,
    pub recording_sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MarketLink {
    pub paper_sequence: u64,
    pub market_sequence: u64,
    pub connection_id: u64,
    pub local_time_ns: u64,
    pub monotonic_ns: u64,
    pub generated_end: bool,
    pub quote: Option<Quote>,
    pub feeds: Option<FeedStates>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct MarketReplayReport {
    pub adapter_version: u16,
    pub mode: &'static str,
    pub source: SourceManifest,
    pub source_report: Report,
    pub source_storage: StorageSummary,
    /// Only this child recording is complete; never attests the 24-hour gate.
    pub full_window_verified: bool,
    pub strategy_enabled: bool,
    pub market_marks: u64,
    pub paper: PaperReport,
}

fn digest_file(path: &Path) -> Result<String> {
    let mut digest = Sha256::new();
    let mut input = File::open(path)?;
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let size = input.read(&mut buffer)?;
        if size == 0 {
            break;
        }
        digest.update(&buffer[..size]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn source_manifest(path: &Path, origin: RecordingOrigin) -> Result<SourceManifest> {
    let mut files = Vec::new();
    let mut total = 0_u64;
    for entry in fs::read_dir(path)? {
        let entry = entry?;
        ensure!(
            entry.file_type()?.is_file(),
            "recording entries must be regular files"
        );
        let file = entry
            .file_name()
            .into_string()
            .map_err(|_| anyhow::anyhow!("non-UTF8 source filename"))?;
        let bytes = entry.metadata()?.len();
        total = total.checked_add(bytes).context("source size overflow")?;
        ensure!(
            total <= MAX_SOURCE_BYTES,
            "recorded-paper input exceeds 16 MiB limit"
        );
        ensure!(
            files.len() < MAX_SOURCE_FILES,
            "recorded-paper source has too many files"
        );
        files.push(SourceFile {
            file,
            bytes,
            sha256: digest_file(&entry.path())?,
        });
    }
    files.sort_by(|a, b| a.file.cmp(&b.file));
    let mut digest = Sha256::new();
    digest.update(b"giethoorn-recorded-market-v1\0");
    digest.update(serde_json::to_vec(&files)?);
    Ok(SourceManifest {
        manifest_version: 1,
        origin,
        files,
        recording_sha256: format!("{:x}", digest.finalize()),
    })
}

pub(super) fn new_file(path: &Path) -> Result<File> {
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    options
        .open(path)
        .with_context(|| format!("create new artifact {}", path.display()))
}

pub(super) fn new_directory(path: &Path) -> Result<()> {
    let mut builder = fs::DirBuilder::new();
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt;
        builder.mode(0o700);
    }
    builder
        .create(path)
        .with_context(|| format!("create new output directory {}", path.display()))
}

pub(super) fn write_line(
    file: &mut File,
    value: &impl Serialize,
    budget: &mut usize,
) -> Result<()> {
    let mut bytes = serde_json::to_vec(value)?;
    bytes.push(b'\n');
    *budget = budget
        .checked_add(bytes.len())
        .context("output size overflow")?;
    ensure!(
        *budget <= MAX_DERIVED_BYTES,
        "recorded-paper derived output exceeds 32 MiB limit"
    );
    file.write_all(&bytes)?;
    Ok(())
}

struct Mapper {
    feed: FeedKind,
    engine: PaperEngine,
    health: Option<FeedStates>,
    health_time_ns: u64,
    marks: u64,
}

impl Mapper {
    fn event(&mut self, record: &Record, observed: Option<&Observation>) -> Result<PaperEvent> {
        if let Some(Observation::Feed(observation)) = observed {
            self.health = Some(observation.feeds.clone());
            self.health_time_ns = record.monotonic_ns;
            let selected = match self.feed {
                FeedKind::Bbo => observation.feeds.bbo.as_ref(),
                FeedKind::Depth => observation.feeds.depth.as_ref(),
            }
            .context("selected feed missing from normalized states")?;
            if selected.status == FeedStatus::Stale {
                return Ok(PaperEvent::Timer {});
            }
            if selected.status != FeedStatus::Fresh {
                return Ok(PaperEvent::MarketDisconnected {
                    reason: "selected feed is not usable".into(),
                });
            }
            if observed.and_then(Observation::source) == Some(self.feed)
                && let Some(quote) = observation.quote.as_ref()
                && let (Some(bid), Some(ask)) = (&quote.bid, &quote.ask)
            {
                let bid: Amount = bid.parse()?;
                let ask: Amount = ask.parse()?;
                if bid < ask {
                    self.marks += 1;
                    return Ok(PaperEvent::MarketObserved { bid, ask });
                }
                return Ok(PaperEvent::MarketDisconnected {
                    reason: "locked book is not a usable paper mark".into(),
                });
            }
        }
        Ok(match record.event {
            Event::ConnectionAttempt { .. }
            | Event::ConnectionOpened
            | Event::ConnectionError { .. }
            | Event::ConnectionClosed { .. }
            | Event::SessionEnded { .. } => PaperEvent::MarketDisconnected {
                reason: "recorded connection unavailable or awaiting data".into(),
            },
            _ => PaperEvent::Timer {},
        })
    }

    fn link(
        &self,
        record: &Record,
        observed: Option<&Observation>,
        generated_end: bool,
    ) -> MarketLink {
        let mut feeds = self.health.clone();
        if let Some(states) = feeds.as_mut() {
            let delay = record.monotonic_ns - self.health_time_ns;
            for state in [states.depth.as_mut(), states.bbo.as_mut()]
                .into_iter()
                .flatten()
            {
                state.age_ns = state.age_ns.map(|age| age.saturating_add(delay));
            }
        }
        MarketLink {
            paper_sequence: record.sequence + u64::from(generated_end),
            market_sequence: record.sequence,
            connection_id: record.connection_id,
            local_time_ns: record.local_time_ns,
            monotonic_ns: record.monotonic_ns,
            generated_end,
            quote: observed
                .filter(|o| o.source() == Some(self.feed))
                .and_then(Observation::quote)
                .cloned(),
            feeds,
        }
    }
}

/// Validate first, copy a bounded finalized source under its shared writer lock,
/// then persist each derived input before applying the paper transition.
/// A failure retains diagnostics/partial files, without a success report or HTML.
pub fn export_recorded_market(
    input: &Path,
    output: &Path,
    origin: RecordingOrigin,
    feed: FeedKind,
) -> Result<MarketReplayReport> {
    let input = input.canonicalize().context("resolve market recording")?;
    ensure!(
        input.is_dir(),
        "recorded-paper replay requires a finalized segmented directory"
    );
    let parent = output
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."))
        .canonicalize()
        .context("output parent must already exist")?;
    let output = parent.join(
        output
            .file_name()
            .context("output needs a new directory name")?,
    );
    ensure!(
        !output.starts_with(&input),
        "output must be outside the original recording"
    );
    ensure!(!output.exists(), "output already exists");
    let index_lock = File::open(input.join(INDEX_NAME))?;
    fs2::FileExt::try_lock_shared(&index_lock)
        .context("source recording is active; stop its writer before export")?;
    let manifest = source_manifest(&input, origin)?;
    let _original_guard = RecordingInput::open(&input, false)?;
    let mut header: Option<(String, Network, FeedPolicy)> = None;
    let (source_report, source_storage) = replay_path_observed(&input, false, |record, _| {
        ensure!(
            record.schema_version == FEED_SCHEMA_VERSION,
            "recorded-paper adapter requires schema-2 market data"
        );
        if let Event::FeedSessionStarted {
            coin,
            network,
            policy,
            ..
        } = &record.event
        {
            ensure!(
                policy.profile.includes(feed),
                "selected feed is disabled in source recording"
            );
            header = Some((coin.clone(), *network, policy.clone()));
        }
        Ok(())
    })?;
    ensure!(
        source_storage.finalized && source_report.complete,
        "recorded-paper source must be finalized and complete"
    );
    ensure!(
        source_report.records < MAX_PAPER_RECORDS,
        "recording exceeds paper's 10,000-record limit including replay end"
    );
    let (coin, network, policy) = header.context("missing schema-2 market session header")?;
    let config = PaperConfig {
        source: PaperSource::RecordedMarket {
            label: format!(
                "{} {} recorded market replay",
                coin,
                if feed == FeedKind::Bbo {
                    "BBO"
                } else {
                    "depth"
                }
            ),
            origin,
            recording_sha256: manifest.recording_sha256.clone(),
            feed,
            network,
        },
        coin,
        quote_currency: "USDC".into(),
        starting_collateral: "10000".parse()?,
        fee_rate: Amount::ZERO,
        max_abs_position: "1".parse()?,
        max_order_notional: "100000".parse()?,
        max_working_orders: 1,
        max_loss: "1000".parse()?,
        stale_after_ms: policy.stale_after_ms(feed),
    };
    config.validate()?;
    new_directory(&output)?;
    let source_copy = output.join("source");
    new_directory(&source_copy)?;
    for entry in &manifest.files {
        let mut original = File::open(input.join(&entry.file))?.take(entry.bytes + 1);
        let target = source_copy.join(&entry.file);
        let mut copied = new_file(&target)?;
        ensure!(
            std::io::copy(&mut original, &mut copied)? == entry.bytes,
            "source changed during copy"
        );
        copied.sync_all()?;
        ensure!(
            digest_file(&target)? == entry.sha256,
            "source digest changed during copy"
        );
    }
    ensure!(
        source_manifest(&input, origin)? == manifest,
        "original recording changed during snapshot"
    );
    let mut budget = 0;
    let mut manifest_file = new_file(&output.join("source-manifest.json"))?;
    write_line(&mut manifest_file, &manifest, &mut budget)?;
    manifest_file.sync_all()?;
    let mut events = new_file(&output.join("paper-input.jsonl"))?;
    let mut updates = new_file(&output.join("paper-updates.jsonl"))?;
    let mut links = new_file(&output.join("market-links.jsonl"))?;
    let mut mapper = Mapper {
        feed,
        engine: PaperEngine::default(),
        health: None,
        health_time_ns: 0,
        marks: 0,
    };
    let mut last = None;
    let (copied_report, copied_storage) =
        replay_path_observed(&source_copy, false, |record, observation| {
            let event = if record.sequence == 1 {
                PaperEvent::SessionStarted {
                    config: config.clone(),
                }
            } else {
                mapper.event(record, observation)?
            };
            let paper_record = PaperRecord {
                paper_schema_version: RECORDED_PAPER_VERSION,
                sequence: record.sequence,
                monotonic_ns: record.monotonic_ns,
                event,
            };
            write_line(&mut events, &paper_record, &mut budget)?;
            events.sync_data()?;
            let update = mapper.engine.apply(&paper_record)?;
            write_line(&mut updates, &update, &mut budget)?;
            write_line(
                &mut links,
                &mapper.link(record, observation, false),
                &mut budget,
            )?;
            last = Some(record.clone());
            Ok(())
        })?;
    ensure!(
        source_report == copied_report && source_storage == copied_storage,
        "copied source disagrees with original validation"
    );
    ensure!(
        mapper.marks > 0,
        "selected feed produced no usable paper marks"
    );
    let last = last.context("empty source recording")?;
    let end = PaperRecord {
        paper_schema_version: RECORDED_PAPER_VERSION,
        sequence: last.sequence + 1,
        monotonic_ns: last.monotonic_ns,
        event: PaperEvent::SessionEnded {
            reason: "offline recording replay finished".into(),
        },
    };
    write_line(&mut events, &end, &mut budget)?;
    events.sync_all()?;
    let update = mapper.engine.apply(&end)?;
    write_line(&mut updates, &update, &mut budget)?;
    write_line(&mut links, &mapper.link(&last, None, true), &mut budget)?;
    updates.sync_all()?;
    links.sync_all()?;
    let report = MarketReplayReport {
        adapter_version: 1,
        mode: "offline_market_marks_only",
        source: manifest,
        source_report,
        source_storage,
        full_window_verified: false,
        strategy_enabled: false,
        market_marks: mapper.marks,
        paper: mapper.engine.report()?,
    };
    let mut paper_report = new_file(&output.join("paper-report.json"))?;
    write_line(&mut paper_report, &report.paper, &mut budget)?;
    paper_report.sync_all()?;
    // Publish the success report last, after all source and derived data syncs.
    let mut success = new_file(&output.join("market-replay.json"))?;
    write_line(&mut success, &report, &mut budget)?;
    success.sync_all()?;
    Ok(report)
}

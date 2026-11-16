use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, ensure};

use crate::engine::Report;
use crate::event::{Event, FEED_SCHEMA_VERSION, MAX_RECORD_BYTES, Record, SCHEMA_VERSION};
use crate::feeds::{MarketEngine, Observation};
use crate::segments::{
    RecordingFormat, RecordingInput, SegmentLimits, SegmentWriter, StorageSummary,
};

#[derive(Debug, Clone, Copy)]
pub struct JournalLimits {
    pub max_bytes: u64,
    pub min_free_bytes: u64,
}

impl JournalLimits {
    /// For explicitly unbounded library use, not the capture CLI default.
    pub const UNLIMITED: Self = Self {
        max_bytes: u64::MAX,
        min_free_bytes: 0,
    };

    pub(crate) fn check_space(self, path: &Path, incoming_bytes: u64) -> Result<()> {
        if self.min_free_bytes > 0 {
            let available =
                fs2::available_space(path).context("read available filesystem space")?;
            ensure!(
                available.saturating_sub(incoming_bytes) >= self.min_free_bytes
                    && available >= incoming_bytes,
                "free disk space guard: {available} bytes available, {} bytes reserved; capture stopped",
                self.min_free_bytes
            );
        }
        Ok(())
    }
}

impl Default for JournalLimits {
    fn default() -> Self {
        Self {
            max_bytes: 256 * 1024 * 1024,
            min_free_bytes: 1024 * 1024 * 1024,
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub enum JournalMode {
    SingleFile(JournalLimits),
    Segmented(SegmentLimits),
}

struct SingleFile {
    file: File,
    path: PathBuf,
    limits: JournalLimits,
    bytes_written: u64,
}

enum Storage {
    Single(SingleFile),
    Segmented(SegmentWriter),
}

pub struct Journal {
    storage: Storage,
    origin: Instant,
    next_sequence: u64,
    poisoned: bool,
    last_was_end: bool,
    finished: bool,
    schema_version: u16,
}

impl Journal {
    /// Never overwrites or appends to an existing session.
    pub fn create(path: &Path) -> Result<Self> {
        Self::create_with_limits(path, JournalLimits::UNLIMITED)
    }

    pub fn create_with_limits(path: &Path, limits: JournalLimits) -> Result<Self> {
        Self::create_single_versioned(path, limits, SCHEMA_VERSION)
    }

    fn create_single_versioned(
        path: &Path,
        limits: JournalLimits,
        schema_version: u16,
    ) -> Result<Self> {
        ensure!(limits.max_bytes > 0, "journal size limit must be positive");
        let parent = path
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
            .unwrap_or(Path::new("."));
        limits.check_space(parent, 0)?;
        let file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(path)
            .with_context(|| {
                format!(
                    "create new journal {} (existing files are never overwritten)",
                    path.display()
                )
            })?;
        file.sync_all().context("sync new journal file")?;
        // On Unix, persist the new directory entry as well as the file data.
        #[cfg(unix)]
        File::open(parent)?
            .sync_all()
            .context("sync journal directory")?;
        Ok(Self::new(
            Storage::Single(SingleFile {
                file,
                path: path.to_path_buf(),
                limits,
                bytes_written: 0,
            }),
            schema_version,
        ))
    }

    pub fn create_segmented(path: &Path, limits: SegmentLimits) -> Result<Self> {
        Self::create_versioned(path, JournalMode::Segmented(limits), SCHEMA_VERSION)
    }

    pub fn create_versioned(path: &Path, mode: JournalMode, schema_version: u16) -> Result<Self> {
        ensure!(
            matches!(schema_version, SCHEMA_VERSION | FEED_SCHEMA_VERSION),
            "unsupported writer schema version"
        );
        match mode {
            JournalMode::SingleFile(limits) => {
                Self::create_single_versioned(path, limits, schema_version)
            }
            JournalMode::Segmented(limits) => Ok(Self::new(
                Storage::Segmented(SegmentWriter::create(path, limits, schema_version)?),
                schema_version,
            )),
        }
    }

    fn new(storage: Storage, schema_version: u16) -> Self {
        Self {
            storage,
            origin: Instant::now(),
            next_sequence: 1,
            poisoned: false,
            last_was_end: false,
            finished: false,
            schema_version,
        }
    }

    /// Sync to stable storage before publishing the event or sending an action.
    /// A failed write poisons the writer: callers must stop, not continue a partial log.
    pub fn append(&mut self, connection_id: u64, event: Event) -> Result<Record> {
        ensure!(!self.poisoned, "journal is unusable after a failed write");
        ensure!(
            !self.last_was_end && !self.finished,
            "cannot append after session end"
        );
        let record = Record {
            schema_version: self.schema_version,
            sequence: self.next_sequence,
            local_time_ns: SystemTime::now()
                .duration_since(UNIX_EPOCH)?
                .as_nanos()
                .try_into()?,
            monotonic_ns: self.origin.elapsed().as_nanos().try_into()?,
            connection_id,
            event,
        };
        let mut bytes = serde_json::to_vec(&record)?;
        bytes.push(b'\n');
        ensure!(
            bytes.len() <= MAX_RECORD_BYTES,
            "record exceeds journal size limit"
        );
        self.poisoned = true;
        match &mut self.storage {
            Storage::Single(storage) => storage.append(&bytes)?,
            Storage::Segmented(storage) => storage.append(&record, &bytes)?,
        }
        self.poisoned = false;
        self.last_was_end = matches!(record.event, Event::SessionEnded { .. });
        self.next_sequence += 1;
        Ok(record)
    }

    /// Drop never invents an end marker or seals an interrupted tail as complete.
    pub fn finish(&mut self) -> Result<()> {
        ensure!(
            !self.poisoned && !self.finished,
            "journal is unusable or already finalized"
        );
        ensure!(
            self.last_was_end,
            "cannot finalize journal without a session end"
        );
        self.poisoned = true;
        match &mut self.storage {
            Storage::Single(storage) => storage.file.sync_all()?,
            Storage::Segmented(storage) => storage.finish()?,
        }
        self.poisoned = false;
        self.finished = true;
        Ok(())
    }
}

impl SingleFile {
    fn append(&mut self, bytes: &[u8]) -> Result<()> {
        let new_length = self
            .bytes_written
            .checked_add(bytes.len() as u64)
            .context("journal byte counter overflow")?;
        ensure!(
            new_length <= self.limits.max_bytes,
            "journal size limit reached: next record would exceed {} bytes; capture stopped (replay the valid prefix with --allow-incomplete)",
            self.limits.max_bytes
        );
        self.limits.check_space(&self.path, bytes.len() as u64)?;
        self.file
            .write_all(bytes)
            .context("write journal; capture stopped")?;
        self.file
            .sync_data()
            .context("sync journal; capture stopped")?;
        self.bytes_written = new_length;
        Ok(())
    }
}

/// Emit quotes through the same engine used during capture. Recovery mode only
/// accepts a valid prefix; it never skips a malformed newline-terminated record.
pub fn replay(
    path: &Path,
    allow_incomplete: bool,
    mut emit: impl FnMut(&Observation) -> Result<()>,
) -> Result<Report> {
    let (report, _) = replay_path_observed(path, allow_incomplete, |_, quote| {
        if let Some(quote) = quote {
            emit(quote)?;
        }
        Ok(())
    })?;
    Ok(report)
}

/// Directory containers verify all sealed checksums before any event is emitted.
pub fn replay_path_observed(
    path: &Path,
    allow_incomplete: bool,
    observe: impl FnMut(&Record, Option<&Observation>) -> Result<()>,
) -> Result<(Report, StorageSummary)> {
    let mut input = RecordingInput::open(path, allow_incomplete)?;
    let mut report = replay_observed_versioned(
        BufReader::new(&mut input.reader),
        allow_incomplete,
        input.event_schema_version,
        observe,
    )?;
    if input.summary.format == RecordingFormat::SegmentedV1 {
        if input.summary.finalized {
            ensure!(
                report.complete,
                "finalized container is missing a session end"
            );
            ensure!(
                Some(report.records) == input.expected_records,
                "container footer record-count mismatch"
            );
        } else {
            report.complete = false;
        }
    } else {
        input.summary.finalized = report.complete;
    }
    Ok((report, input.summary))
}

pub fn replay_reader(
    reader: impl BufRead,
    allow_incomplete: bool,
    mut emit: impl FnMut(&Observation) -> Result<()>,
) -> Result<Report> {
    replay_observed(reader, allow_incomplete, |_, quote| {
        if let Some(quote) = quote {
            emit(quote)?;
        }
        Ok(())
    })
}

/// Observe only records accepted by the engine; a market-data error is terminal.
/// This keeps diagnostic metrics outside deterministic state transitions.
pub fn replay_observed(
    reader: impl BufRead,
    allow_incomplete: bool,
    observe: impl FnMut(&Record, Option<&Observation>) -> Result<()>,
) -> Result<Report> {
    replay_observed_versioned(reader, allow_incomplete, None, observe)
}

fn replay_observed_versioned(
    mut reader: impl BufRead,
    allow_incomplete: bool,
    expected_schema: Option<u16>,
    mut observe: impl FnMut(&Record, Option<&Observation>) -> Result<()>,
) -> Result<Report> {
    let mut engine = MarketEngine::default();
    let mut line_number = 0_u64;
    loop {
        let mut bytes = Vec::new();
        let length =
            Read::take(&mut reader, (MAX_RECORD_BYTES + 1) as u64).read_until(b'\n', &mut bytes)?;
        if length == 0 {
            break;
        }
        line_number += 1;
        ensure!(
            length <= MAX_RECORD_BYTES,
            "line {line_number} exceeds journal size limit"
        );
        if bytes.last() != Some(&b'\n') {
            ensure!(
                !engine.report().complete,
                "unexpected data after completed session"
            );
            ensure!(
                allow_incomplete,
                "unterminated final record at line {line_number}; use --allow-incomplete for crash recovery"
            );
            break;
        }
        let record: Record = serde_json::from_slice(&bytes)
            .with_context(|| format!("invalid journal JSON at line {line_number}"))?;
        ensure!(
            expected_schema.is_none_or(|version| version == record.schema_version),
            "record schema differs from container header at line {line_number}"
        );
        let quote = engine
            .apply(&record)
            .with_context(|| format!("replay failed at line {line_number}"))?;
        observe(&record, quote.as_ref())?;
    }
    let report = engine.report();
    ensure!(report.records > 0, "journal contains no complete records");
    ensure!(
        allow_incomplete || report.complete,
        "session has no end event; use --allow-incomplete for crash recovery"
    );
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::event::Network;

    fn session_start() -> Event {
        Event::SessionStarted {
            coin: "BTC".into(),
            network: Network::Mainnet,
            application_version: "test".into(),
        }
    }

    fn single(journal: &mut Journal) -> &mut SingleFile {
        let Storage::Single(storage) = &mut journal.storage else {
            panic!("expected single-file storage")
        };
        storage
    }

    #[test]
    fn failed_file_write_poisons_the_journal_and_prevents_continuation() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("journal.jsonl");
        let mut journal = Journal::create(&path).unwrap();
        // Replace the handle with a read-only handle to inject a real OS write
        // failure without modifying system resource limits or filling a disk.
        single(&mut journal).file = File::open(&path).unwrap();
        assert!(journal.append(0, session_start()).is_err());
        assert!(journal.poisoned);
        let error = journal.append(0, session_start()).unwrap_err();
        assert!(error.to_string().contains("unusable after a failed write"));
        assert!(std::fs::read(path).unwrap().is_empty());
    }

    #[test]
    fn oversized_record_is_rejected_before_writing_without_consuming_a_sequence() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("journal.jsonl");
        let mut journal = Journal::create(&path).unwrap();
        assert!(
            journal
                .append(
                    1,
                    Event::TextReceived {
                        text: "x".repeat(MAX_RECORD_BYTES)
                    }
                )
                .is_err()
        );
        assert!(std::fs::read(&path).unwrap().is_empty());
        assert!(!journal.poisoned);
        assert_eq!(journal.append(0, session_start()).unwrap().sequence, 1);
    }

    #[test]
    fn disk_reserve_is_rechecked_before_each_write_and_keeps_the_valid_prefix() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("journal.jsonl");
        let mut journal = Journal::create(&path).unwrap();
        journal.append(0, session_start()).unwrap();
        let before = std::fs::read(&path).unwrap();
        // Inject an impossible reserve after startup, without filling the disk.
        single(&mut journal).limits.min_free_bytes = u64::MAX;
        let error = journal
            .append(
                1,
                Event::ConnectionAttempt {
                    endpoint: Network::Mainnet.endpoint().into(),
                },
            )
            .unwrap_err();
        assert!(error.to_string().contains("free disk space guard"));
        assert_eq!(std::fs::read(&path).unwrap(), before);
        assert_eq!(journal.next_sequence, 2);
    }
}

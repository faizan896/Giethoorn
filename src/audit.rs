//! Read-only forensic audit of a completed supervision root. Recompute evidence;
//! do not trust saved summaries or cached inspections as the source of truth.

use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File};
use std::io::{BufRead, BufReader, Read};
use std::path::Path;

use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::event::{
    Event, FEED_SCHEMA_VERSION, FeedPolicy, MAX_RECORD_BYTES, Network, Record, SCHEMA_VERSION,
};
use crate::inspect::inspect;
use crate::supervisor::{SupervisorReport, SupervisorStatus, compare_quotes};

const MAX_REPORT_BYTES: u64 = 16 * 1024 * 1024;
const MAX_LINE_BYTES: u64 = 64 * 1024;
const MAX_CONTROL_BYTES: u64 = 64 * 1024 * 1024;
const ROOT_FILES: &[&str] = &[
    "collector.bin",
    "configuration.json",
    "supervisor.lock",
    "events.jsonl",
    "resources.jsonl",
    "summary.json",
];

#[derive(Deserialize)]
struct Configuration {
    schema_version: u16,
    collector_sha256: String,
    coin: String,
    network: Network,
    duration_secs: u64,
    run_duration_secs: u64,
    max_restarts: u32,
    max_segment_bytes: u64,
    max_run_bytes: u64,
    max_total_recording_bytes: u64,
    #[serde(default = "legacy_schema")]
    event_schema_version: u16,
    #[serde(default)]
    feed_policy: Option<FeedPolicy>,
}

fn legacy_schema() -> u16 {
    SCHEMA_VERSION
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Control {
    schema_version: u16,
    sequence: u64,
    local_time_ns: u64,
    elapsed_ns: u64,
    kind: String,
    data: Value,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Sample {
    run: u32,
    pid: u32,
    elapsed_ns: u64,
    rss_bytes: Option<u64>,
    open_fds: Option<u64>,
}

struct Attempt {
    pid: u32,
    started_ns: u64,
    exited_ns: Option<u64>,
    exit_code: Option<i32>,
    signal: Option<i32>,
    validated: bool,
    restarted: bool,
    interrupted: bool,
    interrupt_ns: Option<u64>,
    watchdog: bool,
    forced: bool,
    allowance: u64,
    comparison: Option<String>,
    snapshots: u64,
    bytes: u64,
}

#[derive(Debug, Serialize)]
pub struct AuditedRun {
    pub run: u32,
    pub directory: String,
    pub snapshots: u64,
    pub recording_bytes: u64,
    pub sealed_segments: u64,
    pub finalized: bool,
    pub comparison: String,
}

#[derive(Debug, Serialize)]
pub struct SupervisionAudit {
    pub schema_version: u16,
    /// Integrity/lifecycle consistency, not a claim that collection was healthy.
    pub integrity: &'static str,
    pub supervisor_status: SupervisorStatus,
    pub full_window_completed: bool,
    pub collector_sha256: String,
    pub coin: String,
    pub network: Network,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub feed_policy: Option<FeedPolicy>,
    pub control_records: u64,
    pub resource_samples: u64,
    pub started_runs: u32,
    pub validated_runs: u32,
    pub restarts: u32,
    pub snapshots: u64,
    pub recording_bytes: u64,
    pub artifact_bytes: u64,
    pub peak_sampled_rss_bytes: u64,
    pub max_sampled_open_fds: u64,
    pub runs: Vec<AuditedRun>,
}

fn regular(path: &Path) -> Result<u64> {
    let metadata = fs::symlink_metadata(path)
        .with_context(|| format!("missing audit artifact {}", path.display()))?;
    ensure!(
        metadata.file_type().is_file(),
        "audit artifact must be a regular file: {}",
        path.display()
    );
    Ok(metadata.len())
}

fn json_file<T: DeserializeOwned>(path: &Path) -> Result<T> {
    ensure!(
        regular(path)? <= MAX_REPORT_BYTES,
        "audit JSON artifact exceeds size limit"
    );
    let mut bytes = Vec::new();
    File::open(path)?
        .take(MAX_REPORT_BYTES + 1)
        .read_to_end(&mut bytes)?;
    ensure!(
        bytes.len() as u64 <= MAX_REPORT_BYTES && bytes.last() == Some(&b'\n'),
        "incomplete audit artifact {}; use per-run recovery for interrupted supervision",
        path.display()
    );
    serde_json::from_slice(&bytes).with_context(|| format!("invalid audit JSON {}", path.display()))
}

fn lines<T: DeserializeOwned>(
    path: &Path,
    mut observe: impl FnMut(T) -> Result<()>,
) -> Result<u64> {
    ensure!(
        regular(path)? <= MAX_CONTROL_BYTES,
        "control artifact exceeds audit size limit"
    );
    let mut reader = BufReader::new(File::open(path)?);
    let mut count = 0;
    loop {
        let mut bytes = Vec::new();
        let length = Read::take(&mut reader, MAX_LINE_BYTES + 1).read_until(b'\n', &mut bytes)?;
        if length == 0 {
            break;
        }
        ensure!(
            length as u64 <= MAX_LINE_BYTES && bytes.last() == Some(&b'\n'),
            "invalid control record boundary in {}",
            path.display()
        );
        count += 1;
        let value = serde_json::from_slice(&bytes)
            .with_context(|| format!("invalid control JSON at {} line {count}", path.display()))?;
        observe(value).with_context(|| {
            format!(
                "invalid control evidence at {} line {count}",
                path.display()
            )
        })?;
    }
    Ok(count)
}

fn number(data: &Value, field: &str) -> Result<u64> {
    data.get(field)
        .and_then(Value::as_u64)
        .with_context(|| format!("missing integer {field}"))
}
fn flag(data: &Value, field: &str) -> Result<bool> {
    data.get(field)
        .and_then(Value::as_bool)
        .with_context(|| format!("missing boolean {field}"))
}
fn text<'a>(data: &'a Value, field: &str) -> Result<&'a str> {
    data.get(field)
        .and_then(Value::as_str)
        .with_context(|| format!("missing text {field}"))
}
fn optional_code(data: &Value, field: &str) -> Result<Option<i32>> {
    let value = data
        .get(field)
        .with_context(|| format!("missing {field}"))?;
    if value.is_null() {
        Ok(None)
    } else {
        Ok(Some(
            value
                .as_i64()
                .context("exit code is not integer")?
                .try_into()?,
        ))
    }
}

pub fn audit_supervision(root: &Path) -> Result<SupervisionAudit> {
    ensure!(root.is_dir(), "supervision audit requires a directory");
    regular(&root.join("supervisor.lock"))?;
    let lock = File::open(root.join("supervisor.lock"))?;
    fs2::FileExt::try_lock_shared(&lock).context("supervisor is active; stop it before audit")?;
    let summary:SupervisorReport=json_file(&root.join("summary.json"))
        .context("supervision has no valid final summary; inspect individual run/session directories with --allow-incomplete")?;
    let config: Configuration = json_file(&root.join("configuration.json"))?;
    ensure!(
        matches!(
            (&config.feed_policy, config.event_schema_version),
            (None, SCHEMA_VERSION) | (Some(_), FEED_SCHEMA_VERSION)
        ),
        "configured event schema and feed policy disagree"
    );
    if let Some(policy) = &config.feed_policy {
        policy.validate()?;
    }
    ensure!(
        summary.schema_version == 1 && config.schema_version == 1,
        "unsupported supervision schema"
    );
    ensure!(
        config.duration_secs > 0 && config.run_duration_secs > 0,
        "invalid configured duration"
    );
    ensure!(
        summary.requested_duration_secs == config.duration_secs,
        "requested duration differs from configuration"
    );
    ensure!(
        summary.collector_sha256 == config.collector_sha256,
        "snapshot hashes disagree between metadata files"
    );
    regular(&root.join("collector.bin"))?;
    let mut executable = File::open(root.join("collector.bin"))?;
    let mut hash = Sha256::new();
    let mut buffer = [0; 65536];
    loop {
        let count = executable.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        hash.update(&buffer[..count]);
    }
    ensure!(
        format!("{:x}", hash.finalize()) == summary.collector_sha256,
        "collector executable checksum mismatch"
    );
    let mut attempts = BTreeMap::<u32, Attempt>::new();
    let mut sequence = 0_u64;
    let mut elapsed = 0_u64;
    let mut restarts = 0_u32;
    let mut stopped = false;
    let mut failed = false;
    let mut before_stop = 0_u64;
    let records = lines::<Control>(&root.join("events.jsonl"), |event| {
        ensure!(
            !stopped && event.schema_version == 1 && event.sequence == sequence + 1,
            "invalid control sequence/version or event after stop"
        );
        ensure!(
            event.elapsed_ns >= elapsed,
            "control monotonic time regressed"
        );
        let _recorded_wall_time = event.local_time_ns;
        if sequence == 0 {
            ensure!(
                event.kind == "started",
                "control log does not start with started"
            );
        }
        if failed {
            ensure!(
                event.kind == "stopped",
                "control event after terminal failure"
            );
        }
        sequence = event.sequence;
        match event.kind.as_str() {
            "started" => ensure!(
                sequence == 1 && attempts.is_empty(),
                "duplicate or late supervisor start"
            ),
            "child_started" => {
                ensure!(
                    sequence > 1 && !failed,
                    "child started outside active supervision"
                );
                if let Some(previous) = attempts.values().next_back() {
                    ensure!(
                        previous.validated && (previous.exit_code == Some(0) || previous.restarted),
                        "new child before previous validation/restart decision"
                    );
                }
                let run: u32 = number(&event.data, "run")?.try_into()?;
                ensure!(
                    run as usize == attempts.len() + 1 && run <= 4096,
                    "noncontiguous run number"
                );
                ensure!(
                    text(&event.data, "directory")? == format!("run-{run:06}"),
                    "noncanonical run directory"
                );
                let duration = number(&event.data, "duration_secs")?;
                ensure!(
                    duration > 0 && duration <= config.run_duration_secs,
                    "child duration exceeds configuration"
                );
                let pid: u32 = number(&event.data, "pid")?.try_into()?;
                ensure!(pid > 0, "invalid child PID");
                attempts.insert(
                    run,
                    Attempt {
                        pid,
                        started_ns: event.elapsed_ns,
                        exited_ns: None,
                        exit_code: None,
                        signal: None,
                        validated: false,
                        restarted: false,
                        interrupted: false,
                        interrupt_ns: None,
                        watchdog: false,
                        forced: false,
                        allowance: number(&event.data, "recording_allowance")?,
                        comparison: None,
                        snapshots: 0,
                        bytes: 0,
                    },
                );
            }
            "child_exited"
            | "child_validated"
            | "restart_scheduled"
            | "child_interrupt_requested"
            | "child_forced_stop" => {
                let run: u32 = number(&event.data, "run")?.try_into()?;
                ensure!(
                    run as usize == attempts.len(),
                    "control event refers to a noncurrent child"
                );
                let attempt = attempts.get_mut(&run).context("event before child start")?;
                match event.kind.as_str() {
                    "child_exited" => {
                        ensure!(attempt.exited_ns.is_none(), "duplicate child exit");
                        attempt.exit_code = optional_code(&event.data, "exit_code")?;
                        attempt.signal = optional_code(&event.data, "signal")?;
                        ensure!(
                            attempt.exit_code.is_some() != attempt.signal.is_some(),
                            "ambiguous child exit"
                        );
                        attempt.exited_ns = Some(event.elapsed_ns);
                    }
                    "child_validated" => {
                        ensure!(
                            attempt.exited_ns.is_some() && !attempt.validated,
                            "validation before exit or repeated validation"
                        );
                        attempt.validated = true;
                        attempt.comparison = Some(text(&event.data, "comparison")?.into());
                        attempt.snapshots = number(&event.data, "snapshots")?;
                        attempt.bytes = number(&event.data, "recording_bytes")?;
                    }
                    "restart_scheduled" => {
                        ensure!(
                            attempt.validated
                                && !attempt.restarted
                                && !attempt.watchdog
                                && !attempt.forced,
                            "invalid restart lifecycle"
                        );
                        ensure!(
                            attempt.exit_code == Some(10) || attempt.signal == Some(9),
                            "nonretryable child was restarted"
                        );
                        restarts += 1;
                        ensure!(
                            restarts <= config.max_restarts
                                && number(&event.data, "restart")? == u64::from(restarts),
                            "restart budget/count mismatch"
                        );
                        ensure!(
                            number(&event.data, "backoff_secs")? == 1_u64 << (restarts - 1).min(5),
                            "restart backoff mismatch"
                        );
                        attempt.restarted = true;
                    }
                    "child_interrupt_requested" => {
                        ensure!(
                            attempt.exited_ns.is_none() && !attempt.interrupted,
                            "late or repeated child interrupt"
                        );
                        attempt.interrupted = true;
                        attempt.interrupt_ns = Some(event.elapsed_ns);
                        attempt.watchdog = flag(&event.data, "watchdog")?;
                    }
                    _ => {
                        ensure!(
                            attempt.interrupted && !attempt.forced && attempt.exited_ns.is_none(),
                            "invalid forced stop"
                        );
                        attempt.forced = true;
                    }
                }
            }
            "failed" => {
                ensure!(
                    !failed && summary.status == SupervisorStatus::Failed,
                    "failure event/status mismatch"
                );
                ensure!(
                    summary.reason.as_deref() == Some(text(&event.data, "error")?),
                    "saved failure reason differs from control event"
                );
                failed = true;
            }
            "stopped" => {
                ensure!(
                    serde_json::to_value(&summary.status)?
                        == event
                            .data
                            .get("status")
                            .cloned()
                            .context("missing stopped status")?,
                    "saved status differs from stop event"
                );
                before_stop = elapsed;
                stopped = true;
            }
            _ => bail!("unknown control event {}", event.kind),
        }
        elapsed = event.elapsed_ns;
        Ok(())
    })?;
    ensure!(records > 0 && stopped, "control log has no final stop");
    ensure!(
        !attempts.values().any(|a| a.watchdog || a.forced)
            || summary.status == SupervisorStatus::Failed,
        "watchdog/forced stop was relabeled as healthy"
    );
    ensure!(
        summary.elapsed_ns >= before_stop && summary.elapsed_ns <= elapsed,
        "summary elapsed time outside control bounds"
    );
    ensure!(
        summary.started_runs as usize == attempts.len() && summary.restarts == restarts,
        "summary process/restart totals disagree with controls"
    );
    ensure!(
        (summary.status == SupervisorStatus::Failed) == failed,
        "failed status/event mismatch"
    );
    let control_bytes =
        regular(&root.join("events.jsonl"))? + regular(&root.join("resources.jsonl"))?;
    ensure!(
        control_bytes <= MAX_CONTROL_BYTES,
        "control artifacts exceed supervisor budget"
    );
    let mut peak_rss = 0_u64;
    let mut max_fds = 0_u64;
    let mut last_sample = 0_u64;
    let samples = lines::<Sample>(&root.join("resources.jsonl"), |sample| {
        let attempt = attempts
            .get(&sample.run)
            .context("resource sample has unknown run")?;
        ensure!(
            sample.pid == attempt.pid
                && sample.elapsed_ns >= last_sample
                && sample.elapsed_ns >= attempt.started_ns
                && Some(sample.elapsed_ns) <= attempt.exited_ns,
            "resource sample outside child lifetime"
        );
        last_sample = sample.elapsed_ns;
        peak_rss = peak_rss.max(sample.rss_bytes.unwrap_or(0));
        max_fds = max_fds.max(sample.open_fds.unwrap_or(0));
        Ok(())
    })?;
    ensure!(
        peak_rss == summary.peak_sampled_rss_bytes && max_fds == summary.max_sampled_open_fds,
        "saved resource maxima disagree with samples"
    );
    let mut expected: BTreeSet<String> = ROOT_FILES.iter().map(|s| (*s).into()).collect();
    let mut artifact_bytes = 0_u64;
    for name in ROOT_FILES {
        artifact_bytes = artifact_bytes
            .checked_add(regular(&root.join(name))?)
            .context("artifact size overflow")?;
    }
    let mut total_bytes = 0_u64;
    let mut snapshots = 0_u64;
    let mut audited = Vec::new();
    ensure!(
        summary.runs.len() <= attempts.len(),
        "summary claims unannounced runs"
    );
    ensure!(
        summary
            .runs
            .iter()
            .enumerate()
            .all(|(i, r)| r.run as usize == i + 1),
        "saved validated runs are duplicated or out of order"
    );
    for (&run, attempt) in &attempts {
        let name = format!("run-{run:06}");
        expected.insert(name.clone());
        let path = root.join(&name);
        ensure!(
            fs::symlink_metadata(&path)?.file_type().is_dir(),
            "run directory is missing or is a symlink"
        );
        let session = path.join("session");
        ensure!(
            fs::symlink_metadata(&session)?.file_type().is_dir(),
            "run has no regular recording directory; inspect failed attempt manually"
        );
        let inspection = inspect(&session, attempt.exit_code != Some(0))
            .with_context(|| format!("audit run {run}"))?;
        let first_path = session.join("segment-00000001.jsonl");
        regular(&first_path)?;
        let mut first_line = Vec::new();
        Read::take(
            BufReader::new(File::open(first_path)?),
            (MAX_RECORD_BYTES + 1) as u64,
        )
        .read_until(b'\n', &mut first_line)?;
        ensure!(
            first_line.len() <= MAX_RECORD_BYTES && first_line.last() == Some(&b'\n'),
            "invalid first record in audit"
        );
        let first: Record = serde_json::from_slice(&first_line)?;
        let identity_matches = match &first.event {
            Event::SessionStarted { coin, network, .. } => {
                coin == &config.coin
                    && *network == config.network
                    && config.feed_policy.is_none()
                    && first.schema_version == SCHEMA_VERSION
            }
            Event::FeedSessionStarted {
                coin,
                network,
                policy,
                ..
            } => {
                coin == &config.coin
                    && *network == config.network
                    && config.feed_policy.as_ref() == Some(policy)
                    && first.schema_version == FEED_SCHEMA_VERSION
            }
            _ => false,
        };
        ensure!(
            identity_matches,
            "recorded market/network/feed policy differs from supervision configuration"
        );
        let allowance = config
            .max_total_recording_bytes
            .saturating_sub(total_bytes)
            .min(config.max_run_bytes);
        ensure!(
            attempt.allowance == allowance && inspection.file_bytes <= allowance,
            "run allowance differs from global budget"
        );
        total_bytes = total_bytes
            .checked_add(inspection.file_bytes)
            .context("recording size overflow")?;
        ensure!(
            total_bytes <= config.max_total_recording_bytes,
            "whole-supervision recording budget exceeded"
        );
        regular(&path.join("live-quotes.jsonl"))?;
        let comparison = compare_quotes(
            &session,
            &path.join("live-quotes.jsonl"),
            !inspection.storage.finalized,
        )?;
        if attempt.exit_code == Some(0) {
            ensure!(
                inspection.storage.finalized
                    && inspection.session.complete
                    && inspection.two_sided_snapshots > 0
                    && inspection
                        .session
                        .feeds
                        .as_ref()
                        .is_none_or(|f| f.all_required_fresh_observed),
                "successful child exit has no finalized usable recording"
            );
            match inspection.session.end_reason.as_deref() {
                Some("duration_elapsed") => {}
                Some("interrupted") => {
                    ensure!(
                        run as usize == attempts.len(),
                        "new child started after interrupted collection"
                    );
                    if matches!(
                        summary.status,
                        SupervisorStatus::Completed | SupervisorStatus::CompletedWithRestarts
                    ) {
                        ensure!(
                            attempt.interrupted
                                && attempt.interrupt_ns.is_some_and(|at| u128::from(at)
                                    >= u128::from(config.duration_secs) * 1_000_000_000),
                            "interrupted child was relabeled as a full supervision window"
                        );
                    }
                }
                _ => bail!("successful child exit contradicts recorded end reason"),
            }
        }
        let claimed = summary.runs.iter().find(|s| s.run == run);
        ensure!(
            attempt.validated == claimed.is_some(),
            "saved validated-run set differs from control log"
        );
        if let Some(claimed) = claimed {
            ensure!(
                claimed.directory == name
                    && claimed.pid == attempt.pid
                    && claimed.exit_code == attempt.exit_code
                    && claimed.signal == attempt.signal,
                "saved child identity/exit differs from control log"
            );
            ensure!(
                claimed.elapsed_ns > 0 && claimed.elapsed_ns <= summary.elapsed_ns,
                "invalid saved child elapsed time"
            );
            ensure!(
                claimed.snapshots == inspection.two_sided_snapshots
                    && attempt.snapshots == inspection.two_sided_snapshots
                    && claimed.recording_bytes == inspection.file_bytes
                    && attempt.bytes == inspection.file_bytes
                    && claimed.finalized == inspection.storage.finalized
                    && claimed.comparison == comparison
                    && attempt.comparison.as_deref() == Some(comparison),
                "saved run totals/comparison differ from actual recording"
            );
            let saved: Value = json_file(&path.join("inspection.json"))?;
            ensure!(
                saved == serde_json::to_value(&inspection)?,
                "cached inspection differs from recomputed evidence"
            );
            snapshots = snapshots
                .checked_add(inspection.two_sided_snapshots)
                .context("snapshot count overflow")?;
        }
        let mut run_names = BTreeSet::from([
            "session".to_string(),
            "live-quotes.jsonl".into(),
            "capture.stderr".into(),
        ]);
        if path.join("inspection.json").exists() {
            run_names.insert("inspection.json".into());
        }
        for entry in fs::read_dir(&path)? {
            let entry = entry?;
            let entry_name = entry
                .file_name()
                .into_string()
                .map_err(|_| anyhow::anyhow!("non-UTF-8 run artifact"))?;
            ensure!(
                run_names.remove(&entry_name),
                "unexpected run artifact {entry_name}"
            );
            if entry_name != "session" {
                artifact_bytes = artifact_bytes
                    .checked_add(regular(&entry.path())?)
                    .context("artifact size overflow")?;
            }
        }
        ensure!(run_names.is_empty(), "missing run artifact");
        for entry in fs::read_dir(&session)? {
            let entry = entry?;
            let length = regular(&entry.path())?;
            if entry.file_name() != "index.jsonl" {
                ensure!(
                    length <= config.max_segment_bytes,
                    "segment exceeds configured policy"
                );
            }
        }
        artifact_bytes = artifact_bytes
            .checked_add(inspection.file_bytes)
            .context("artifact size overflow")?;
        audited.push(AuditedRun {
            run,
            directory: name,
            snapshots: inspection.two_sided_snapshots,
            recording_bytes: inspection.file_bytes,
            sealed_segments: inspection.storage.sealed_segments,
            finalized: inspection.storage.finalized,
            comparison: comparison.into(),
        });
    }
    for entry in fs::read_dir(root)? {
        let name = entry?
            .file_name()
            .into_string()
            .map_err(|_| anyhow::anyhow!("non-UTF-8 supervision artifact"))?;
        ensure!(
            expected.remove(&name),
            "unexpected supervision artifact {name}"
        );
    }
    ensure!(expected.is_empty(), "missing supervision artifact");
    ensure!(
        summary.recording_bytes == total_bytes && summary.validated_snapshots == snapshots,
        "saved aggregate totals differ from actual recordings"
    );
    let completed = matches!(
        summary.status,
        SupervisorStatus::Completed | SupervisorStatus::CompletedWithRestarts
    );
    if completed {
        ensure!(
            summary.reason.is_none(),
            "completed supervision has a failure reason"
        );
        ensure!(
            snapshots > 0
                && summary
                    .runs
                    .last()
                    .is_some_and(|r| r.exit_code == Some(0) && r.finalized),
            "completed supervision has no healthy final run"
        );
        ensure!(
            (restarts > 0) == (summary.status == SupervisorStatus::CompletedWithRestarts),
            "completed restart status mismatch"
        );
    }
    let full_window = completed
        && u128::from(summary.elapsed_ns) >= u128::from(config.duration_secs) * 1_000_000_000;
    Ok(SupervisionAudit {
        schema_version: 1,
        integrity: "verified",
        supervisor_status: summary.status,
        full_window_completed: full_window,
        collector_sha256: summary.collector_sha256,
        coin: config.coin,
        network: config.network,
        feed_policy: config.feed_policy,
        control_records: records,
        resource_samples: samples,
        started_runs: summary.started_runs,
        validated_runs: summary.runs.len().try_into()?,
        restarts,
        snapshots,
        recording_bytes: total_bytes,
        artifact_bytes,
        peak_sampled_rss_bytes: peak_rss,
        max_sampled_open_fds: max_fds,
        runs: audited,
    })
}

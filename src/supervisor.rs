//! Bounded public-data process supervision. Never executes orders, resumes a
//! partial journal in place, or retries a failed integrity/recording check.

use std::fs::{self, File, OpenOptions};
use std::io::{BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

use crate::event::{FEED_SCHEMA_VERSION, FeedPolicy, Network, SCHEMA_VERSION};
use crate::hyperliquid::validate_coin;
use crate::inspect::{Inspection, inspect};
use crate::journal::replay;

const MAX_RUNS: usize = 4096;
const MAX_CONTROL_BYTES: u64 = 64 * 1024 * 1024;

#[derive(Debug, Clone)]
pub struct SupervisorOptions {
    pub output_dir: PathBuf,
    pub coin: String,
    pub network: Network,
    pub duration: Duration,
    pub run_duration: Duration,
    pub max_restarts: u32,
    pub max_reconnects: u32,
    pub stale_after_secs: u64,
    pub max_segment_bytes: u64,
    pub max_run_bytes: u64,
    /// Only recording-container bytes across all attempts; see runbook for exclusions.
    pub max_total_recording_bytes: u64,
    pub min_free_bytes: u64,
    pub sample_interval: Duration,
    pub shutdown_grace: Duration,
    pub feed_policy: Option<FeedPolicy>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SupervisorStatus {
    Completed,
    CompletedWithRestarts,
    Interrupted,
    Failed,
    BudgetExhausted,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunSummary {
    pub run: u32,
    pub directory: String,
    pub pid: u32,
    pub exit_code: Option<i32>,
    pub signal: Option<i32>,
    pub elapsed_ns: u64,
    pub comparison: String,
    pub snapshots: u64,
    pub recording_bytes: u64,
    pub finalized: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SupervisorReport {
    pub schema_version: u16,
    pub status: SupervisorStatus,
    pub reason: Option<String>,
    pub requested_duration_secs: u64,
    pub elapsed_ns: u64,
    pub restarts: u32,
    pub recording_bytes: u64,
    pub validated_snapshots: u64,
    pub peak_sampled_rss_bytes: u64,
    pub max_sampled_open_fds: u64,
    pub collector_sha256: String,
    pub started_runs: u32,
    pub runs: Vec<RunSummary>,
}

impl SupervisorReport {
    pub fn successful(&self) -> bool {
        matches!(
            self.status,
            SupervisorStatus::Completed
                | SupervisorStatus::CompletedWithRestarts
                | SupervisorStatus::Interrupted
        )
    }
}

struct ChildGuard(Child);
impl Drop for ChildGuard {
    fn drop(&mut self) {
        if !matches!(self.0.try_wait(), Ok(Some(_))) {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }
}

struct Supervisor {
    options: SupervisorOptions,
    origin: Instant,
    deadline: Instant,
    events: File,
    resources: File,
    _lock: File,
    control_bytes: u64,
    event_sequence: u64,
    collector: PathBuf,
    report: SupervisorReport,
}

fn sync_directory(path: &Path) -> Result<()> {
    #[cfg(unix)]
    File::open(path)?.sync_all()?;
    Ok(())
}

fn new_file(path: &Path) -> Result<File> {
    OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .with_context(|| format!("create new control file {}", path.display()))
}

fn save_json(path: &Path, value: &impl Serialize) -> Result<()> {
    let mut file = new_file(path)?;
    serde_json::to_writer_pretty(&mut file, value)?;
    file.write_all(b"\n")?;
    file.sync_all()?;
    Ok(())
}

fn bounded_message(error: &anyhow::Error) -> String {
    format!("{error:#}").chars().take(4096).collect()
}

pub fn supervise(options: SupervisorOptions, stop: &AtomicBool) -> Result<SupervisorReport> {
    ensure!(cfg!(unix), "process supervision currently requires Unix");
    validate_coin(&options.coin)?;
    if let Some(policy) = &options.feed_policy {
        policy.validate()?;
    }
    ensure!(
        options.duration.as_secs() > 0 && options.run_duration.as_secs() > 0,
        "supervision durations must be at least one second"
    );
    ensure!(
        !options.sample_interval.is_zero() && !options.shutdown_grace.is_zero(),
        "sampling and shutdown grace must be positive"
    );
    ensure!(
        options.max_segment_bytes > 0
            && options.max_run_bytes >= 2048
            && options.max_total_recording_bytes >= 2048,
        "invalid supervisor storage budgets"
    );
    let origin = Instant::now();
    let deadline = origin
        .checked_add(options.duration)
        .context("supervisor duration is too large")?;
    origin
        .checked_add(options.run_duration)
        .context("collector run duration is too large")?;
    origin
        .checked_add(options.sample_interval)
        .context("resource sample interval is too large")?;
    origin
        .checked_add(options.shutdown_grace)
        .context("shutdown grace period is too large")?;
    options
        .run_duration
        .checked_add(options.shutdown_grace)
        .context("collector watchdog duration is too large")?;
    let parent = options
        .output_dir
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    fs::create_dir_all(parent)?;
    let source = if cfg!(target_os = "linux") {
        PathBuf::from("/proc/self/exe")
    } else {
        std::env::current_exe()?
    };
    let mut executable = File::open(source)?;
    let available = fs2::available_space(parent)?;
    ensure!(
        available.saturating_sub(executable.metadata()?.len()) >= options.min_free_bytes,
        "insufficient free disk reserve for supervisor snapshot"
    );
    fs::create_dir(&options.output_dir).context("supervision requires a NEW output directory")?;
    sync_directory(parent)?;
    let lock = new_file(&options.output_dir.join("supervisor.lock"))?;
    fs2::FileExt::try_lock_exclusive(&lock)?;
    let collector = options.output_dir.join("collector.bin");
    let mut open = OpenOptions::new();
    open.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        open.mode(0o755);
    }
    let mut snapshot = open.open(&collector)?;
    let mut hash = Sha256::new();
    let mut buffer = [0; 65536];
    loop {
        let size = executable.read(&mut buffer)?;
        if size == 0 {
            break;
        }
        snapshot.write_all(&buffer[..size])?;
        hash.update(&buffer[..size]);
    }
    snapshot.sync_all()?;
    drop(snapshot);
    let collector_sha256 = format!("{:x}", hash.finalize());
    save_json(
        &options.output_dir.join("configuration.json"),
        &json!({
            "schema_version":1,"coin":options.coin,"network":options.network,
            "duration_secs":options.duration.as_secs(),"run_duration_secs":options.run_duration.as_secs(),
            "max_restarts":options.max_restarts,"max_reconnects":options.max_reconnects,
            "stale_after_secs":options.stale_after_secs,"max_segment_bytes":options.max_segment_bytes,
            "max_run_bytes":options.max_run_bytes,"max_total_recording_bytes":options.max_total_recording_bytes,
            "min_free_bytes":options.min_free_bytes,"collector_sha256":collector_sha256,
            "application_version":env!("CARGO_PKG_VERSION")
            ,"event_schema_version":if options.feed_policy.is_some() {FEED_SCHEMA_VERSION} else {SCHEMA_VERSION},
            "feed_policy":options.feed_policy
        }),
    )?;
    let events = new_file(&options.output_dir.join("events.jsonl"))?;
    let resources = new_file(&options.output_dir.join("resources.jsonl"))?;
    sync_directory(&options.output_dir)?;
    let report = SupervisorReport {
        schema_version: 1,
        status: SupervisorStatus::Completed,
        reason: None,
        requested_duration_secs: options.duration.as_secs(),
        elapsed_ns: 0,
        restarts: 0,
        recording_bytes: 0,
        validated_snapshots: 0,
        peak_sampled_rss_bytes: 0,
        max_sampled_open_fds: 0,
        collector_sha256,
        started_runs: 0,
        runs: Vec::new(),
    };
    let mut supervisor = Supervisor {
        options,
        origin,
        deadline,
        events,
        resources,
        _lock: lock,
        control_bytes: 0,
        event_sequence: 0,
        collector,
        report,
    };
    supervisor.event("started", json!({}))?;
    if let Err(error) = supervisor.run(stop) {
        supervisor.report.status = SupervisorStatus::Failed;
        supervisor.report.reason = Some(bounded_message(&error));
        supervisor.event("failed", json!({"error":bounded_message(&error)}))?;
    }
    supervisor.report.elapsed_ns = supervisor.origin.elapsed().as_nanos().try_into()?;
    supervisor.event("stopped", json!({"status":supervisor.report.status}))?;
    save_json(
        &supervisor.options.output_dir.join("summary.json"),
        &supervisor.report,
    )?;
    sync_directory(&supervisor.options.output_dir)?;
    Ok(supervisor.report)
}

impl Supervisor {
    fn event(&mut self, kind: &str, data: Value) -> Result<()> {
        self.event_sequence += 1;
        let mut bytes = serde_json::to_vec(&json!({
            "schema_version":1,"sequence":self.event_sequence,
            "local_time_ns":u64::try_from(SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos())?,
            "elapsed_ns":u64::try_from(self.origin.elapsed().as_nanos())?,"kind":kind,"data":data
        }))?;
        bytes.push(b'\n');
        self.control_bytes += bytes.len() as u64;
        ensure!(
            self.control_bytes <= MAX_CONTROL_BYTES,
            "supervisor control log budget exhausted"
        );
        self.events.write_all(&bytes)?;
        self.events.sync_data()?;
        Ok(())
    }

    fn sample(&mut self, run: u32, pid: u32) -> Result<()> {
        let mut sample = json!({"run":run,"pid":pid,"elapsed_ns":u64::try_from(self.origin.elapsed().as_nanos())?});
        #[cfg(target_os = "linux")]
        {
            let root = PathBuf::from(format!("/proc/{pid}"));
            if let Ok(status) = fs::read_to_string(root.join("status")) {
                for line in status.lines().filter(|s| s.starts_with("VmRSS:")) {
                    if let Some(rss) = line
                        .split_whitespace()
                        .nth(1)
                        .and_then(|v| v.parse::<u64>().ok())
                    {
                        let bytes = rss * 1024;
                        sample["rss_bytes"] = json!(bytes);
                        self.report.peak_sampled_rss_bytes =
                            self.report.peak_sampled_rss_bytes.max(bytes);
                    }
                }
            }
            if let Ok(entries) = fs::read_dir(root.join("fd")) {
                let count = entries.count() as u64;
                sample["open_fds"] = json!(count);
                self.report.max_sampled_open_fds = self.report.max_sampled_open_fds.max(count);
            }
        }
        let mut bytes = serde_json::to_vec(&sample)?;
        bytes.push(b'\n');
        self.control_bytes += bytes.len() as u64;
        ensure!(
            self.control_bytes <= MAX_CONTROL_BYTES,
            "supervisor control log budget exhausted"
        );
        self.resources.write_all(&bytes)?;
        self.resources.flush()?;
        Ok(())
    }

    fn run(&mut self, stop: &AtomicBool) -> Result<()> {
        loop {
            if stop.load(Ordering::Relaxed) {
                self.report.status = SupervisorStatus::Interrupted;
                break;
            }
            let remaining = self.deadline.saturating_duration_since(Instant::now());
            if remaining.as_secs() == 0 {
                while Instant::now() < self.deadline && !stop.load(Ordering::Relaxed) {
                    std::thread::sleep(
                        self.deadline
                            .saturating_duration_since(Instant::now())
                            .min(Duration::from_millis(50)),
                    );
                }
                if stop.load(Ordering::Relaxed) {
                    self.report.status = SupervisorStatus::Interrupted;
                }
                break;
            }
            ensure!(
                self.report.runs.len() < MAX_RUNS,
                "supervisor run-count limit reached"
            );
            let allowance = self
                .options
                .max_total_recording_bytes
                .saturating_sub(self.report.recording_bytes)
                .min(self.options.max_run_bytes);
            if allowance < 2048 {
                self.report.status = SupervisorStatus::BudgetExhausted;
                self.report.reason =
                    Some("remaining recording budget is too small for another run".into());
                break;
            }
            let duration = remaining.as_secs().min(self.options.run_duration.as_secs());
            let run = self.report.runs.len() as u32 + 1;
            let name = format!("run-{run:06}");
            let directory = self.options.output_dir.join(&name);
            fs::create_dir(&directory)?;
            sync_directory(&self.options.output_dir)?;
            let stdout = new_file(&directory.join("live-quotes.jsonl"))?;
            let stderr = new_file(&directory.join("capture.stderr"))?;
            let mut command = Command::new(&self.collector);
            command
                .args(["collect", "--coin"])
                .arg(&self.options.coin)
                .args([
                    "--network",
                    match self.options.network {
                        Network::Mainnet => "mainnet",
                        Network::Testnet => "testnet",
                    },
                ])
                .arg("--duration-secs")
                .arg(duration.to_string())
                .arg("--max-reconnects")
                .arg(self.options.max_reconnects.to_string())
                .arg("--max-segment-bytes")
                .arg(self.options.max_segment_bytes.to_string())
                .arg("--max-session-bytes")
                .arg(allowance.to_string())
                .arg("--min-free-disk-bytes")
                .arg(self.options.min_free_bytes.to_string())
                .arg("--parent-pid")
                .arg(std::process::id().to_string())
                .arg("--output-dir")
                .arg(directory.join("session"))
                .stdin(Stdio::null())
                .stdout(stdout)
                .stderr(stderr);
            if let Some(policy) = &self.options.feed_policy {
                command
                    .arg("--feed-profile")
                    .arg(policy.profile.argument())
                    .arg("--depth-stale-after-ms")
                    .arg(policy.depth_stale_after_ms.to_string())
                    .arg("--bbo-stale-after-ms")
                    .arg(policy.bbo_stale_after_ms.to_string())
                    .arg("--feed-timer-ms")
                    .arg(policy.timer_interval_ms.to_string());
            } else {
                command
                    .arg("--stale-after-secs")
                    .arg(self.options.stale_after_secs.to_string());
            }
            let started = Instant::now();
            let mut child = ChildGuard(command.spawn().context("start collector snapshot")?);
            let pid = child.0.id();
            self.report.started_runs += 1;
            self.event("child_started", json!({"run":run,"pid":pid,"directory":name,"duration_secs":duration,"recording_allowance":allowance}))?;
            let mut next_sample = Instant::now();
            let mut interrupt_sent = None;
            let mut watchdog = false;
            let mut forced_stop = false;
            let status = loop {
                if let Some(status) = child.0.try_wait()? {
                    break status;
                }
                let now = Instant::now();
                if now >= next_sample {
                    self.sample(run, pid)?;
                    next_sample = now + self.options.sample_interval;
                }
                let timed_out =
                    started.elapsed() > Duration::from_secs(duration) + self.options.shutdown_grace;
                if interrupt_sent.is_none()
                    && (stop.load(Ordering::Relaxed) || now >= self.deadline || timed_out)
                {
                    watchdog = timed_out;
                    request_interrupt(&mut child.0)?;
                    interrupt_sent = Some(now);
                    self.event(
                        "child_interrupt_requested",
                        json!({"run":run,"watchdog":watchdog}),
                    )?;
                }
                if interrupt_sent.is_some_and(|at| at.elapsed() >= self.options.shutdown_grace) {
                    forced_stop = true;
                    child.0.kill()?;
                    self.event("child_forced_stop", json!({"run":run}))?;
                    break child.0.wait()?;
                }
                std::thread::sleep(Duration::from_millis(50));
            };
            let elapsed_ns = started.elapsed().as_nanos().try_into()?;
            self.event(
                "child_exited",
                json!({"run":run,"exit_code":status.code(),"signal":exit_signal(status)}),
            )?;
            // No process can write the container now. Every sealed checksum and
            // the original event stream must validate before a restart is allowed.
            let recovery = !status.success();
            let measured_bytes = recording_bytes(&directory.join("session"))?;
            self.report.recording_bytes = self
                .report
                .recording_bytes
                .checked_add(measured_bytes)
                .context("supervisor byte count overflow")?;
            ensure!(
                self.report.recording_bytes <= self.options.max_total_recording_bytes,
                "supervisor recording budget exceeded"
            );
            let inspection = inspect(&directory.join("session"), recovery)
                .with_context(|| format!("run {run} failed recording validation; no restart"))?;
            let comparison = compare_quotes(
                &directory.join("session"),
                &directory.join("live-quotes.jsonl"),
                !inspection.storage.finalized,
            )?;
            save_json(&directory.join("inspection.json"), &inspection)?;
            ensure!(
                measured_bytes == inspection.file_bytes,
                "recording size changed during validation"
            );
            self.report.validated_snapshots += inspection.two_sided_snapshots;
            self.report.runs.push(RunSummary {
                run,
                directory: name,
                pid,
                exit_code: status.code(),
                signal: exit_signal(status),
                elapsed_ns,
                comparison: comparison.into(),
                snapshots: inspection.two_sided_snapshots,
                recording_bytes: inspection.file_bytes,
                finalized: inspection.storage.finalized,
            });
            self.event("child_validated", json!({"run":run,"comparison":comparison,"snapshots":inspection.two_sided_snapshots,"recording_bytes":inspection.file_bytes}))?;
            if watchdog {
                bail!("collector exceeded its run deadline; no automatic restart");
            }
            ensure!(
                !forced_stop,
                "collector did not stop within the shutdown grace period"
            );
            if stop.load(Ordering::Relaxed) {
                self.report.status = SupervisorStatus::Interrupted;
                break;
            }
            if interrupt_sent.is_some() && Instant::now() >= self.deadline {
                break;
            }
            if inspection.session.end_reason.as_deref() == Some("interrupted") {
                self.report.status = SupervisorStatus::Interrupted;
                break;
            }
            if status.success() {
                require_successful_capture(&inspection)?;
                continue;
            }
            let retryable = status.code() == Some(10) || exit_signal(status) == Some(9);
            ensure!(
                retryable,
                "collector failed with nonretryable exit {:?} / signal {:?}; no restart",
                status.code(),
                exit_signal(status)
            );
            ensure!(
                self.report.restarts < self.options.max_restarts,
                "collector restart budget exhausted"
            );
            self.report.restarts += 1;
            let delay = Duration::from_secs(1_u64 << (self.report.restarts - 1).min(5));
            self.event(
                "restart_scheduled",
                json!({"run":run,"restart":self.report.restarts,"backoff_secs":delay.as_secs()}),
            )?;
            let until = (Instant::now() + delay).min(self.deadline);
            while Instant::now() < until && !stop.load(Ordering::Relaxed) {
                std::thread::sleep(
                    until
                        .saturating_duration_since(Instant::now())
                        .min(Duration::from_millis(50)),
                );
            }
        }
        if self.report.status == SupervisorStatus::Completed {
            ensure!(
                self.report.validated_snapshots > 0,
                "supervision collected no usable snapshots"
            );
            ensure!(
                self.report
                    .runs
                    .last()
                    .is_some_and(|run| run.exit_code == Some(0) && run.finalized),
                "supervision ended before a failed collector recovered"
            );
            if self.report.restarts > 0 {
                self.report.status = SupervisorStatus::CompletedWithRestarts;
            }
        }
        Ok(())
    }
}

fn require_successful_capture(inspection: &Inspection) -> Result<()> {
    ensure!(
        inspection.session.complete
            && inspection.storage.finalized
            && inspection.two_sided_snapshots > 0
            && inspection
                .session
                .feeds
                .as_ref()
                .is_none_or(|f| f.all_required_fresh_observed),
        "collector exited successfully without a finalized usable recording"
    );
    ensure!(
        inspection.session.end_reason.as_deref() == Some("duration_elapsed"),
        "collector completed for an unexpected reason"
    );
    Ok(())
}

fn recording_bytes(path: &Path) -> Result<u64> {
    if !path.exists() {
        return Ok(0);
    }
    let mut bytes = 0_u64;
    for entry in fs::read_dir(path)? {
        let metadata = entry?.path().symlink_metadata()?;
        ensure!(
            metadata.file_type().is_file(),
            "unexpected nonregular recording entry"
        );
        bytes = bytes
            .checked_add(metadata.len())
            .context("recording byte count overflow")?;
    }
    Ok(bytes)
}

/// Crashes can happen after WAL sync but before quote output. In recovery mode,
/// the original bytes must therefore be a prefix of replay, never the reverse.
pub fn compare_quotes(recording: &Path, live: &Path, recovery: bool) -> Result<&'static str> {
    let mut reader = BufReader::new(File::open(live)?);
    let mut live_ended = false;
    replay(recording, recovery, |quote| {
        let mut expected = serde_json::to_vec(quote)?;
        expected.push(b'\n');
        if live_ended {
            return Ok(());
        }
        let mut actual = vec![0; expected.len()];
        let mut filled = 0;
        while filled < actual.len() {
            let count = reader.read(&mut actual[filled..])?;
            if count == 0 {
                live_ended = true;
                break;
            }
            filled += count;
        }
        ensure!(
            actual[..filled] == expected[..filled],
            "live quote bytes diverge from replay"
        );
        ensure!(
            filled == expected.len() || recovery,
            "live quote stream ended before replay"
        );
        Ok(())
    })?;
    let mut extra = [0];
    ensure!(
        reader.read(&mut extra)? == 0,
        "live output contains bytes not present in replay"
    );
    Ok(if recovery { "live_prefix" } else { "exact" })
}

fn exit_signal(status: ExitStatus) -> Option<i32> {
    #[cfg(unix)]
    {
        use std::os::unix::process::ExitStatusExt;
        status.signal()
    }
    #[cfg(not(unix))]
    {
        let _ = status;
        None
    }
}

fn request_interrupt(child: &mut Child) -> Result<()> {
    #[cfg(unix)]
    {
        nix::sys::signal::kill(
            nix::unistd::Pid::from_raw(child.id().try_into()?),
            nix::sys::signal::Signal::SIGINT,
        )?;
    }
    #[cfg(not(unix))]
    {
        child.kill()?;
    }
    Ok(())
}

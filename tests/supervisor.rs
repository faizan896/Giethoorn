#![cfg(target_os = "linux")]
mod common;

use std::fs;
use std::io::{Read, Write};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Output, Stdio};
use std::sync::{
    Arc, Mutex, MutexGuard,
    atomic::{AtomicBool, AtomicUsize, Ordering},
};
use std::thread;
use std::time::{Duration, Instant};

use giethoorn::audit::audit_supervision;
use giethoorn::event::{Event, Record};
use giethoorn::journal::{Journal, replay};
use giethoorn::segments::SegmentLimits;
use giethoorn::supervisor::compare_quotes;
use native_tls::{Identity, TlsAcceptor};
use rcgen::generate_simple_self_signed;
use serde_json::Value;
use tungstenite::Message;

#[derive(Clone, Copy)]
enum ExchangeMode {
    Normal,
    Combined,
    CombinedDropFirst,
    DropFirst,
    DropAll,
    Deny,
    StallHandshake,
}

// A fork temporarily inherits other test threads' locked FDs before exec's
// CLOEXEC closes them. Keep process-spawning and direct-WAL cases isolated in
// this binary; assertions remain unchanged and each case still uses real I/O.
static PROCESS_TESTS: Mutex<()> = Mutex::new(());

fn process_test_guard() -> MutexGuard<'static, ()> {
    PROCESS_TESTS
        .lock()
        .unwrap_or_else(|poison| poison.into_inner())
}

struct Harness {
    _serial: MutexGuard<'static, ()>,
    temp: tempfile::TempDir,
    proxy: String,
    ca: PathBuf,
    stop: Arc<AtomicBool>,
    count: Arc<AtomicUsize>,
    thread: Option<thread::JoinHandle<()>>,
    combined: bool,
}

impl Harness {
    fn new(mode: ExchangeMode) -> Self {
        let serial = process_test_guard();
        let temp = tempfile::tempdir().unwrap();
        let cert = generate_simple_self_signed(vec!["api.hyperliquid.xyz".into()]).unwrap();
        let pem = cert.cert.pem();
        let ca = temp.path().join("root.pem");
        fs::write(&ca, &pem).unwrap();
        let identity =
            Identity::from_pkcs8(pem.as_bytes(), cert.signing_key.serialize_pem().as_bytes())
                .unwrap();
        let acceptor = TlsAcceptor::new(identity).unwrap();
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let proxy = format!("http://{}", listener.local_addr().unwrap());
        let stop = Arc::new(AtomicBool::new(false));
        let stopped = stop.clone();
        let count = Arc::new(AtomicUsize::new(0));
        let connections = count.clone();
        let thread = thread::spawn(move || {
            while !stopped.load(Ordering::Relaxed) {
                let (mut tcp, _) = match listener.accept() {
                    Ok(pair) => pair,
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                        thread::sleep(Duration::from_millis(10));
                        continue;
                    }
                    Err(error) => panic!("mock proxy: {error}"),
                };
                let ordinal = connections.fetch_add(1, Ordering::Relaxed);
                tcp.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
                tcp.set_write_timeout(Some(Duration::from_secs(3))).unwrap();
                let mut headers = Vec::new();
                while !headers.ends_with(b"\r\n\r\n") {
                    let mut byte = [0];
                    tcp.read_exact(&mut byte).unwrap();
                    headers.push(byte[0]);
                    assert!(headers.len() < 4096);
                }
                if matches!(mode, ExchangeMode::Deny) {
                    tcp.write_all(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                        .unwrap();
                    continue;
                }
                tcp.write_all(b"HTTP/1.1 200 Connection established\r\n\r\n")
                    .unwrap();
                if matches!(mode, ExchangeMode::StallHandshake) {
                    // A valid TLS record header with an incomplete body keeps
                    // the socket readable, but never completes the handshake.
                    tcp.write_all(b"\x16\x03\x03\x03\xe8").unwrap();
                    for _ in 0..100 {
                        if tcp.write_all(&[0]).is_err() {
                            break;
                        }
                        thread::sleep(Duration::from_millis(100));
                    }
                    continue;
                }
                let tls = acceptor.accept(tcp).unwrap();
                let mut socket = match tungstenite::accept(tls) {
                    Ok(socket) => socket,
                    Err(_) => continue, // A local recording limit can stop before upgrade.
                };
                assert!(
                    socket
                        .read()
                        .unwrap()
                        .into_text()
                        .unwrap()
                        .contains("subscribe")
                );
                if matches!(
                    mode,
                    ExchangeMode::Combined | ExchangeMode::CombinedDropFirst
                ) {
                    let request: Value =
                        serde_json::from_str(&socket.read().unwrap().into_text().unwrap()).unwrap();
                    assert_eq!(request["subscription"]["type"], "bbo");
                    for channel in ["l2Book", "bbo"] {
                        socket.send(Message::Text(serde_json::json!({"channel":"subscriptionResponse","data":{"method":"subscribe","subscription":{"type":channel,"coin":"BTC"}}}).to_string().into())).unwrap();
                    }
                }
                let Event::TextReceived { text } = common::book(100 + ordinal as u64, "100", "102")
                else {
                    unreachable!()
                };
                socket.send(Message::Text(text.into())).unwrap();
                if matches!(
                    mode,
                    ExchangeMode::Combined | ExchangeMode::CombinedDropFirst
                ) {
                    socket.send(Message::Text(serde_json::json!({"channel":"bbo","data":{"coin":"BTC","time":100+ordinal as u64,"bbo":[{"px":"101","sz":"1","n":1},{"px":"103","sz":"2","n":2}]}}).to_string().into())).unwrap();
                }
                if matches!(mode, ExchangeMode::DropAll)
                    || (matches!(
                        mode,
                        ExchangeMode::DropFirst | ExchangeMode::CombinedDropFirst
                    ) && ordinal == 0)
                {
                    socket.close(None).unwrap();
                    continue;
                }
                loop {
                    match socket.read() {
                        Ok(Message::Close(_)) => {
                            let _ = socket.flush();
                            break;
                        }
                        Err(_) => break,
                        _ => {}
                    }
                }
            }
        });
        Self {
            _serial: serial,
            temp,
            proxy,
            ca,
            stop,
            count,
            thread: Some(thread),
            combined: matches!(
                mode,
                ExchangeMode::Combined | ExchangeMode::CombinedDropFirst
            ),
        }
    }

    fn root(&self) -> PathBuf {
        self.temp.path().join("supervision")
    }

    fn spawn(&self, duration: u64, restarts: u32) -> Child {
        self.spawn_with_budget(duration, restarts, 65536, 1048576)
    }

    fn spawn_with_budget(
        &self,
        duration: u64,
        restarts: u32,
        run_bytes: u64,
        total_bytes: u64,
    ) -> Child {
        let mut command = Command::new(env!("CARGO_BIN_EXE_giethoorn"));
        command
            .args(["supervise", "--output-dir"])
            .arg(self.root())
            .arg("--duration-secs")
            .arg(duration.to_string())
            .args([
                "--run-duration-secs",
                "2",
                "--max-reconnects",
                "0",
                "--sample-interval-secs",
                "1",
                "--max-segment-bytes",
                "700",
                "--shutdown-grace-secs",
                "1",
            ])
            .arg("--max-run-bytes")
            .arg(run_bytes.to_string())
            .arg("--max-total-recording-bytes")
            .arg(total_bytes.to_string())
            .arg("--max-restarts")
            .arg(restarts.to_string())
            .env("HTTPS_PROXY", &self.proxy)
            .env("https_proxy", &self.proxy)
            .env("ALL_PROXY", &self.proxy)
            .env("all_proxy", &self.proxy)
            .env("NO_PROXY", "")
            .env("no_proxy", "")
            .env("SSL_CERT_FILE", &self.ca)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        if self.combined {
            command.args([
                "--feed-profile",
                "combined",
                "--depth-stale-after-ms",
                "5000",
                "--bbo-stale-after-ms",
                "5000",
            ]);
        }
        command.spawn().unwrap()
    }
}

impl Drop for Harness {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

fn finish(mut child: Child) -> Output {
    let deadline = Instant::now() + Duration::from_secs(15);
    while child.try_wait().unwrap().is_none() {
        if Instant::now() > deadline {
            let _ = child.kill();
            let _ = child.wait();
            panic!("supervisor exceeded test deadline");
        }
        thread::sleep(Duration::from_millis(20));
    }
    child.wait_with_output().unwrap()
}

fn summary(h: &Harness, output: &Output) -> Value {
    let value: Value = serde_json::from_slice(&output.stdout)
        .unwrap_or_else(|e| panic!("{e}: {}", String::from_utf8_lossy(&output.stderr)));
    let saved: Value =
        serde_json::from_slice(&fs::read(h.root().join("summary.json")).unwrap()).unwrap();
    assert_eq!(value, saved);
    value
}

fn events(root: &Path) -> Vec<Value> {
    fs::read_to_string(root.join("events.jsonl"))
        .unwrap_or_default()
        .lines()
        .filter_map(|line| serde_json::from_str(line).ok())
        .collect()
}

fn wait_for_snapshot(h: &Harness, child: &mut Child) -> u32 {
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        let pid = events(&h.root())
            .iter()
            .find(|e| e["kind"] == "child_started")
            .and_then(|e| e["data"]["pid"].as_u64());
        let session = h.root().join("run-000001/session");
        if let (Some(pid), Ok(entries)) = (pid, fs::read_dir(&session)) {
            for entry in entries.flatten() {
                if !entry.file_name().to_string_lossy().starts_with("segment-") {
                    continue;
                }
                let raw = fs::read_to_string(entry.path()).unwrap_or_default();
                if raw
                    .lines()
                    .filter_map(|line| serde_json::from_str::<Record>(line).ok())
                    .any(|r| match r.event {
                        Event::TextReceived { text } if h.combined => {
                            serde_json::from_str::<Value>(&text)
                                .is_ok_and(|v| v["channel"] == "bbo")
                        }
                        Event::TextReceived { .. } => true,
                        _ => false,
                    })
                {
                    return pid as u32;
                }
            }
        }
        if Instant::now() > deadline || child.try_wait().unwrap().is_some() {
            let _ = child.kill();
            let _ = child.wait();
            panic!("supervised child did not record a snapshot");
        }
        thread::sleep(Duration::from_millis(10));
    }
}

#[test]
fn planned_runs_are_validated_and_collected_in_new_directories() {
    let h = Harness::new(ExchangeMode::Normal);
    let output = finish(h.spawn(8, 1));
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let report = summary(&h, &output);
    assert_eq!(report["status"], "completed");
    assert_eq!(report["restarts"], 0);
    assert!(report["started_runs"].as_u64().unwrap() >= 2);
    assert!(report["validated_snapshots"].as_u64().unwrap() >= 2);
    assert!(report["peak_sampled_rss_bytes"].as_u64().unwrap() > 0);
    for run in report["runs"].as_array().unwrap() {
        assert_eq!(run["comparison"], "exact");
        assert_eq!(run["finalized"], true);
    }
}

#[test]
fn combined_profiles_survive_handovers_and_audit_the_recorded_policy() {
    let h = Harness::new(ExchangeMode::Combined);
    let output = finish(h.spawn(6, 1));
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let report = summary(&h, &output);
    assert_eq!(report["status"], "completed");
    assert!(report["started_runs"].as_u64().unwrap() >= 2);
    let audit = audit_supervision(&h.root()).unwrap();
    assert!(audit.full_window_completed);
    assert_eq!(
        audit.feed_policy.unwrap().profile,
        giethoorn::event::FeedProfile::Combined
    );
    let config_path = h.root().join("configuration.json");
    let mut config: Value = serde_json::from_slice(&fs::read(&config_path).unwrap()).unwrap();
    config["feed_policy"]["bbo_stale_after_ms"] = serde_json::json!(4000);
    save_value(&config_path, &config);
    assert!(audit_supervision(&h.root()).is_err());
}

#[test]
fn combined_profile_network_failure_restarts_after_exact_validation() {
    let h = Harness::new(ExchangeMode::CombinedDropFirst);
    let output = finish(h.spawn(6, 1));
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let report = summary(&h, &output);
    assert_eq!(report["status"], "completed_with_restarts");
    assert_eq!(report["runs"][0]["exit_code"], 10);
    assert_eq!(report["runs"][0]["comparison"], "exact");
    let audit = audit_supervision(&h.root()).unwrap();
    assert_eq!(audit.restarts, 1);
    assert!(audit.full_window_completed);
}

#[test]
fn killed_combined_child_recovers_observations_and_freshness_as_a_prefix() {
    let h = Harness::new(ExchangeMode::Combined);
    let mut child = h.spawn(6, 1);
    let pid = wait_for_snapshot(&h, &mut child);
    nix::sys::signal::kill(
        nix::unistd::Pid::from_raw(pid as i32),
        nix::sys::signal::Signal::SIGKILL,
    )
    .unwrap();
    let output = finish(child);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let report = summary(&h, &output);
    assert_eq!(report["status"], "completed_with_restarts");
    assert_eq!(report["runs"][0]["signal"], 9);
    assert_eq!(report["runs"][0]["comparison"], "live_prefix");
    assert_eq!(report["runs"][0]["finalized"], false);
    let audit = audit_supervision(&h.root()).unwrap();
    assert_eq!(audit.runs[0].comparison, "live_prefix");
    assert!(audit.full_window_completed);
}

#[test]
fn transient_disconnect_restarts_after_validation_and_ends_healthy() {
    let h = Harness::new(ExchangeMode::DropFirst);
    let output = finish(h.spawn(6, 1));
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let report = summary(&h, &output);
    assert_eq!(report["status"], "completed_with_restarts");
    assert_eq!(report["restarts"], 1);
    assert_eq!(report["runs"][0]["exit_code"], 10);
    assert_eq!(report["runs"][0]["comparison"], "exact");
    assert_eq!(
        report["runs"].as_array().unwrap().last().unwrap()["exit_code"],
        0
    );
    let audit = audit_supervision(&h.root()).unwrap();
    assert_eq!(audit.restarts, 1);
    assert!(audit.full_window_completed);
}

#[test]
fn killed_child_recovers_a_prefix_before_a_fresh_restart() {
    let h = Harness::new(ExchangeMode::Normal);
    let mut child = h.spawn(6, 1);
    let pid = wait_for_snapshot(&h, &mut child);
    nix::sys::signal::kill(
        nix::unistd::Pid::from_raw(pid as i32),
        nix::sys::signal::Signal::SIGKILL,
    )
    .unwrap();
    let output = finish(child);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let report = summary(&h, &output);
    assert_eq!(report["status"], "completed_with_restarts");
    assert_eq!(report["restarts"], 1);
    assert_eq!(report["runs"][0]["signal"], 9);
    assert_eq!(report["runs"][0]["comparison"], "live_prefix");
    assert_eq!(report["runs"][0]["finalized"], false);
    assert!(report["started_runs"].as_u64().unwrap() >= 2);
    assert_eq!(
        audit_supervision(&h.root()).unwrap().runs[0].comparison,
        "live_prefix"
    );
}

#[test]
fn permanent_proxy_denial_is_not_retried_by_collector_or_supervisor() {
    let h = Harness::new(ExchangeMode::Deny);
    let output = finish(h.spawn(8, 3));
    assert!(!output.status.success());
    let report = summary(&h, &output);
    assert_eq!(report["status"], "failed");
    assert_eq!(report["restarts"], 0);
    assert_eq!(report["started_runs"], 1);
    assert_eq!(h.count.load(Ordering::Relaxed), 1);
    let audit = audit_supervision(&h.root()).unwrap();
    assert_eq!(
        audit.supervisor_status,
        giethoorn::supervisor::SupervisorStatus::Failed
    );
    assert!(!audit.full_window_completed);
    // Coherent-looking exit metadata cannot turn zero usable data into success.
    let mut falsified = report.clone();
    falsified["runs"][0]["exit_code"] = serde_json::json!(0);
    save_value(&h.root().join("summary.json"), &falsified);
    let event_path = h.root().join("events.jsonl");
    let mut controls = events(&h.root());
    for control in &mut controls {
        if control["kind"] == "child_exited" {
            control["data"]["exit_code"] = serde_json::json!(0);
        }
    }
    fs::write(
        event_path,
        controls
            .iter()
            .map(|v| format!("{v}\n"))
            .collect::<String>(),
    )
    .unwrap();
    assert!(audit_supervision(&h.root()).is_err());
}

#[test]
fn repeated_network_failures_exhaust_the_restart_budget_and_do_not_claim_success() {
    let h = Harness::new(ExchangeMode::DropAll);
    let output = finish(h.spawn(10, 1));
    assert!(!output.status.success());
    let report = summary(&h, &output);
    assert_eq!(report["status"], "failed");
    assert_eq!(report["restarts"], 1);
    assert_eq!(report["started_runs"], 2);
    assert!(
        report["reason"]
            .as_str()
            .unwrap()
            .contains("restart budget exhausted")
    );
}

#[test]
fn sigterm_stops_the_owned_child_gracefully_and_finalizes_its_archive() {
    let h = Harness::new(ExchangeMode::Normal);
    let mut child = h.spawn(30, 1);
    wait_for_snapshot(&h, &mut child);
    nix::sys::signal::kill(
        nix::unistd::Pid::from_raw(child.id() as i32),
        nix::sys::signal::Signal::SIGTERM,
    )
    .unwrap();
    let output = finish(child);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let report = summary(&h, &output);
    assert_eq!(report["status"], "interrupted");
    assert_eq!(report["runs"][0]["finalized"], true);
    let archive = h.root().join("run-000001/session");
    assert_eq!(
        replay(&archive, false, |_| Ok(()))
            .unwrap()
            .end_reason
            .as_deref(),
        Some("interrupted")
    );
}

#[test]
fn checksum_corruption_stops_supervision_instead_of_restarting() {
    let h = Harness::new(ExchangeMode::Normal);
    let mut child = h.spawn(8, 3);
    let pid = wait_for_snapshot(&h, &mut child);
    let session = h.root().join("run-000001/session");
    let index: Vec<Value> = fs::read_to_string(session.join("index.jsonl"))
        .unwrap()
        .lines()
        .map(|s| serde_json::from_str(s).unwrap())
        .collect();
    let name = index.iter().find(|e| e["kind"] == "segment").unwrap()["file"]
        .as_str()
        .unwrap();
    let file = session.join(name);
    let original = fs::read_to_string(&file).unwrap();
    let mut records: Vec<Record> = original
        .lines()
        .map(|s| serde_json::from_str(s).unwrap())
        .collect();
    records[0].local_time_ns -= 1;
    let altered = common::encode(&records);
    assert_eq!(altered.len(), original.len());
    fs::write(file, altered).unwrap();
    nix::sys::signal::kill(
        nix::unistd::Pid::from_raw(pid as i32),
        nix::sys::signal::Signal::SIGKILL,
    )
    .unwrap();
    let output = finish(child);
    assert!(!output.status.success());
    let report = summary(&h, &output);
    assert_eq!(report["status"], "failed");
    assert_eq!(report["restarts"], 0);
    assert_eq!(report["started_runs"], 1);
    assert!(
        report["reason"]
            .as_str()
            .unwrap()
            .contains("checksum mismatch")
    );
    assert!(report["recording_bytes"].as_u64().unwrap() > 0);
}

#[test]
fn crash_comparison_accepts_a_live_prefix_but_rejects_divergent_or_extra_bytes() {
    let _serial = process_test_guard();
    let temp = tempfile::tempdir().unwrap();
    let archive = temp.path().join("session");
    let mut writer = Journal::create_segmented(
        &archive,
        SegmentLimits {
            max_segment_bytes: 600,
            max_session_bytes: 65536,
            min_free_bytes: 0,
        },
    )
    .unwrap();
    for record in common::session().into_iter().take(4) {
        writer.append(record.connection_id, record.event).unwrap();
    }
    drop(writer);
    let mut quotes = Vec::new();
    replay(&archive, true, |q| {
        serde_json::to_writer(&mut quotes, q)?;
        quotes.push(b'\n');
        Ok(())
    })
    .unwrap();
    let live = temp.path().join("live.jsonl");
    fs::write(&live, &quotes[..quotes.len() / 2]).unwrap();
    assert_eq!(
        compare_quotes(&archive, &live, true).unwrap(),
        "live_prefix"
    );
    let mut wrong = quotes.clone();
    wrong[0] = b'!';
    fs::write(&live, wrong).unwrap();
    assert!(compare_quotes(&archive, &live, true).is_err());
    quotes.push(b'!');
    fs::write(&live, quotes).unwrap();
    assert!(compare_quotes(&archive, &live, true).is_err());
}

#[test]
fn stalled_handshake_is_bounded_by_the_watchdog_and_is_not_restarted() {
    let h = Harness::new(ExchangeMode::StallHandshake);
    let output = finish(h.spawn(10, 3));
    assert!(!output.status.success());
    let report = summary(&h, &output);
    assert_eq!(report["status"], "failed");
    assert_eq!(report["started_runs"], 1);
    assert_eq!(report["restarts"], 0);
    assert!(
        report["reason"].as_str().unwrap().contains("deadline"),
        "{report}"
    );
}

#[test]
fn killed_supervisor_does_not_leave_an_orphaned_collector_running() {
    // Adopt/reap the intentionally orphaned process in this test runner. Some
    // container PID-1 implementations do not reap adopted grandchildren.
    nix::sys::prctl::set_child_subreaper(true).unwrap();
    let h = Harness::new(ExchangeMode::Normal);
    let mut child = h.spawn(30, 1);
    let collector_pid = wait_for_snapshot(&h, &mut child);
    child.kill().unwrap();
    child.wait().unwrap();
    let archive = h.root().join("run-000001/session");
    let deadline = Instant::now() + Duration::from_secs(5);
    let report = loop {
        match replay(&archive, false, |_| Ok(())) {
            Ok(report) => break report,
            Err(_) => {
                assert!(
                    Instant::now() < deadline,
                    "orphan collector did not release/finalize its archive"
                );
                thread::sleep(Duration::from_millis(20));
            }
        }
    };
    assert_eq!(report.end_reason.as_deref(), Some("interrupted"));
    assert!(!h.root().join("summary.json").exists());
    assert!(audit_supervision(&h.root()).is_err());
    let reap_deadline = Instant::now() + Duration::from_secs(3);
    while let nix::sys::wait::WaitStatus::StillAlive = nix::sys::wait::waitpid(
        nix::unistd::Pid::from_raw(collector_pid as i32),
        Some(nix::sys::wait::WaitPidFlag::WNOHANG),
    )
    .unwrap()
    {
        assert!(
            Instant::now() < reap_deadline,
            "orphan did not exit for reaping"
        );
        thread::sleep(Duration::from_millis(10));
    }
}

fn save_value(path: &Path, value: &Value) {
    fs::write(
        path,
        format!("{}\n", serde_json::to_string_pretty(value).unwrap()),
    )
    .unwrap();
}

#[test]
fn supervision_audit_recomputes_saved_counts_and_rejects_altered_metadata_and_binary() {
    let h = Harness::new(ExchangeMode::Normal);
    let output = finish(h.spawn(4, 1));
    assert!(output.status.success());
    let report = summary(&h, &output);
    let audit = audit_supervision(&h.root()).unwrap();
    assert_eq!(audit.integrity, "verified");
    assert!(audit.full_window_completed);
    assert_eq!(
        audit.snapshots,
        report["validated_snapshots"].as_u64().unwrap()
    );
    assert_eq!(
        audit.recording_bytes,
        report["recording_bytes"].as_u64().unwrap()
    );
    assert!(audit.artifact_bytes > audit.recording_bytes);
    let result = Command::new(env!("CARGO_BIN_EXE_giethoorn"))
        .args(["audit-supervision", "--input"])
        .arg(h.root())
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let cli: Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(cli, serde_json::to_value(&audit).unwrap());

    let summary_path = h.root().join("summary.json");
    let original_summary = fs::read(&summary_path).unwrap();
    let mut altered = report.clone();
    altered["validated_snapshots"] = serde_json::json!(audit.snapshots + 1);
    save_value(&summary_path, &altered);
    assert!(audit_supervision(&h.root()).is_err());
    fs::write(&summary_path, &original_summary).unwrap();
    let config_path = h.root().join("configuration.json");
    let original_config = fs::read(&config_path).unwrap();
    let mut wrong_market: Value = serde_json::from_slice(&original_config).unwrap();
    wrong_market["coin"] = serde_json::json!("ETH");
    save_value(&config_path, &wrong_market);
    assert!(audit_supervision(&h.root()).is_err());
    fs::write(config_path, original_config).unwrap();

    let control_path = h.root().join("events.jsonl");
    let original = fs::read(&control_path).unwrap();
    let mut controls: Vec<Value> = String::from_utf8(original.clone())
        .unwrap()
        .lines()
        .map(|s| serde_json::from_str(s).unwrap())
        .collect();
    controls[0]["kind"] = serde_json::json!("failed");
    fs::write(
        &control_path,
        controls
            .iter()
            .map(|v| format!("{v}\n"))
            .collect::<String>(),
    )
    .unwrap();
    assert!(audit_supervision(&h.root()).is_err());
    fs::write(&control_path, original).unwrap();

    let cache = h.root().join("run-000001/inspection.json");
    let original = fs::read(&cache).unwrap();
    let mut value: Value = serde_json::from_slice(&original).unwrap();
    value["two_sided_snapshots"] = serde_json::json!(999999);
    save_value(&cache, &value);
    assert!(audit_supervision(&h.root()).is_err());
    fs::write(&cache, original).unwrap();

    let resources = h.root().join("resources.jsonl");
    let original = fs::read(&resources).unwrap();
    let mut samples: Vec<Value> = String::from_utf8(original.clone())
        .unwrap()
        .lines()
        .map(|s| serde_json::from_str(s).unwrap())
        .collect();
    samples[0]["rss_bytes"] = serde_json::json!(audit.peak_sampled_rss_bytes + 1);
    fs::write(
        &resources,
        samples.iter().map(|v| format!("{v}\n")).collect::<String>(),
    )
    .unwrap();
    assert!(audit_supervision(&h.root()).is_err());
    fs::write(&resources, original).unwrap();

    let binary = h.root().join("collector.bin");
    let original = fs::read(&binary).unwrap();
    let mut altered = original.clone();
    altered[0] ^= 1;
    fs::write(&binary, altered).unwrap();
    assert!(audit_supervision(&h.root()).is_err());
    fs::write(&binary, original).unwrap();
    let extra = h.root().join("run-999999");
    fs::create_dir(&extra).unwrap();
    assert!(audit_supervision(&h.root()).is_err());
    fs::remove_dir(extra).unwrap();
    fs::remove_file(&summary_path).unwrap();
    assert!(audit_supervision(&h.root()).is_err());
    fs::write(summary_path, original_summary).unwrap();
    audit_supervision(&h.root()).unwrap();
}

#[test]
fn supervision_audit_refuses_active_writers_but_can_verify_an_interrupted_final_report() {
    let h = Harness::new(ExchangeMode::Normal);
    let mut child = h.spawn(30, 1);
    wait_for_snapshot(&h, &mut child);
    assert!(format!("{:#}", audit_supervision(&h.root()).unwrap_err()).contains("active"));
    nix::sys::signal::kill(
        nix::unistd::Pid::from_raw(child.id() as i32),
        nix::sys::signal::Signal::SIGTERM,
    )
    .unwrap();
    let output = finish(child);
    assert!(output.status.success());
    let audit = audit_supervision(&h.root()).unwrap();
    assert_eq!(
        audit.supervisor_status,
        giethoorn::supervisor::SupervisorStatus::Interrupted
    );
    assert!(!audit.full_window_completed);
}

#[test]
fn local_recording_budget_failure_is_fatal_and_never_restarted() {
    let h = Harness::new(ExchangeMode::Normal);
    let output = finish(h.spawn_with_budget(8, 3, 4096, 1048576));
    assert!(!output.status.success());
    let report = summary(&h, &output);
    assert_eq!(report["status"], "failed");
    assert_eq!(report["started_runs"], 1);
    assert_eq!(report["restarts"], 0);
    assert_eq!(report["runs"][0]["exit_code"], 11);
    assert!(report["recording_bytes"].as_u64().unwrap() <= 4096);
}

#[test]
fn whole_supervision_budget_stops_before_starting_a_child_with_insufficient_allowance() {
    let h = Harness::new(ExchangeMode::Normal);
    let sizing = finish(h.spawn(3, 0));
    assert!(sizing.status.success());
    let used = summary(&h, &sizing)["recording_bytes"].as_u64().unwrap();
    fs::rename(h.root(), h.temp.path().join("sizing")).unwrap();
    let limit = used + 1800;
    let output = finish(h.spawn_with_budget(8, 0, 65536, limit));
    assert!(!output.status.success());
    let report = summary(&h, &output);
    assert_eq!(report["status"], "budget_exhausted");
    assert_eq!(report["started_runs"], 1);
    assert!(report["recording_bytes"].as_u64().unwrap() <= limit);
    let audit = audit_supervision(&h.root()).unwrap();
    assert_eq!(
        audit.supervisor_status,
        giethoorn::supervisor::SupervisorStatus::BudgetExhausted
    );
    assert!(!audit.full_window_completed);
}

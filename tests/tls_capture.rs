//! Exercise the actual CLI transport through HTTP CONNECT and verified TLS.
//! SSL_CERT_FILE configures OpenSSL on Linux; other native-tls backends use their
//! platform trust stores. No external exchange traffic or persistent test key.
#![cfg(target_os = "linux")]

mod common;

use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::process::Command;
use std::thread;
use std::time::{Duration, Instant};

use giethoorn::event::{Event, Record};
use giethoorn::journal::replay;
use native_tls::{Identity, TlsAcceptor};
use rcgen::generate_simple_self_signed;
use tungstenite::Message;

#[derive(Clone, Copy, PartialEq, Eq)]
enum Scenario {
    Single,
    Segmented,
    KillSegmented,
}

fn observed_records(path: &std::path::Path) -> Vec<Record> {
    let raw = if path.is_dir() {
        let mut files: Vec<_> = std::fs::read_dir(path)
            .unwrap()
            .map(|e| e.unwrap().path())
            .filter(|p| {
                p.file_name()
                    .unwrap()
                    .to_string_lossy()
                    .starts_with("segment-")
            })
            .collect();
        files.sort();
        files
            .into_iter()
            .map(|p| std::fs::read_to_string(p).unwrap())
            .collect::<String>()
    } else if path.is_file() {
        std::fs::read_to_string(path).unwrap()
    } else {
        return Vec::new();
    };
    // Diagnostic polling only: the product reader never skips corrupt lines.
    raw.lines()
        .filter_map(|line| serde_json::from_str(line).ok())
        .collect()
}

fn run_tls_capture(trust_test_certificate: bool, certificate_hostname: &str, scenario: Scenario) {
    let segmented = scenario != Scenario::Single;
    let directory = tempfile::tempdir().unwrap();
    let journal = directory.path().join("capture.jsonl");
    let certificate = generate_simple_self_signed(vec![certificate_hostname.to_string()]).unwrap();
    let pem = certificate.cert.pem();
    let ca_path = directory.path().join("test-root.pem");
    std::fs::write(&ca_path, &pem).unwrap();
    let identity = Identity::from_pkcs8(
        pem.as_bytes(),
        certificate.signing_key.serialize_pem().as_bytes(),
    )
    .unwrap();
    let acceptor = TlsAcceptor::new(identity).unwrap();
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    listener.set_nonblocking(true).unwrap();
    let proxy_url = format!("http://{}", listener.local_addr().unwrap());
    let expect_success = trust_test_certificate && certificate_hostname == "api.hyperliquid.xyz";
    let observed_journal = journal.clone();
    let exchange = thread::spawn(move || {
        let mut tcp = accept_with_deadline(listener);
        tcp.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
        tcp.set_write_timeout(Some(Duration::from_secs(3))).unwrap();
        let mut request = Vec::new();
        while !request.ends_with(b"\r\n\r\n") {
            assert!(request.len() < 4096);
            let mut byte = [0];
            tcp.read_exact(&mut byte).unwrap();
            request.push(byte[0]);
        }
        assert!(
            String::from_utf8(request)
                .unwrap()
                .starts_with("CONNECT api.hyperliquid.xyz:443 HTTP/1.1\r\n")
        );
        tcp.write_all(b"HTTP/1.1 200 Connection established\r\n\r\n")
            .unwrap();
        let accepted = acceptor.accept(tcp);
        if !expect_success {
            assert!(
                accepted.is_err(),
                "untrusted or wrong-host certificate was accepted"
            );
            return;
        }
        let mut socket = tungstenite::accept(accepted.unwrap()).unwrap();
        let subscription = socket.read().unwrap().into_text().unwrap();
        assert_eq!(
            serde_json::from_str::<serde_json::Value>(&subscription).unwrap()["method"],
            "subscribe"
        );
        let records = observed_records(&observed_journal);
        assert!(
            records
                .iter()
                .any(|r| matches!(r.event, Event::UpgradeResponse { status: 101, .. }))
        );
        let Event::TextReceived { text } = common::book(100, "100.10", "100.30") else {
            unreachable!()
        };
        socket.send(Message::Text(text.into())).unwrap();
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
    });
    let mut command = Command::new(env!("CARGO_BIN_EXE_giethoorn"));
    command
        .args([
            if segmented { "collect" } else { "capture" },
            "--coin",
            "BTC",
            "--network",
            "mainnet",
            "--duration-secs",
            if scenario == Scenario::KillSegmented {
                "60"
            } else {
                "1"
            },
            "--max-reconnects",
            "0",
            if segmented {
                "--output-dir"
            } else {
                "--output"
            },
        ])
        .arg(&journal)
        // Child-only overrides: never mutate the test runner's environment or
        // use the cloud egress proxy for this loopback integration test.
        .env("https_proxy", &proxy_url)
        .env("HTTPS_PROXY", &proxy_url)
        .env("ALL_PROXY", &proxy_url)
        .env("all_proxy", &proxy_url)
        .env("NO_PROXY", "")
        .env("no_proxy", "");
    if segmented {
        command.args(["--max-segment-bytes", "700", "--max-session-bytes", "65536"]);
    }
    if trust_test_certificate {
        command.env("SSL_CERT_FILE", &ca_path);
    }
    let mut child = command
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .unwrap();
    if scenario == Scenario::KillSegmented {
        let deadline = Instant::now() + Duration::from_secs(5);
        while !observed_records(&journal)
            .iter()
            .any(|r| matches!(r.event, Event::TextReceived { .. }))
        {
            if Instant::now() >= deadline {
                let _ = child.kill();
                let _ = child.wait();
                panic!("child did not record the test snapshot before deadline");
            }
            thread::sleep(Duration::from_millis(10));
        }
        child.kill().unwrap();
    }
    let output = child.wait_with_output().unwrap();
    exchange.join().unwrap();
    if scenario == Scenario::KillSegmented {
        use std::os::unix::process::ExitStatusExt;
        assert_eq!(output.status.signal(), Some(9));
        assert!(replay(&journal, false, |_| Ok(())).is_err());
        let recovered = replay(&journal, true, |_| Ok(())).unwrap();
        assert_eq!(recovered.snapshots, 1);
        assert!(!recovered.complete);
        let diagnostic = giethoorn::inspect::inspect(&journal, true).unwrap();
        assert!(diagnostic.storage.sealed_segments > 0);
        assert!(diagnostic.storage.has_unsealed_tail);
        return;
    }
    if expect_success {
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        let mut replayed = Vec::new();
        let report = replay(&journal, false, |quote| {
            serde_json::to_writer(&mut replayed, quote)?;
            replayed.push(b'\n');
            Ok(())
        })
        .unwrap();
        assert_eq!(output.stdout, replayed);
        assert_eq!(report.snapshots, 1);
        if segmented {
            let storage = giethoorn::inspect::inspect(&journal, false)
                .unwrap()
                .storage;
            assert!(storage.finalized && storage.sealed_segments >= 2);
            assert_eq!(report.connections, 1);
        }
        assert_eq!(
            serde_json::from_slice::<serde_json::Value>(&output.stderr).unwrap(),
            serde_json::to_value(report).unwrap()
        );
    } else {
        assert!(!output.status.success());
        let diagnostic = String::from_utf8_lossy(&output.stderr);
        assert!(
            diagnostic.contains("verified TLS handshake failed"),
            "{diagnostic}"
        );
        assert!(
            diagnostic.contains("certificate verify failed"),
            "{diagnostic}"
        );
        let report = replay(&journal, false, |_| Ok(())).unwrap();
        assert_eq!(report.snapshots, 0);
        assert_eq!(report.end_reason.as_deref(), Some("failed"));
    }
}

fn accept_with_deadline(listener: TcpListener) -> TcpStream {
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        match listener.accept() {
            Ok((tcp, _)) => return tcp,
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                assert!(
                    Instant::now() < deadline,
                    "CLI never connected to local proxy"
                );
                thread::sleep(Duration::from_millis(10));
            }
            Err(error) => panic!("local proxy accept failed: {error}"),
        }
    }
}

#[test]
fn production_cli_records_and_replays_through_proxy_and_verified_tls() {
    run_tls_capture(true, "api.hyperliquid.xyz", Scenario::Single);
}

#[test]
fn production_cli_rejects_an_untrusted_tls_certificate() {
    run_tls_capture(false, "api.hyperliquid.xyz", Scenario::Single);
}

#[test]
fn production_cli_rejects_a_trusted_certificate_for_the_wrong_hostname() {
    run_tls_capture(true, "wrong-host.example", Scenario::Single);
}

#[test]
fn production_cli_rotates_on_one_verified_tls_connection_and_replays_identically() {
    run_tls_capture(true, "api.hyperliquid.xyz", Scenario::Segmented);
}

#[test]
fn killed_cli_releases_the_lock_and_recovers_sealed_segments_plus_the_live_tail() {
    run_tls_capture(true, "api.hyperliquid.xyz", Scenario::KillSegmented);
}

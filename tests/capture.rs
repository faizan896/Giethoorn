mod common;

use std::io::Write;
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::sync::{Arc, atomic::AtomicBool};
use std::thread;
use std::time::Duration;

use anyhow::Result;
use giethoorn::capture::{CaptureOptions, capture_with_connector};
use giethoorn::event::{Event, Network, Record};
use giethoorn::journal::{JournalLimits, JournalMode, replay};
use giethoorn::transport::{Socket, set_io_timeout};
use tungstenite::stream::MaybeTlsStream;
use tungstenite::{Message, WebSocket};

fn options(path: std::path::PathBuf) -> CaptureOptions {
    CaptureOptions {
        coin: "BTC".into(),
        network: Network::Mainnet,
        output: path,
        duration: Duration::from_millis(200),
        max_reconnects: 0,
        stale_after: Duration::from_secs(2),
        journal_mode: JournalMode::SingleFile(JournalLimits::UNLIMITED),
        feed_policy: None,
    }
}

fn connector(address: SocketAddr, record: &mut dyn FnMut(Event) -> Result<()>) -> Result<Socket> {
    let tcp = TcpStream::connect(address)?;
    tcp.set_read_timeout(Some(Duration::from_secs(2)))?;
    tcp.set_write_timeout(Some(Duration::from_secs(2)))?;
    record(Event::TcpConnected)?;
    let (socket, _) =
        tungstenite::client(format!("ws://{address}/ws"), MaybeTlsStream::Plain(tcp))?;
    set_io_timeout(&socket, Duration::from_millis(20))?;
    Ok(socket)
}

fn server(listener: &TcpListener) -> WebSocket<TcpStream> {
    let (tcp, _) = listener.accept().unwrap();
    tcp.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
    tcp.set_write_timeout(Some(Duration::from_secs(3))).unwrap();
    tungstenite::accept(tcp).unwrap()
}

fn read_subscription(socket: &mut WebSocket<TcpStream>) {
    let message = socket.read().unwrap().into_text().unwrap();
    assert_eq!(
        serde_json::from_str::<serde_json::Value>(&message).unwrap(),
        serde_json::json!({"method":"subscribe","subscription":{"type":"l2Book","coin":"BTC"}})
    );
}

fn send_book(socket: &mut WebSocket<TcpStream>, time: u64, bid: &str, ask: &str) {
    let Event::TextReceived { text } = common::book(time, bid, ask) else {
        unreachable!()
    };
    socket.send(Message::Text(text.into())).unwrap();
}

fn wait_until_closed(socket: &mut WebSocket<TcpStream>) {
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

#[test]
fn real_websocket_capture_and_replay_produce_identical_bytes() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("capture.jsonl");
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let observed_path = path.clone();
    let exchange = thread::spawn(move || {
        let mut socket = server(&listener);
        read_subscription(&mut socket);
        // Sending the subscription must happen AFTER its journal append.
        let records: Vec<Record> = std::fs::read_to_string(observed_path)
            .unwrap()
            .lines()
            .map(|line| serde_json::from_str(line).unwrap())
            .collect();
        assert!(
            records
                .iter()
                .any(|record| matches!(record.event, Event::TextSent { .. }))
        );
        send_book(&mut socket, 100, "100.1", "100.2");
        send_book(&mut socket, 101, "100.2", "100.4");
        wait_until_closed(&mut socket);
    });
    let mut live = Vec::new();
    let report = capture_with_connector(
        &options(path.clone()),
        &mut live,
        Arc::new(AtomicBool::new(false)),
        |_, _, record| connector(address, record),
    )
    .unwrap();
    exchange.join().unwrap();
    let mut replayed = Vec::new();
    let replay_report = replay(&path, false, |quote| {
        serde_json::to_writer(&mut replayed, quote)?;
        replayed.push(b'\n');
        Ok(())
    })
    .unwrap();
    assert_eq!(live, replayed);
    assert_eq!(report, replay_report);
    assert_eq!(report.snapshots, 2);
    assert_eq!(report.end_reason.as_deref(), Some("duration_elapsed"));
}

#[test]
fn server_ping_is_logged_before_pong_and_session_remains_replayable() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("capture.jsonl");
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let exchange = thread::spawn(move || {
        let mut socket = server(&listener);
        read_subscription(&mut socket);
        socket
            .send(Message::Ping(b"probe".to_vec().into()))
            .unwrap();
        assert_eq!(
            socket.read().unwrap(),
            Message::Pong(b"probe".to_vec().into())
        );
        send_book(&mut socket, 100, "1", "2");
        wait_until_closed(&mut socket);
    });
    capture_with_connector(
        &options(path.clone()),
        Vec::new(),
        Arc::new(AtomicBool::new(false)),
        |_, _, record| connector(address, record),
    )
    .unwrap();
    exchange.join().unwrap();
    let records: Vec<Record> = std::fs::read_to_string(&path)
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect();
    let ping = records
        .iter()
        .position(|r| matches!(&r.event, Event::ControlReceived { kind, .. } if kind == "ping"))
        .unwrap();
    assert!(
        matches!(&records[ping + 1].event, Event::ControlSent { kind, payload_hex } if kind == "pong" && payload_hex == "70726f6265")
    );
    assert_eq!(replay(&path, false, |_| Ok(())).unwrap().snapshots, 1);
}

#[test]
fn disconnect_reconnects_and_accepts_a_fresh_snapshot_on_new_connection() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("capture.jsonl");
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let exchange = thread::spawn(move || {
        let mut first = server(&listener);
        read_subscription(&mut first);
        send_book(&mut first, 200, "100", "102");
        first.close(None).unwrap();
        drop(first);
        let mut second = server(&listener);
        read_subscription(&mut second);
        // Earlier exchange timestamp is allowed only after the connection reset.
        send_book(&mut second, 100, "98", "100");
        wait_until_closed(&mut second);
    });
    let mut config = options(path.clone());
    config.duration = Duration::from_millis(1500);
    config.max_reconnects = 1;
    let mut live = Vec::new();
    let report = capture_with_connector(
        &config,
        &mut live,
        Arc::new(AtomicBool::new(false)),
        |_, _, record| connector(address, record),
    )
    .unwrap();
    exchange.join().unwrap();
    assert_eq!(report.connections, 2);
    assert_eq!(report.snapshots, 2);
    assert_eq!(
        report.last_quote.as_ref().unwrap().mid.as_deref(),
        Some("99")
    );
    assert_eq!(report, replay(&path, false, |_| Ok(())).unwrap());
}

#[test]
fn no_market_data_is_a_failure_not_a_successful_smoke_test() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("capture.jsonl");
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let exchange = thread::spawn(move || {
        let mut socket = server(&listener);
        read_subscription(&mut socket);
        wait_until_closed(&mut socket);
    });
    let error = capture_with_connector(
        &options(path.clone()),
        Vec::new(),
        Arc::new(AtomicBool::new(false)),
        |_, _, record| connector(address, record),
    )
    .unwrap_err();
    exchange.join().unwrap();
    assert!(error.to_string().contains("no usable two-sided book"));
    let report = replay(&path, false, |_| Ok(())).unwrap();
    assert_eq!(report.snapshots, 0);
    assert_eq!(report.end_reason.as_deref(), Some("failed"));
}

#[test]
fn stalled_book_is_detected_even_when_socket_stays_open() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("capture.jsonl");
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let exchange = thread::spawn(move || {
        let mut socket = server(&listener);
        read_subscription(&mut socket);
        wait_until_closed(&mut socket);
    });
    let mut config = options(path.clone());
    config.stale_after = Duration::from_millis(50);
    let error = capture_with_connector(
        &config,
        Vec::new(),
        Arc::new(AtomicBool::new(false)),
        |_, _, record| connector(address, record),
    )
    .unwrap_err();
    exchange.join().unwrap();
    assert!(format!("{error:#}").contains("stalled"));
    assert_eq!(
        replay(&path, false, |_| Ok(()))
            .unwrap()
            .end_reason
            .as_deref(),
        Some("failed")
    );
}

struct BrokenOutput;
impl Write for BrokenOutput {
    fn write(&mut self, _: &[u8]) -> std::io::Result<usize> {
        Err(std::io::Error::other("output unavailable"))
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

#[test]
fn local_recording_failure_stops_without_reconnecting_and_preserves_raw_input() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("capture.jsonl");
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let exchange = thread::spawn(move || {
        let mut socket = server(&listener);
        read_subscription(&mut socket);
        send_book(&mut socket, 100, "1", "2");
        wait_until_closed(&mut socket);
    });
    let mut attempts = 0;
    let mut config = options(path.clone());
    config.max_reconnects = 10;
    let error = capture_with_connector(
        &config,
        BrokenOutput,
        Arc::new(AtomicBool::new(false)),
        |_, _, record| {
            attempts += 1;
            connector(address, record)
        },
    )
    .unwrap_err();
    exchange.join().unwrap();
    assert!(format!("{error:#}").contains("output unavailable"));
    assert_eq!(attempts, 1);
    let recovered = replay(&path, true, |_| Ok(())).unwrap();
    assert!(!recovered.complete);
    assert_eq!(recovered.snapshots, 1);
}

#[test]
fn journal_budget_failure_happens_before_any_network_connection() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("capture.jsonl");
    let mut config = options(path.clone());
    config.journal_mode = JournalMode::SingleFile(JournalLimits {
        max_bytes: 1,
        min_free_bytes: 0,
    });
    let mut attempts = 0;
    let error = capture_with_connector(
        &config,
        Vec::new(),
        Arc::new(AtomicBool::new(false)),
        |_, _, _| {
            attempts += 1;
            anyhow::bail!("network must not be called")
        },
    )
    .unwrap_err();
    assert!(format!("{error:#}").contains("journal size limit reached"));
    assert_eq!(attempts, 0);
    assert_eq!(std::fs::metadata(path).unwrap().len(), 0);
}

#[test]
fn journal_budget_failure_during_streaming_stops_without_processing_unlogged_data() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("capture.jsonl");
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let exchange = thread::spawn(move || {
        let mut socket = server(&listener);
        read_subscription(&mut socket);
        let Event::TextReceived { text } = common::book(100, "1", "2") else {
            unreachable!()
        };
        let mut value: serde_json::Value = serde_json::from_str(&text).unwrap();
        value["data"]["additional_field"] = serde_json::json!("x".repeat(4096));
        socket
            .send(Message::Text(value.to_string().into()))
            .unwrap();
        wait_until_closed(&mut socket);
    });
    let mut config = options(path.clone());
    config.max_reconnects = 10;
    config.journal_mode = JournalMode::SingleFile(JournalLimits {
        max_bytes: 2000,
        min_free_bytes: 0,
    });
    let mut attempts = 0;
    let mut quotes = Vec::new();
    let error = capture_with_connector(
        &config,
        &mut quotes,
        Arc::new(AtomicBool::new(false)),
        |_, _, record| {
            attempts += 1;
            connector(address, record)
        },
    )
    .unwrap_err();
    exchange.join().unwrap();
    assert!(format!("{error:#}").contains("journal size limit reached"));
    assert_eq!(attempts, 1);
    assert!(quotes.is_empty());
    assert!(std::fs::metadata(&path).unwrap().len() <= 2000);
    let prefix = replay(&path, true, |_| Ok(())).unwrap();
    assert!(!prefix.complete);
    assert_eq!(prefix.snapshots, 0);
}

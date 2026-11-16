mod common;

use anyhow::Result;
use giethoorn::capture::{CaptureOptions, capture_with_connector, failure_exit_code};
use giethoorn::event::{Event, FeedKind, FeedPolicy, FeedProfile, Network, Record};
use giethoorn::journal::{JournalLimits, JournalMode, replay};
use giethoorn::segments::SegmentLimits;
use giethoorn::transport::{Socket, set_io_timeout};
use serde_json::{Value, json};
use std::io::Write;
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::sync::{
    Arc,
    atomic::{AtomicBool, Ordering},
};
use std::thread;
use std::time::{Duration, Instant};
use tungstenite::stream::MaybeTlsStream;
use tungstenite::{Message, WebSocket};

fn options(path: std::path::PathBuf) -> CaptureOptions {
    CaptureOptions {
        coin: "BTC".into(),
        network: Network::Mainnet,
        output: path,
        duration: Duration::from_secs(3),
        max_reconnects: 0,
        stale_after: Duration::from_secs(15),
        journal_mode: JournalMode::SingleFile(JournalLimits::UNLIMITED),
        feed_policy: Some(FeedPolicy {
            profile: FeedProfile::Combined,
            depth_stale_after_ms: 300,
            bbo_stale_after_ms: 300,
            timer_interval_ms: 10,
        }),
    }
}

fn connect(address: SocketAddr, record: &mut dyn FnMut(Event) -> Result<()>) -> Result<Socket> {
    let tcp = TcpStream::connect(address)?;
    tcp.set_read_timeout(Some(Duration::from_secs(3)))?;
    tcp.set_write_timeout(Some(Duration::from_secs(3)))?;
    record(Event::TcpConnected)?;
    let (socket, _) =
        tungstenite::client(format!("ws://{address}/ws"), MaybeTlsStream::Plain(tcp))?;
    set_io_timeout(&socket, Duration::from_millis(10))?;
    Ok(socket)
}

fn server(listener: &TcpListener) -> WebSocket<TcpStream> {
    let (tcp, _) = listener.accept().unwrap();
    tcp.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
    tcp.set_write_timeout(Some(Duration::from_secs(3))).unwrap();
    tungstenite::accept(tcp).unwrap()
}

fn subscriptions(socket: &mut WebSocket<TcpStream>, path: &std::path::Path) {
    let mut received = Vec::new();
    for _ in 0..2 {
        let value: Value =
            serde_json::from_str(&socket.read().unwrap().into_text().unwrap()).unwrap();
        assert_eq!(value["method"], "subscribe");
        assert_eq!(value["subscription"]["coin"], "BTC");
        received.push(value["subscription"]["type"].as_str().unwrap().to_string());
    }
    assert_eq!(received, ["l2Book", "bbo"]);
    // The peer has received both subscriptions; both must already be durable.
    let input = if path.is_dir() {
        std::fs::read_to_string(path.join("segment-00000001.jsonl")).unwrap()
    } else {
        std::fs::read_to_string(path).unwrap()
    };
    let recorded = input
        .lines()
        .map(|line| serde_json::from_str::<Record>(line).unwrap())
        .filter(|r| matches!(r.event, Event::TextSent { .. }))
        .count();
    assert_eq!(recorded, 2);
    for channel in received {
        socket.send(Message::Text(json!({"channel":"subscriptionResponse","data":{"method":"subscribe","subscription":{"type":channel,"coin":"BTC"}}}).to_string().into())).unwrap();
    }
}

fn message(kind: FeedKind, time: u64) -> Message {
    let value = if kind == FeedKind::Depth {
        let Event::TextReceived { text } = common::book(time, "100.1", "100.3") else {
            unreachable!()
        };
        text
    } else {
        json!({"channel":"bbo","data":{"coin":"BTC","time":time,"bbo":[{"px":"100.2","sz":"1","n":1},{"px":"100.4","sz":"2","n":2}]}}).to_string()
    };
    Message::Text(value.into())
}

fn replay_bytes(path: &std::path::Path) -> Vec<u8> {
    let mut bytes = Vec::new();
    replay(path, false, |observation| {
        serde_json::to_writer(&mut bytes, observation)?;
        bytes.push(b'\n');
        Ok(())
    })
    .unwrap();
    bytes
}

#[test]
fn a_frozen_required_channel_stalls_even_while_the_other_channel_is_busy() {
    for frozen in [FeedKind::Depth, FeedKind::Bbo] {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("capture.jsonl");
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let observed_path = path.clone();
        let exchange = thread::spawn(move || {
            let mut socket = server(&listener);
            subscriptions(&mut socket, &observed_path);
            socket.send(message(frozen, 100)).unwrap();
            let fast = if frozen == FeedKind::Depth {
                FeedKind::Bbo
            } else {
                FeedKind::Depth
            };
            let start = Instant::now();
            let mut time = 101;
            while start.elapsed() < Duration::from_secs(3) {
                if socket.send(message(fast, time)).is_err() {
                    break;
                }
                time += 1;
                thread::sleep(Duration::from_millis(20));
            }
        });
        let mut live = Vec::new();
        let error = capture_with_connector(
            &options(path.clone()),
            &mut live,
            Arc::new(AtomicBool::new(false)),
            |_, _, record| connect(address, record),
        )
        .unwrap_err();
        exchange.join().unwrap();
        assert_eq!(failure_exit_code(&error), 10);
        assert!(format!("{error:#}").contains(frozen.channel()));
        assert_eq!(live, replay_bytes(&path));
        let observations: Vec<Value> = live
            .split(|b| *b == b'\n')
            .filter(|l| !l.is_empty())
            .map(|l| serde_json::from_slice(l).unwrap())
            .collect();
        let frozen_key = if frozen == FeedKind::Depth {
            "depth"
        } else {
            "bbo"
        };
        let fast_key = if frozen == FeedKind::Depth {
            "bbo"
        } else {
            "depth"
        };
        assert!(
            observations
                .iter()
                .any(|o| o["feeds"][frozen_key]["status"] == "stale"
                    && o["feeds"][fast_key]["status"] == "fresh")
        );
        let inspection = giethoorn::inspect::inspect(&path, false).unwrap();
        assert_eq!(inspection.connection_errors, 1);
        assert_eq!(inspection.session.end_reason.as_deref(), Some("failed"));
        assert!(inspection.session.feeds.unwrap().timer_events > 0);
    }
}

struct CountedOutput {
    bytes: Vec<u8>,
    processed: usize,
    snapshots: usize,
    stop: Arc<AtomicBool>,
}
impl Write for CountedOutput {
    fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
        self.bytes.extend_from_slice(bytes);
        Ok(bytes.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        for line in self.bytes[self.processed..]
            .split(|b| *b == b'\n')
            .filter(|l| !l.is_empty())
        {
            let value: Value = serde_json::from_slice(line).unwrap();
            if value.get("quote").is_some() {
                self.snapshots += 1;
            }
        }
        self.processed = self.bytes.len();
        if self.snapshots == 100 {
            self.stop.store(true, Ordering::Relaxed);
        }
        Ok(())
    }
}

#[test]
fn combined_bursts_rotate_and_replay_every_market_and_freshness_observation_exactly() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("session");
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let observed_path = path.clone();
    let exchange = thread::spawn(move || {
        let mut socket = server(&listener);
        subscriptions(&mut socket, &observed_path);
        for time in 100..150 {
            socket.send(message(FeedKind::Depth, time)).unwrap();
            socket.send(message(FeedKind::Bbo, time)).unwrap();
        }
        while let Ok(message) = socket.read() {
            if matches!(message, Message::Close(_)) {
                let _ = socket.flush();
                break;
            }
        }
    });
    let stop = Arc::new(AtomicBool::new(false));
    let mut output = CountedOutput {
        bytes: Vec::new(),
        processed: 0,
        snapshots: 0,
        stop: stop.clone(),
    };
    let mut config = options(path.clone());
    config.duration = Duration::from_secs(5);
    config.feed_policy.as_mut().unwrap().depth_stale_after_ms = 5000;
    config.feed_policy.as_mut().unwrap().bbo_stale_after_ms = 5000;
    config.journal_mode = JournalMode::Segmented(SegmentLimits {
        max_segment_bytes: 4096,
        max_session_bytes: 512 * 1024,
        min_free_bytes: 0,
    });
    let report = capture_with_connector(&config, &mut output, stop, |_, _, record| {
        connect(address, record)
    })
    .unwrap();
    exchange.join().unwrap();
    assert_eq!(report.snapshots, 100);
    assert_eq!(output.snapshots, 100);
    assert_eq!(output.bytes, replay_bytes(&path));
    let inspection = giethoorn::inspect::inspect(&path, false).unwrap();
    assert!(inspection.storage.sealed_segments > 5);
    let feeds = inspection.feeds.unwrap();
    assert_eq!(feeds.depth.unwrap().snapshots, 50);
    assert_eq!(feeds.bbo.unwrap().snapshots, 50);
    assert!(report.feeds.unwrap().all_required_fresh_observed);
    let index = std::fs::read_to_string(path.join("index.jsonl")).unwrap();
    assert_eq!(
        serde_json::from_str::<Value>(index.lines().next().unwrap()).unwrap()["event_schema_version"],
        2
    );
}

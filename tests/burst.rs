mod common;

use std::io::Write;
use std::net::{TcpListener, TcpStream};
use std::sync::{
    Arc,
    atomic::{AtomicBool, Ordering},
};
use std::thread;
use std::time::Duration;

use giethoorn::capture::{CaptureOptions, capture_with_connector};
use giethoorn::event::{Event, Network};
use giethoorn::journal::{JournalMode, replay};
use giethoorn::segments::SegmentLimits;
use giethoorn::transport::set_io_timeout;
use tungstenite::{Message, stream::MaybeTlsStream};

struct CountedOutput {
    bytes: Vec<u8>,
    lines: u64,
    target: u64,
    stop: Arc<AtomicBool>,
}

impl Write for CountedOutput {
    fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
        self.lines += bytes.iter().filter(|&&b| b == b'\n').count() as u64;
        self.bytes.extend_from_slice(bytes);
        Ok(bytes.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        if self.lines == self.target {
            self.stop.store(true, Ordering::Relaxed);
        }
        Ok(())
    }
}

#[test]
fn a_thousand_queued_snapshots_survive_sync_backpressure_and_rotation_without_loss() {
    let count = 1000;
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let exchange = thread::spawn(move || {
        let (tcp, _) = listener.accept().unwrap();
        tcp.set_read_timeout(Some(Duration::from_secs(15))).unwrap();
        tcp.set_write_timeout(Some(Duration::from_secs(15)))
            .unwrap();
        let mut socket = tungstenite::accept(tcp).unwrap();
        assert!(
            socket
                .read()
                .unwrap()
                .into_text()
                .unwrap()
                .contains("subscribe")
        );
        for i in 0..count {
            let Event::TextReceived { text } = common::book(100 + i, "100.01", "100.03") else {
                unreachable!()
            };
            socket.send(Message::Text(text.into())).unwrap();
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
    });
    let directory = tempfile::tempdir().unwrap();
    let recording = directory.path().join("recording");
    let stop = Arc::new(AtomicBool::new(false));
    let mut output = CountedOutput {
        bytes: Vec::new(),
        lines: 0,
        target: count,
        stop: stop.clone(),
    };
    let options = CaptureOptions {
        coin: "BTC".into(),
        network: Network::Mainnet,
        output: recording.clone(),
        duration: Duration::from_secs(15),
        max_reconnects: 0,
        stale_after: Duration::from_secs(3),
        feed_policy: None,
        journal_mode: JournalMode::Segmented(SegmentLimits {
            max_segment_bytes: 4096,
            max_session_bytes: 2 * 1024 * 1024,
            min_free_bytes: 0,
        }),
    };
    let report = capture_with_connector(&options, &mut output, stop, |_, _, record| {
        let tcp = TcpStream::connect(address)?;
        tcp.set_read_timeout(Some(Duration::from_secs(3)))?;
        tcp.set_write_timeout(Some(Duration::from_secs(3)))?;
        record(Event::TcpConnected)?;
        let (socket, _) =
            tungstenite::client(format!("ws://{address}/ws"), MaybeTlsStream::Plain(tcp))?;
        set_io_timeout(&socket, Duration::from_millis(50))?;
        Ok(socket)
    })
    .unwrap();
    exchange.join().unwrap();
    assert_eq!(report.snapshots, count);
    assert_eq!(output.lines, count);
    assert_eq!(report.connections, 1);
    assert_eq!(
        report.last_quote.as_ref().unwrap().exchange_time_ms,
        100 + count - 1
    );
    let mut replayed = Vec::new();
    let replay_report = replay(&recording, false, |quote| {
        serde_json::to_writer(&mut replayed, quote)?;
        replayed.push(b'\n');
        Ok(())
    })
    .unwrap();
    assert_eq!(report, replay_report);
    assert_eq!(output.bytes, replayed);
    let inspection = giethoorn::inspect::inspect(&recording, false).unwrap();
    assert!(inspection.storage.sealed_segments > 10);
}

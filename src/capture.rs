use std::fmt;
use std::io::Write;
use std::path::PathBuf;
use std::sync::{
    Arc,
    atomic::{AtomicBool, Ordering},
};
use std::time::{Duration, Instant};

use anyhow::{Context, Result, bail, ensure};
use tungstenite::{Error as WsError, Message};

use crate::engine::Report;
use crate::event::{Event, FEED_SCHEMA_VERSION, FeedKind, FeedPolicy, Network, SCHEMA_VERSION};
use crate::feeds::MarketEngine;
use crate::hyperliquid::{feed_subscription, subscription, validate_coin};
use crate::journal::{Journal, JournalMode};
use crate::transport::{self, Socket};

#[derive(Debug, Clone)]
pub struct CaptureOptions {
    pub coin: String,
    pub network: Network,
    pub output: PathBuf,
    pub duration: Duration,
    /// Retries after the initial attempt, including disconnect recovery.
    pub max_reconnects: u32,
    pub stale_after: Duration,
    pub journal_mode: JournalMode,
    /// None retains the schema-1 depth-only contract.
    pub feed_policy: Option<FeedPolicy>,
}

/// Recording, validation and output failures are terminal; never retry them as
/// network failures or send further application messages after a journal error.
#[derive(Debug)]
struct RecordingError(anyhow::Error);

impl fmt::Display for RecordingError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "recording failed: {:#}", self.0)
    }
}

impl std::error::Error for RecordingError {}

#[derive(Debug)]
struct NetworkFailure(anyhow::Error);

impl fmt::Display for NetworkFailure {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "network collection failed: {:#}", self.0)
    }
}
impl std::error::Error for NetworkFailure {}

/// Subprocess contract: only 10 is eligible for a bounded network restart.
/// 11 is a local recording/data/output failure; other errors are fatal by default.
pub fn failure_exit_code(error: &anyhow::Error) -> u8 {
    if error.downcast_ref::<NetworkFailure>().is_some() {
        10
    } else if error.downcast_ref::<RecordingError>().is_some() {
        11
    } else {
        1
    }
}

struct Session<W> {
    journal: Journal,
    engine: MarketEngine,
    output: W,
}

impl<W: Write> Session<W> {
    fn record(&mut self, connection_id: u64, event: Event) -> Result<()> {
        let result = (|| {
            let record = self.journal.append(connection_id, event)?;
            if let Some(quote) = self.engine.apply(&record)? {
                serde_json::to_writer(&mut self.output, &quote)?;
                self.output.write_all(b"\n")?;
                self.output.flush()?;
            }
            Ok(())
        })();
        result.map_err(|error| anyhow::Error::new(RecordingError(error)))
    }
}

pub fn capture(
    options: &CaptureOptions,
    output: impl Write,
    stop: Arc<AtomicBool>,
) -> Result<Report> {
    capture_with_connector(options, output, stop, |endpoint, timeout, record| {
        transport::connect(endpoint, timeout, record)
    })
}

/// The connector seam enables real local WebSocket integration tests without
/// exchange availability, credentials, TLS bypasses, or a mock state engine.
pub fn capture_with_connector(
    options: &CaptureOptions,
    output: impl Write,
    stop: Arc<AtomicBool>,
    mut connect: impl FnMut(&str, Duration, &mut dyn FnMut(Event) -> Result<()>) -> Result<Socket>,
) -> Result<Report> {
    validate_coin(&options.coin)?;
    if let Some(policy) = &options.feed_policy {
        policy.validate()?;
    }
    ensure!(
        !options.duration.is_zero(),
        "capture duration must be positive"
    );
    ensure!(
        !options.stale_after.is_zero(),
        "stale-book timeout must be positive"
    );
    let deadline = Instant::now()
        .checked_add(options.duration)
        .context("capture duration is too large")?;
    if let Some(parent) = options
        .output
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
    {
        std::fs::create_dir_all(parent).context("create capture directory")?;
    }
    let mut session = Session {
        journal: Journal::create_versioned(
            &options.output,
            options.journal_mode,
            if options.feed_policy.is_some() {
                FEED_SCHEMA_VERSION
            } else {
                SCHEMA_VERSION
            },
        )?,
        engine: MarketEngine::default(),
        output,
    };
    session.record(
        0,
        if let Some(policy) = &options.feed_policy {
            Event::FeedSessionStarted {
                coin: options.coin.clone(),
                network: options.network,
                application_version: env!("CARGO_PKG_VERSION").to_string(),
                policy: policy.clone(),
            }
        } else {
            Event::SessionStarted {
                coin: options.coin.clone(),
                network: options.network,
                application_version: env!("CARGO_PKG_VERSION").to_string(),
            }
        },
    )?;
    let mut connection_id = 0_u64;
    let mut last_error = None;
    let outcome = loop {
        if stop.load(Ordering::Relaxed) || Instant::now() >= deadline {
            break last_error.map_or(Ok(()), Err);
        }
        connection_id += 1;
        session.record(
            connection_id,
            Event::ConnectionAttempt {
                endpoint: options.network.endpoint().to_string(),
            },
        )?;
        let timeout = deadline
            .saturating_duration_since(Instant::now())
            .min(Duration::from_secs(5))
            .max(Duration::from_millis(1));
        let result = connect(options.network.endpoint(), timeout, &mut |event| {
            session.record(connection_id, event)
        });
        let result = match result {
            Ok(mut socket) => {
                session.record(connection_id, Event::ConnectionOpened)?;
                let result = stream(
                    &mut socket,
                    &mut session,
                    connection_id,
                    options,
                    deadline,
                    &stop,
                );
                if result.is_ok() {
                    session.record(
                        connection_id,
                        Event::ControlSent {
                            kind: "close".into(),
                            payload_hex: String::new(),
                        },
                    )?;
                    // A close-write error is still recorded, but does not erase a
                    // successfully completed timed capture of market data.
                    if let Err(error) = socket.close(None) {
                        session.record(
                            connection_id,
                            Event::ConnectionError {
                                message: format!("close handshake: {error}"),
                            },
                        )?;
                    }
                }
                // Dropping the socket closes the TCP stream before the close event.
                drop(socket);
                result
            }
            Err(error) => Err(error),
        };
        match result {
            Ok(()) => {
                session.record(
                    connection_id,
                    Event::ConnectionClosed {
                        reason: "capture stopped".into(),
                    },
                )?;
                break Ok(());
            }
            Err(error) => {
                if error.downcast_ref::<RecordingError>().is_some() {
                    return Err(error);
                }
                session.record(
                    connection_id,
                    Event::ConnectionError {
                        message: format!("{error:#}"),
                    },
                )?;
                session.record(
                    connection_id,
                    Event::ConnectionClosed {
                        reason: "connection failed".into(),
                    },
                )?;
                let permanent = transport::is_permanent_failure(&error);
                last_error = Some(error);
                if permanent || connection_id > u64::from(options.max_reconnects) {
                    break Err(last_error.take().expect("error was just set"));
                }
                let delay = Duration::from_secs(1_u64 << (connection_id - 1).min(4));
                let until = (Instant::now() + delay).min(deadline);
                while Instant::now() < until && !stop.load(Ordering::Relaxed) {
                    std::thread::sleep(
                        until
                            .saturating_duration_since(Instant::now())
                            .min(Duration::from_millis(50)),
                    );
                }
            }
        }
    };
    let has_two_sided_book = session.engine.has_usable_data();
    let reason = if outcome.is_err() || !has_two_sided_book {
        "failed"
    } else if stop.load(Ordering::Relaxed) {
        "interrupted"
    } else {
        "duration_elapsed"
    };
    session.record(
        0,
        Event::SessionEnded {
            reason: reason.into(),
        },
    )?;
    session
        .journal
        .finish()
        .map_err(|error| anyhow::Error::new(RecordingError(error)))?;
    if let Err(error) = outcome {
        let error = if transport::is_permanent_failure(&error) {
            error
        } else {
            anyhow::Error::new(NetworkFailure(error))
        };
        return Err(error).with_context(|| {
            format!(
                "capture failed; diagnostic journal: {}",
                options.output.display()
            )
        });
    }
    ensure!(
        has_two_sided_book,
        "capture received no usable two-sided book for every required feed with required acknowledgements; diagnostic journal: {}",
        options.output.display()
    );
    Ok(session.engine.report())
}

fn stream<W: Write>(
    socket: &mut Socket,
    session: &mut Session<W>,
    connection_id: u64,
    options: &CaptureOptions,
    deadline: Instant,
    stop: &AtomicBool,
) -> Result<()> {
    if let Some(policy) = &options.feed_policy {
        transport::set_io_timeout(socket, Duration::from_millis(policy.timer_interval_ms))?;
        for feed in [FeedKind::Depth, FeedKind::Bbo] {
            if policy.profile.includes(feed) {
                send_text(
                    socket,
                    session,
                    connection_id,
                    feed_subscription(&options.coin, feed),
                )?;
            }
        }
    } else {
        send_text(socket, session, connection_id, subscription(&options.coin))?;
    }
    let mut last_ping = Instant::now();
    let mut last_book = Instant::now();
    let mut last_timer = Instant::now();
    while !stop.load(Ordering::Relaxed) && Instant::now() < deadline {
        if let Some(policy) = &options.feed_policy {
            if last_timer.elapsed() >= Duration::from_millis(policy.timer_interval_ms) {
                session.record(connection_id, Event::FeedTimer)?;
                last_timer = Instant::now();
            }
            if let Some(feed) = session.engine.stalled_feed() {
                bail!("required {} feed stalled; reconnecting", feed.channel());
            }
        } else {
            ensure!(
                last_book.elapsed() < options.stale_after,
                "market-data book stalled; reconnecting"
            );
        }
        if last_ping.elapsed() >= Duration::from_secs(20) {
            send_text(
                socket,
                session,
                connection_id,
                r#"{"method":"ping"}"#.to_string(),
            )?;
            last_ping = Instant::now();
        }
        match socket.read() {
            Ok(Message::Text(text)) => {
                let before = options
                    .feed_policy
                    .is_none()
                    .then(|| session.engine.report().snapshots);
                session.record(
                    connection_id,
                    Event::TextReceived {
                        text: text.to_string(),
                    },
                )?;
                if before.is_some_and(|before| session.engine.report().snapshots > before) {
                    last_book = Instant::now();
                }
            }
            Ok(Message::Ping(payload)) => {
                let payload_hex = hex(&payload);
                session.record(
                    connection_id,
                    Event::ControlReceived {
                        kind: "ping".into(),
                        payload_hex: payload_hex.clone(),
                    },
                )?;
                session.record(
                    connection_id,
                    Event::ControlSent {
                        kind: "pong".into(),
                        payload_hex,
                    },
                )?;
                // tungstenite queues the matching pong on read; flush only after logging.
                socket.flush()?;
            }
            Ok(Message::Pong(payload)) => {
                session.record(
                    connection_id,
                    Event::ControlReceived {
                        kind: "pong".into(),
                        payload_hex: hex(&payload),
                    },
                )?;
            }
            Ok(Message::Close(frame)) => {
                let payload = frame
                    .as_ref()
                    .map(|f| {
                        let mut bytes = u16::from(f.code).to_be_bytes().to_vec();
                        bytes.extend_from_slice(f.reason.as_bytes());
                        bytes
                    })
                    .unwrap_or_default();
                session.record(
                    connection_id,
                    Event::ControlReceived {
                        kind: "close".into(),
                        payload_hex: hex(&payload),
                    },
                )?;
                session.record(
                    connection_id,
                    Event::ControlSent {
                        kind: "close".into(),
                        payload_hex: hex(&payload),
                    },
                )?;
                let _ = socket.flush();
                bail!("exchange closed WebSocket");
            }
            Ok(Message::Binary(payload)) => {
                session.record(
                    connection_id,
                    Event::ControlReceived {
                        kind: "binary".into(),
                        payload_hex: hex(&payload),
                    },
                )?;
                bail!("unexpected binary market data");
            }
            Ok(Message::Frame(_)) => bail!("unexpected raw WebSocket frame"),
            Err(WsError::Io(error))
                if matches!(
                    error.kind(),
                    std::io::ErrorKind::WouldBlock
                        | std::io::ErrorKind::TimedOut
                        | std::io::ErrorKind::Interrupted
                ) => {}
            Err(error) => return Err(error).context("read WebSocket"),
        }
    }
    Ok(())
}

fn send_text<W: Write>(
    socket: &mut Socket,
    session: &mut Session<W>,
    connection_id: u64,
    text: String,
) -> Result<()> {
    session.record(connection_id, Event::TextSent { text: text.clone() })?;
    socket
        .send(Message::Text(text.into()))
        .context("send WebSocket text")
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

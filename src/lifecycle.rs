//! Shared record/lifecycle validation for both normalization versions.
use crate::event::{Event, FEED_SCHEMA_VERSION, Record, SCHEMA_VERSION};
use crate::hyperliquid::validate_coin;
use anyhow::{Result, ensure};

#[derive(Debug, Default, PartialEq, Eq)]
pub(crate) enum Phase {
    #[default]
    New,
    Idle,
    Connecting,
    Connected,
    Ended,
}

#[derive(Debug, Default)]
pub(crate) struct Lifecycle {
    pub phase: Phase,
    pub sequence: u64,
    pub monotonic_ns: u64,
    pub connection_id: u64,
    pub coin: String,
    pub end_reason: Option<String>,
}

impl Lifecycle {
    /// Returns whether active market state must be cleared.
    pub fn apply(&mut self, record: &Record, schema: u16) -> Result<bool> {
        ensure!(
            record.schema_version == schema,
            "unsupported or mixed schema version {}",
            record.schema_version
        );
        ensure!(
            record.sequence == self.sequence + 1,
            "noncontiguous sequence: expected {}, got {}",
            self.sequence + 1,
            record.sequence
        );
        ensure!(
            record.monotonic_ns >= self.monotonic_ns,
            "monotonic timestamp moved backwards"
        );
        ensure!(self.phase != Phase::Ended, "event after session end");
        let mut clear = false;
        match &record.event {
            Event::SessionStarted { coin, .. } | Event::FeedSessionStarted { coin, .. } => {
                ensure!(
                    (schema == SCHEMA_VERSION
                        && matches!(record.event, Event::SessionStarted { .. }))
                        || (schema == FEED_SCHEMA_VERSION
                            && matches!(record.event, Event::FeedSessionStarted { .. })),
                    "session start does not match schema"
                );
                ensure!(
                    self.phase == Phase::New && record.connection_id == 0,
                    "invalid session start"
                );
                validate_coin(coin)?;
                self.coin = coin.clone();
                self.phase = Phase::Idle;
            }
            Event::ConnectionAttempt { .. } => {
                ensure!(
                    self.phase == Phase::Idle,
                    "connection attempt outside idle state"
                );
                ensure!(
                    record.connection_id == self.connection_id + 1,
                    "connection IDs must increase by one"
                );
                self.connection_id = record.connection_id;
                self.phase = Phase::Connecting;
                clear = true;
            }
            Event::SessionEnded { reason } => {
                ensure!(
                    self.phase == Phase::Idle && record.connection_id == 0,
                    "session ended with an open connection or without a session"
                );
                self.phase = Phase::Ended;
                self.end_reason = Some(reason.clone());
            }
            event => {
                ensure!(
                    record.connection_id == self.connection_id && self.connection_id > 0,
                    "event has wrong connection ID"
                );
                match event {
                    Event::TcpConnected
                    | Event::UpgradeRequest { .. }
                    | Event::UpgradeResponse { .. } => {
                        ensure!(
                            self.phase == Phase::Connecting,
                            "handshake event outside connection attempt"
                        );
                    }
                    Event::ConnectionOpened => {
                        ensure!(
                            self.phase == Phase::Connecting,
                            "connection opened outside connection attempt"
                        );
                        self.phase = Phase::Connected;
                    }
                    Event::ConnectionClosed { .. } => {
                        ensure!(
                            matches!(self.phase, Phase::Connecting | Phase::Connected),
                            "close outside active connection"
                        );
                        self.phase = Phase::Idle;
                        clear = true;
                    }
                    Event::ConnectionError { .. } => {
                        ensure!(
                            matches!(self.phase, Phase::Connecting | Phase::Connected),
                            "error outside active connection"
                        );
                        clear = true;
                    }
                    Event::FeedTimer => {
                        ensure!(
                            schema == FEED_SCHEMA_VERSION && self.phase == Phase::Connected,
                            "feed timer outside schema-2 open connection"
                        );
                    }
                    Event::TextReceived { .. }
                    | Event::TextSent { .. }
                    | Event::ControlReceived { .. }
                    | Event::ControlSent { .. } => {
                        ensure!(
                            self.phase == Phase::Connected,
                            "WebSocket event outside open connection"
                        );
                    }
                    Event::SessionStarted { .. }
                    | Event::FeedSessionStarted { .. }
                    | Event::SessionEnded { .. }
                    | Event::ConnectionAttempt { .. } => unreachable!(),
                }
            }
        }
        self.sequence = record.sequence;
        self.monotonic_ns = record.monotonic_ns;
        Ok(clear)
    }
}

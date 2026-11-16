//! Version-2 normalization. State and freshness depend only on accepted records.
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};

use crate::engine::{Engine, Quote, Report};
use crate::event::{Event, FEED_SCHEMA_VERSION, FeedKind, FeedPolicy, Record, SCHEMA_VERSION};
use crate::hyperliquid::{Book, FeedMessage, parse_feed_message};
use crate::lifecycle::{Lifecycle, Phase};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FeedStatus {
    Disconnected,
    AwaitingAcknowledgement,
    AwaitingData,
    Fresh,
    Empty,
    Stale,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FeedState {
    pub status: FeedStatus,
    pub acknowledged: bool,
    pub stale_after_ms: u64,
    pub latest_sequence: Option<u64>,
    pub exchange_time_ms: Option<u64>,
    /// Age of the latest accepted observation, including an empty side.
    pub age_ns: Option<u64>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FeedStates {
    pub depth: Option<FeedState>,
    pub bbo: Option<FeedState>,
    pub all_required_fresh: bool,
}

impl FeedStates {
    fn signature(&self) -> [Option<(FeedStatus, bool)>; 2] {
        [self.depth.as_ref(), self.bbo.as_ref()]
            .map(|state| state.map(|s| (s.status, s.acknowledged)))
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ObservationKind {
    Depth,
    Bbo,
    Freshness,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FeedObservation {
    pub normalization_version: u16,
    pub kind: ObservationKind,
    pub sequence: u64,
    pub connection_id: u64,
    pub local_time_ns: u64,
    pub monotonic_ns: u64,
    pub coin: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub quote: Option<Quote>,
    pub feeds: FeedStates,
}

/// Untagged only at this boundary: legacy quote bytes are kept exactly intact.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(untagged)]
pub enum Observation {
    Legacy(Quote),
    Feed(FeedObservation),
}

impl Observation {
    pub fn quote(&self) -> Option<&Quote> {
        match self {
            Self::Legacy(quote) => Some(quote),
            Self::Feed(observation) => observation.quote.as_ref(),
        }
    }

    pub fn source(&self) -> Option<FeedKind> {
        match self {
            Self::Feed(observation) => match observation.kind {
                ObservationKind::Depth => Some(FeedKind::Depth),
                ObservationKind::Bbo => Some(FeedKind::Bbo),
                ObservationKind::Freshness => None,
            },
            Self::Legacy(_) => None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FeedSummary {
    pub snapshots: u64,
    pub two_sided_snapshots: u64,
    pub stale_snapshots: u64,
    pub acknowledgements: u64,
    /// Historical only; live state is in FeedReport.current.
    pub last_observation: Option<Quote>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FeedReport {
    pub normalization_version: u16,
    pub policy: FeedPolicy,
    pub depth: Option<FeedSummary>,
    pub bbo: Option<FeedSummary>,
    pub timer_events: u64,
    pub freshness_events: u64,
    pub all_required_fresh_observed: bool,
    pub current: FeedStates,
}

#[derive(Debug, Default)]
struct Slot {
    book: Option<Book>,
    quote: Option<Quote>,
    historical_quote: Option<Quote>,
    acknowledged: bool,
    last_usable_ns: Option<u64>,
    snapshots: u64,
    two_sided_snapshots: u64,
    stale_snapshots: u64,
    acknowledgements: u64,
}

impl Slot {
    fn reset(&mut self) {
        self.book = None;
        self.quote = None;
        self.acknowledged = false;
        self.last_usable_ns = None;
    }

    fn summary(&self) -> FeedSummary {
        FeedSummary {
            snapshots: self.snapshots,
            two_sided_snapshots: self.two_sided_snapshots,
            stale_snapshots: self.stale_snapshots,
            acknowledgements: self.acknowledgements,
            last_observation: self.historical_quote.clone(),
        }
    }
}

#[derive(Debug, Default)]
struct FeedEngine {
    lifecycle: Lifecycle,
    policy: Option<FeedPolicy>,
    depth: Slot,
    bbo: Slot,
    available: bool,
    opened_ns: u64,
    other_messages: u64,
    timer_events: u64,
    freshness_events: u64,
    all_fresh_observed: bool,
    signature: Option<[Option<(FeedStatus, bool)>; 2]>,
}

impl FeedEngine {
    fn slot(&self, kind: FeedKind) -> &Slot {
        match kind {
            FeedKind::Depth => &self.depth,
            FeedKind::Bbo => &self.bbo,
        }
    }

    fn slot_mut(&mut self, kind: FeedKind) -> &mut Slot {
        match kind {
            FeedKind::Depth => &mut self.depth,
            FeedKind::Bbo => &mut self.bbo,
        }
    }

    fn deadline_reference(&self, slot: &Slot) -> u64 {
        if slot.acknowledged {
            slot.last_usable_ns.unwrap_or(self.opened_ns)
        } else {
            self.opened_ns
        }
    }

    fn state(&self, kind: FeedKind) -> Option<FeedState> {
        let policy = self.policy.as_ref()?;
        if !policy.profile.includes(kind) {
            return None;
        }
        let slot = self.slot(kind);
        let now = self.lifecycle.monotonic_ns;
        let limit_ms = policy.stale_after_ms(kind);
        let status = if !self.available {
            FeedStatus::Disconnected
        } else if now - self.deadline_reference(slot) >= limit_ms * 1_000_000 {
            FeedStatus::Stale
        } else if !slot.acknowledged {
            FeedStatus::AwaitingAcknowledgement
        } else if let Some(quote) = &slot.quote {
            if quote.mid.is_some() {
                FeedStatus::Fresh
            } else {
                FeedStatus::Empty
            }
        } else {
            FeedStatus::AwaitingData
        };
        Some(FeedState {
            status,
            acknowledged: slot.acknowledged,
            stale_after_ms: limit_ms,
            latest_sequence: slot.quote.as_ref().map(|q| q.sequence),
            exchange_time_ms: slot.quote.as_ref().map(|q| q.exchange_time_ms),
            age_ns: slot.quote.as_ref().map(|q| now - q.monotonic_ns),
        })
    }

    fn states(&self) -> FeedStates {
        let depth = self.state(FeedKind::Depth);
        let bbo = self.state(FeedKind::Bbo);
        let all_required_fresh = self.available
            && [depth.as_ref(), bbo.as_ref()]
                .into_iter()
                .flatten()
                .all(|s| s.status == FeedStatus::Fresh);
        FeedStates {
            depth,
            bbo,
            all_required_fresh,
        }
    }

    fn apply(&mut self, record: &Record) -> Result<Option<FeedObservation>> {
        if let Event::FeedSessionStarted { policy, .. } = &record.event {
            policy.validate()?;
        }
        let clear = self.lifecycle.apply(record, FEED_SCHEMA_VERSION)?;
        if clear {
            self.available = false;
            self.depth.reset();
            self.bbo.reset();
        }
        let mut market = None;
        match &record.event {
            Event::FeedSessionStarted { policy, .. } => {
                self.policy = Some(policy.clone());
                self.signature = Some(self.states().signature());
                return Ok(None);
            }
            Event::ConnectionOpened => {
                self.available = true;
                self.opened_ns = record.monotonic_ns;
            }
            Event::FeedTimer => self.timer_events += 1,
            Event::TextReceived { text } => {
                ensure!(self.available, "market message after invalidation");
                let message = parse_feed_message(
                    text,
                    &self.lifecycle.coin,
                    self.policy.as_ref().context("missing feed policy")?,
                );
                let message = match message {
                    Ok(message) => message,
                    Err(error) => {
                        self.available = false;
                        self.depth.reset();
                        self.bbo.reset();
                        return Err(error).with_context(|| {
                            format!("invalid market data at sequence {}", record.sequence)
                        });
                    }
                };
                match message {
                    FeedMessage::Acknowledged(kind) => {
                        let slot = self.slot_mut(kind);
                        slot.acknowledged = true;
                        slot.acknowledgements += 1;
                        self.other_messages += 1;
                    }
                    FeedMessage::Other => self.other_messages += 1,
                    FeedMessage::Book(kind, book) => {
                        let slot = self.slot(kind);
                        if slot
                            .book
                            .as_ref()
                            .is_some_and(|old| old.exchange_time_ms > book.exchange_time_ms)
                        {
                            self.slot_mut(kind).stale_snapshots += 1;
                        } else {
                            let quote = crate::engine::quote_from_book(
                                record,
                                &self.lifecycle.coin,
                                &book,
                            )?;
                            let slot = self.slot_mut(kind);
                            if quote.mid.is_some() {
                                slot.two_sided_snapshots += 1;
                                slot.last_usable_ns = Some(record.monotonic_ns);
                            }
                            slot.snapshots += 1;
                            slot.book = Some(book);
                            slot.historical_quote = Some(quote.clone());
                            slot.quote = Some(quote.clone());
                            market = Some((kind, quote));
                        }
                    }
                }
            }
            _ => {}
        }
        let states = self.states();
        self.all_fresh_observed |= states.all_required_fresh;
        let changed = self.signature != Some(states.signature());
        self.signature = Some(states.signature());
        let (kind, quote) = if let Some((source, quote)) = market {
            (
                match source {
                    FeedKind::Depth => ObservationKind::Depth,
                    FeedKind::Bbo => ObservationKind::Bbo,
                },
                Some(quote),
            )
        } else if changed {
            self.freshness_events += 1;
            (ObservationKind::Freshness, None)
        } else {
            return Ok(None);
        };
        Ok(Some(FeedObservation {
            normalization_version: FEED_SCHEMA_VERSION,
            kind,
            sequence: record.sequence,
            connection_id: record.connection_id,
            local_time_ns: record.local_time_ns,
            monotonic_ns: record.monotonic_ns,
            coin: self.lifecycle.coin.clone(),
            quote,
            feeds: states,
        }))
    }

    fn report(&self) -> Report {
        Report {
            records: self.lifecycle.sequence,
            connections: self.lifecycle.connection_id,
            snapshots: self.depth.snapshots + self.bbo.snapshots,
            stale_snapshots: self.depth.stale_snapshots + self.bbo.stale_snapshots,
            other_messages: self.other_messages,
            complete: self.lifecycle.phase == Phase::Ended,
            end_reason: self.lifecycle.end_reason.clone(),
            last_quote: None,
            feeds: self.policy.as_ref().map(|policy| FeedReport {
                normalization_version: FEED_SCHEMA_VERSION,
                policy: policy.clone(),
                depth: policy
                    .profile
                    .includes(FeedKind::Depth)
                    .then(|| self.depth.summary()),
                bbo: policy
                    .profile
                    .includes(FeedKind::Bbo)
                    .then(|| self.bbo.summary()),
                timer_events: self.timer_events,
                freshness_events: self.freshness_events,
                all_required_fresh_observed: self.all_fresh_observed,
                current: self.states(),
            }),
        }
    }
}

/// Select once from the recorded schema. Never infer normalization from payloads.
#[derive(Debug, Default)]
pub struct MarketEngine {
    schema: Option<u16>,
    legacy: Engine,
    feeds: FeedEngine,
}

impl MarketEngine {
    pub fn apply(&mut self, record: &Record) -> Result<Option<Observation>> {
        ensure!(
            matches!(record.schema_version, SCHEMA_VERSION | FEED_SCHEMA_VERSION),
            "unsupported schema version {}",
            record.schema_version
        );
        if let Some(schema) = self.schema {
            ensure!(
                schema == record.schema_version,
                "mixed event schemas in one session"
            );
        }
        self.schema = Some(record.schema_version);
        if record.schema_version == SCHEMA_VERSION {
            self.legacy
                .apply(record)
                .map(|quote| quote.map(Observation::Legacy))
        } else {
            match self.feeds.apply(record) {
                Ok(observation) => Ok(observation.map(Observation::Feed)),
                Err(error) => {
                    self.feeds.available = false;
                    self.feeds.depth.reset();
                    self.feeds.bbo.reset();
                    Err(error)
                }
            }
        }
    }

    pub fn report(&self) -> Report {
        if self.schema == Some(FEED_SCHEMA_VERSION) {
            self.feeds.report()
        } else {
            self.legacy.report()
        }
    }

    pub fn has_usable_data(&self) -> bool {
        if self.schema == Some(FEED_SCHEMA_VERSION) {
            self.feeds.all_fresh_observed
        } else {
            self.legacy
                .report()
                .last_quote
                .is_some_and(|q| q.mid.is_some())
        }
    }

    /// Evaluated only at recorded time; the I/O loop supplies timer records.
    pub fn stalled_feed(&self) -> Option<FeedKind> {
        if self.schema != Some(FEED_SCHEMA_VERSION) {
            return None;
        }
        [FeedKind::Depth, FeedKind::Bbo].into_iter().find(|kind| {
            self.feeds
                .state(*kind)
                .is_some_and(|s| s.status == FeedStatus::Stale)
        })
    }
}

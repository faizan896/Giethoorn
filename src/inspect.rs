//! Offline collection diagnostics. These are measurements of the recorded
//! session, never a current market-health signal or trading decision input.

use std::path::Path;

use anyhow::{Context, Result};
use serde::Serialize;

use crate::engine::Report;
use crate::event::{Event, FeedKind, Record};
use crate::feeds::Observation;
use crate::journal::replay_path_observed;
use crate::segments::StorageSummary;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum InspectionStatus {
    Completed,
    CompletedWithConnectionErrors,
    Failed,
    Incomplete,
    NoUsableData,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ClockDeltaRange {
    pub min_ms: i64,
    pub max_ms: i64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Inspection {
    pub status: InspectionStatus,
    pub session: Report,
    pub file_bytes: u64,
    pub storage: StorageSummary,
    pub recorded_duration_ns: u64,
    pub successful_connections: u64,
    pub connection_errors: u64,
    pub two_sided_snapshots: u64,
    pub one_sided_snapshots: u64,
    /// Only between accepted snapshots on the same connection.
    pub max_snapshot_gap_ns: Option<u64>,
    pub max_first_snapshot_wait_ns: Option<u64>,
    /// Includes outage tails up to the last recorded event; not after recording.
    pub max_disconnected_ns: Option<u64>,
    pub snapshot_age_at_end_ns: Option<u64>,
    /// local_wall_ms - exchange_ms; includes clock offset, batching and delay.
    /// It is NOT network latency or round-trip time.
    pub observed_source_clock_delta: Option<ClockDeltaRange>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub feeds: Option<FeedInspection>,
}

#[derive(Debug, Default, Clone, PartialEq, Eq, Serialize)]
pub struct FeedMeasurements {
    pub snapshots: u64,
    pub two_sided_snapshots: u64,
    pub one_sided_snapshots: u64,
    pub max_snapshot_gap_ns: Option<u64>,
    pub max_first_snapshot_wait_ns: Option<u64>,
    pub snapshot_age_at_end_ns: Option<u64>,
    pub observed_source_clock_delta: Option<ClockDeltaRange>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FeedInspection {
    pub depth: Option<FeedMeasurements>,
    pub bbo: Option<FeedMeasurements>,
}

#[derive(Default)]
struct ChannelMeasurements {
    report: FeedMeasurements,
    previous_ns: Option<u64>,
    last_ns: Option<u64>,
}

#[derive(Default)]
struct Measurements {
    first_ns: Option<u64>,
    last_ns: u64,
    opened_ns: Option<u64>,
    disconnected_ns: Option<u64>,
    previous_snapshot_ns: Option<u64>,
    last_snapshot_ns: Option<u64>,
    successful_connections: u64,
    connection_errors: u64,
    two_sided: u64,
    one_sided: u64,
    max_gap: Option<u64>,
    max_first_wait: Option<u64>,
    max_disconnected: Option<u64>,
    clock_delta: Option<ClockDeltaRange>,
    channels: [ChannelMeasurements; 2],
}

impl Measurements {
    fn observe(&mut self, record: &Record, observation: Option<&Observation>) -> Result<()> {
        let now = record.monotonic_ns;
        self.first_ns.get_or_insert(now);
        self.last_ns = now;
        match record.event {
            Event::ConnectionOpened => {
                self.successful_connections += 1;
                self.opened_ns = Some(now);
                self.previous_snapshot_ns = None;
                for channel in &mut self.channels {
                    channel.previous_ns = None;
                }
                if let Some(start) = self.disconnected_ns.take() {
                    update_max(&mut self.max_disconnected, now - start);
                }
            }
            Event::ConnectionClosed { .. } => {
                self.disconnected_ns.get_or_insert(now);
                self.opened_ns = None;
                self.previous_snapshot_ns = None;
                for channel in &mut self.channels {
                    channel.previous_ns = None;
                }
            }
            Event::ConnectionError { .. } => self.connection_errors += 1,
            _ => {}
        }
        if let Some(quote) = observation.and_then(Observation::quote) {
            let source = observation.and_then(Observation::source);
            if quote.mid.is_some() {
                self.two_sided += 1;
            } else {
                self.one_sided += 1;
            }
            let previous = source.map_or(self.previous_snapshot_ns, |source| {
                self.channels[if source == FeedKind::Depth { 0 } else { 1 }].previous_ns
            });
            if let Some(previous) = previous {
                update_max(&mut self.max_gap, now - previous);
            } else if let Some(opened) = self.opened_ns {
                update_max(&mut self.max_first_wait, now - opened);
            }
            if source.is_none() {
                self.previous_snapshot_ns = Some(now);
            }
            self.last_snapshot_ns = Some(now);
            let delta: i64 = (i128::from(quote.local_time_ns / 1_000_000)
                - i128::from(quote.exchange_time_ms))
            .try_into()
            .context("source clock delta exceeds supported diagnostic range")?;
            if let Some(source) = source {
                let channel = &mut self.channels[if source == FeedKind::Depth { 0 } else { 1 }];
                channel.report.snapshots += 1;
                if quote.mid.is_some() {
                    channel.report.two_sided_snapshots += 1;
                } else {
                    channel.report.one_sided_snapshots += 1;
                }
                if let Some(previous) = channel.previous_ns {
                    update_max(&mut channel.report.max_snapshot_gap_ns, now - previous);
                } else if let Some(opened) = self.opened_ns {
                    update_max(&mut channel.report.max_first_snapshot_wait_ns, now - opened);
                }
                channel.previous_ns = Some(now);
                channel.last_ns = Some(now);
                update_delta(&mut channel.report.observed_source_clock_delta, delta);
            }
            match &mut self.clock_delta {
                Some(range) => {
                    range.min_ms = range.min_ms.min(delta);
                    range.max_ms = range.max_ms.max(delta);
                }
                range @ None => {
                    *range = Some(ClockDeltaRange {
                        min_ms: delta,
                        max_ms: delta,
                    })
                }
            }
        }
        Ok(())
    }
}

fn update_max(value: &mut Option<u64>, observed: u64) {
    *value = Some(value.unwrap_or(0).max(observed));
}

fn update_delta(range: &mut Option<ClockDeltaRange>, delta: i64) {
    match range {
        Some(range) => {
            range.min_ms = range.min_ms.min(delta);
            range.max_ms = range.max_ms.max(delta);
        }
        None => {
            *range = Some(ClockDeltaRange {
                min_ms: delta,
                max_ms: delta,
            })
        }
    }
}

pub fn inspect(path: &Path, allow_incomplete: bool) -> Result<Inspection> {
    let mut metrics = Measurements::default();
    let (session, storage) = replay_path_observed(path, allow_incomplete, |record, quote| {
        metrics.observe(record, quote)
    })?;
    if let Some(start) = metrics.disconnected_ns {
        update_max(&mut metrics.max_disconnected, metrics.last_ns - start);
    }
    let status = if !session.complete {
        InspectionStatus::Incomplete
    } else if session.end_reason.as_deref() == Some("failed") {
        InspectionStatus::Failed
    } else if metrics.two_sided == 0
        || session
            .feeds
            .as_ref()
            .is_some_and(|f| !f.all_required_fresh_observed)
    {
        InspectionStatus::NoUsableData
    } else if metrics.connection_errors > 0 {
        InspectionStatus::CompletedWithConnectionErrors
    } else {
        InspectionStatus::Completed
    };
    for channel in &mut metrics.channels {
        channel.report.snapshot_age_at_end_ns = channel.last_ns.map(|last| metrics.last_ns - last);
    }
    let feeds = session.feeds.as_ref().map(|f| FeedInspection {
        depth: f.depth.as_ref().map(|_| metrics.channels[0].report.clone()),
        bbo: f.bbo.as_ref().map(|_| metrics.channels[1].report.clone()),
    });
    let age_at_end = if feeds.is_some() {
        metrics
            .channels
            .iter()
            .filter_map(|c| c.report.snapshot_age_at_end_ns)
            .max()
    } else {
        metrics.last_snapshot_ns.map(|last| metrics.last_ns - last)
    };
    Ok(Inspection {
        status,
        session,
        file_bytes: storage.file_bytes,
        storage,
        recorded_duration_ns: metrics.last_ns - metrics.first_ns.unwrap_or(metrics.last_ns),
        successful_connections: metrics.successful_connections,
        connection_errors: metrics.connection_errors,
        two_sided_snapshots: metrics.two_sided,
        one_sided_snapshots: metrics.one_sided,
        max_snapshot_gap_ns: metrics.max_gap,
        max_first_snapshot_wait_ns: metrics.max_first_wait,
        max_disconnected_ns: metrics.max_disconnected,
        snapshot_age_at_end_ns: age_at_end,
        observed_source_clock_delta: metrics.clock_delta,
        feeds,
    })
}

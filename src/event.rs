use std::collections::BTreeMap;

use clap::ValueEnum;
use serde::{Deserialize, Serialize};

pub const SCHEMA_VERSION: u16 = 1;
pub const FEED_SCHEMA_VERSION: u16 = 2;
pub const MAX_RECORD_BYTES: usize = 4 * 1024 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
pub enum FeedKind {
    Depth,
    Bbo,
}

impl FeedKind {
    pub fn channel(self) -> &'static str {
        match self {
            Self::Depth => "l2Book",
            Self::Bbo => "bbo",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
pub enum FeedProfile {
    Depth,
    Bbo,
    Combined,
}

impl FeedProfile {
    pub fn includes(self, feed: FeedKind) -> bool {
        self == Self::Combined
            || matches!(
                (self, feed),
                (Self::Depth, FeedKind::Depth) | (Self::Bbo, FeedKind::Bbo)
            )
    }

    pub fn argument(self) -> &'static str {
        match self {
            Self::Depth => "depth",
            Self::Bbo => "bbo",
            Self::Combined => "combined",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FeedPolicy {
    pub profile: FeedProfile,
    pub depth_stale_after_ms: u64,
    pub bbo_stale_after_ms: u64,
    pub timer_interval_ms: u64,
}

impl FeedPolicy {
    pub fn validate(&self) -> anyhow::Result<()> {
        for value in [
            self.depth_stale_after_ms,
            self.bbo_stale_after_ms,
            self.timer_interval_ms,
        ] {
            anyhow::ensure!(
                value > 0 && value.checked_mul(1_000_000).is_some(),
                "feed timing is outside supported nanosecond range"
            );
        }
        anyhow::ensure!(
            self.timer_interval_ms <= 250,
            "feed timer interval must be at most 250 ms"
        );
        for feed in [FeedKind::Depth, FeedKind::Bbo] {
            anyhow::ensure!(
                !self.profile.includes(feed) || self.timer_interval_ms <= self.stale_after_ms(feed),
                "feed timer interval exceeds freshness threshold"
            );
        }
        Ok(())
    }

    pub fn stale_after_ms(&self, feed: FeedKind) -> u64 {
        match feed {
            FeedKind::Depth => self.depth_stale_after_ms,
            FeedKind::Bbo => self.bbo_stale_after_ms,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
pub enum Network {
    Mainnet,
    Testnet,
}

impl Network {
    pub fn endpoint(self) -> &'static str {
        match self {
            Self::Mainnet => "wss://api.hyperliquid.xyz/ws",
            Self::Testnet => "wss://api.hyperliquid-testnet.xyz/ws",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Record {
    pub schema_version: u16,
    /// Contiguous, starting at one. Ordering never depends on the wall clock.
    pub sequence: u64,
    pub local_time_ns: u64,
    pub monotonic_ns: u64,
    /// Zero for session events; one-based for connection attempts.
    pub connection_id: u64,
    pub event: Event,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Event {
    SessionStarted {
        coin: String,
        network: Network,
        application_version: String,
    },
    /// Explicit schema-2 session; never inferred from a received channel.
    FeedSessionStarted {
        coin: String,
        network: Network,
        application_version: String,
        policy: FeedPolicy,
    },
    /// Freshness uses this record's monotonic timestamp, never a replay clock.
    FeedTimer,
    ConnectionAttempt {
        endpoint: String,
    },
    TcpConnected,
    UpgradeRequest {
        method: String,
        uri: String,
        headers: BTreeMap<String, String>,
    },
    UpgradeResponse {
        status: u16,
        headers: BTreeMap<String, String>,
    },
    ConnectionOpened,
    TextSent {
        text: String,
    },
    TextReceived {
        text: String,
    },
    ControlReceived {
        kind: String,
        payload_hex: String,
    },
    ControlSent {
        kind: String,
        payload_hex: String,
    },
    ConnectionError {
        message: String,
    },
    ConnectionClosed {
        reason: String,
    },
    SessionEnded {
        reason: String,
    },
}

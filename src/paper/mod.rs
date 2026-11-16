//! Offline research model. Explicit assumed fills; no exchange execution adapter.
mod amount;
mod engine;
mod execution;
mod market;
mod replay;

use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};

pub use amount::Amount;
pub use engine::PaperEngine;
pub use execution::{
    ExecutionReport, ExecutionScenario, IocAssumptions, ScenarioOrder, export_execution_scenario,
};
pub use market::{MarketReplayReport, export_recorded_market};
pub use replay::{replay_paper, replay_paper_reader};

pub const PAPER_VERSION: u16 = 1;
/// Recorded-market, mark-only replay. Version 1 bytes and accounting are unchanged.
pub const RECORDED_PAPER_VERSION: u16 = 2;
pub const EXECUTION_PAPER_VERSION: u16 = 3;
pub const MAX_PAPER_RECORD_BYTES: usize = 64 * 1024;
pub const MAX_PAPER_RECORDS: u64 = 10000;
pub const MAX_PAPER_ORDERS: usize = 1000;
pub const MAX_PAPER_FILLS: usize = 5000;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, clap::ValueEnum)]
#[serde(rename_all = "snake_case")]
pub enum RecordingOrigin {
    CapturedPublicData,
    SyntheticFixture,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum PaperSource {
    Synthetic {
        label: String,
    },
    ManualSimulation {
        label: String,
    },
    RecordedMarket {
        label: String,
        origin: RecordingOrigin,
        recording_sha256: String,
        feed: crate::event::FeedKind,
        network: crate::event::Network,
    },
    RecordedExecution {
        label: String,
        origin: RecordingOrigin,
        recording_sha256: String,
        scenario_sha256: String,
        feed: crate::event::FeedKind,
        network: crate::event::Network,
        assumptions: Box<IocAssumptions>,
    },
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PaperConfig {
    pub source: PaperSource,
    pub coin: String,
    pub quote_currency: String,
    pub starting_collateral: Amount,
    /// An explicitly assumed fixed fee; never presented as the venue's fee tier.
    pub fee_rate: Amount,
    pub max_abs_position: Amount,
    pub max_order_notional: Amount,
    pub max_working_orders: u32,
    pub max_loss: Amount,
    pub stale_after_ms: u64,
}

impl PaperConfig {
    pub fn validate(&self) -> Result<()> {
        crate::hyperliquid::validate_coin(&self.coin)?;
        ensure!(
            self.quote_currency == "USDC",
            "paper model v1 requires USDC-denominated linear contracts"
        );
        let label = match &self.source {
            PaperSource::Synthetic { label } | PaperSource::ManualSimulation { label } => label,
            PaperSource::RecordedExecution {
                scenario_sha256,
                assumptions,
                ..
            } => {
                validate_digest(scenario_sha256)?;
                assumptions.validate()?;
                ensure!(
                    self.fee_rate == assumptions.fee_rate,
                    "paper fee differs from execution assumption"
                );
                let PaperSource::RecordedExecution {
                    label,
                    recording_sha256,
                    ..
                } = &self.source
                else {
                    unreachable!()
                };
                validate_digest(recording_sha256)?;
                ensure!(
                    !label.chars().any(char::is_control),
                    "invalid recorded source label"
                );
                label
            }
            PaperSource::RecordedMarket {
                label,
                recording_sha256,
                ..
            } => {
                validate_digest(recording_sha256)?;
                ensure!(
                    !label.chars().any(char::is_control),
                    "invalid recorded source label"
                );
                label
            }
        };
        ensure!(
            !label.is_empty() && label.len() <= 160,
            "paper source label must contain 1–160 bytes"
        );
        ensure!(
            self.starting_collateral.positive(),
            "starting collateral must be positive"
        );
        ensure!(
            self.fee_rate >= Amount::ZERO && self.fee_rate <= "0.01".parse()?,
            "assumed fee rate must be between 0 and 1%"
        );
        ensure!(
            self.max_abs_position.positive() && self.max_order_notional.positive(),
            "paper exposure limits must be positive"
        );
        ensure!(
            self.max_working_orders > 0 && self.max_working_orders as usize <= MAX_PAPER_ORDERS,
            "invalid working-order limit"
        );
        ensure!(
            self.max_loss.positive() && self.max_loss <= self.starting_collateral,
            "loss limit must be positive and no greater than starting collateral"
        );
        self.starting_collateral.subtract_exact(self.max_loss)?;
        ensure!(
            self.stale_after_ms > 0 && self.stale_after_ms.checked_mul(1_000_000).is_some(),
            "invalid paper freshness threshold"
        );
        Ok(())
    }
}

fn validate_digest(value: &str) -> Result<()> {
    ensure!(
        value.len() == 64
            && value
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "recorded source requires a lowercase SHA-256 digest"
    );
    Ok(())
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Side {
    Buy,
    Sell,
}

impl Side {
    fn signed(self, value: Amount) -> Amount {
        if self == Self::Buy {
            value
        } else {
            value.negated()
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum OrderStatus {
    PendingNew,
    Open,
    PartiallyFilled,
    PendingCancel,
    Filled,
    Cancelled,
    Rejected,
}

impl OrderStatus {
    pub fn working(self) -> bool {
        matches!(
            self,
            Self::PendingNew | Self::Open | Self::PartiallyFilled | Self::PendingCancel
        )
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RejectReason {
    Halted,
    MissingMarket,
    StaleMarket,
    WorkingOrderLimit,
    PositionLimit,
    OrderNotionalLimit,
    AdapterRejected,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Order {
    pub id: String,
    pub created_sequence: u64,
    pub side: Side,
    pub limit_price: Amount,
    pub quantity: Amount,
    pub filled_quantity: Amount,
    pub remaining_quantity: Amount,
    pub status: OrderStatus,
    pub accepted: bool,
    pub cancel_pending: bool,
    pub cancel_acknowledged: bool,
    pub rejection: Option<RejectReason>,
    pub rejection_detail: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PaperRecord {
    pub paper_schema_version: u16,
    pub sequence: u64,
    pub monotonic_ns: u64,
    pub event: PaperEvent,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum PaperEvent {
    SessionStarted {
        config: PaperConfig,
    },
    MarketObserved {
        bid: Amount,
        ask: Amount,
    },
    MarketDisconnected {
        reason: String,
    },
    Timer {},
    OrderRequested {
        id: String,
        side: Side,
        limit_price: Amount,
        quantity: Amount,
    },
    OrderAccepted {
        id: String,
    },
    OrderRejected {
        id: String,
        reason: String,
    },
    CancelRequested {
        id: String,
    },
    CancelAccepted {
        id: String,
    },
    CancelRejected {
        id: String,
        reason: String,
    },
    AssumedFill {
        fill_id: String,
        order_id: String,
        price: Amount,
        quantity: Amount,
    },
    Halt {
        reason: String,
    },
    SessionEnded {
        reason: String,
    },
}

impl PaperEvent {
    fn kind(&self) -> &'static str {
        match self {
            Self::SessionStarted { .. } => "session_started",
            Self::MarketObserved { .. } => "market_observed",
            Self::MarketDisconnected { .. } => "market_disconnected",
            Self::Timer {} => "timer",
            Self::OrderRequested { .. } => "order_requested",
            Self::OrderAccepted { .. } => "order_accepted",
            Self::OrderRejected { .. } => "order_rejected",
            Self::CancelRequested { .. } => "cancel_requested",
            Self::CancelAccepted { .. } => "cancel_accepted",
            Self::CancelRejected { .. } => "cancel_rejected",
            Self::AssumedFill { .. } => "assumed_fill",
            Self::Halt { .. } => "halt",
            Self::SessionEnded { .. } => "session_ended",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Lot {
    pub side: Side,
    pub quantity: Amount,
    pub entry_price: Amount,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Account {
    pub position_quantity: Amount,
    pub open_cost_basis: Amount,
    pub lot_count: u32,
    pub realized_pnl: Amount,
    pub fees: Amount,
    pub collateral_balance: Amount,
    pub mark_price: Option<Amount>,
    pub mark_fresh: bool,
    pub unrealized_pnl: Option<Amount>,
    pub equity: Option<Amount>,
    pub net_pnl: Option<Amount>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct RiskState {
    pub halted: bool,
    pub halt_reason: Option<String>,
    pub market_status: &'static str,
    pub working_orders: u32,
    pub worst_long_position: Amount,
    pub worst_short_position: Amount,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Fill {
    pub fill_id: String,
    pub order_id: String,
    pub side: Side,
    pub price: Amount,
    pub quantity: Amount,
    pub fee: Amount,
    pub realized_pnl: Amount,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct PaperUpdate {
    pub paper_model_version: u16,
    pub mode: &'static str,
    pub source: PaperSource,
    pub sequence: u64,
    pub monotonic_ns: u64,
    pub event_kind: &'static str,
    pub duplicate: bool,
    pub order: Option<Order>,
    pub assumed_fill: Option<Fill>,
    pub account: Account,
    pub risk: RiskState,
    pub complete: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct PaperReport {
    pub paper_model_version: u16,
    pub mode: &'static str,
    pub fill_model: &'static str,
    pub accounting_model: &'static str,
    pub config: PaperConfig,
    pub records: u64,
    pub assumed_fills: u64,
    pub duplicate_events: u64,
    pub orders: Vec<Order>,
    pub open_lots: Vec<Lot>,
    pub account: Account,
    pub risk: RiskState,
    pub complete: bool,
    pub end_reason: Option<String>,
}

//! Bounded, transactional research ledger. No I/O, clocks, randomness or floats.
use super::*;
use anyhow::{Context, Result, ensure};
use std::collections::{BTreeMap, VecDeque};

#[derive(Debug, Clone)]
struct Mark {
    price: Amount,
    monotonic_ns: u64,
}

#[derive(Debug, Clone, Default)]
pub struct PaperEngine {
    version: u16,
    config: Option<PaperConfig>,
    sequence: u64,
    monotonic_ns: u64,
    ended: bool,
    end_reason: Option<String>,
    market_connected: bool,
    mark: Option<Mark>,
    orders: BTreeMap<String, Order>,
    fills: BTreeMap<String, Fill>,
    lots: VecDeque<Lot>,
    realized: Amount,
    fees: Amount,
    halt_reason: Option<String>,
    duplicate_events: u64,
}

fn identity(value: &str) -> Result<()> {
    ensure!(
        !value.is_empty()
            && value.len() <= 64
            && value
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || b"_.-".contains(&c)),
        "paper identities require 1–64 plain identifier bytes"
    );
    Ok(())
}

fn reason(value: &str) -> Result<()> {
    ensure!(
        !value.is_empty() && value.len() <= 256 && !value.chars().any(char::is_control),
        "paper reason requires 1–256 printable bytes"
    );
    Ok(())
}

impl PaperEngine {
    /// Invalid/overflowing input cannot leave partially applied cash, fills or
    /// reservations. This first offline model uses a bounded transaction copy.
    pub fn apply(&mut self, record: &PaperRecord) -> Result<PaperUpdate> {
        ensure!(
            matches!(
                record.paper_schema_version,
                PAPER_VERSION | RECORDED_PAPER_VERSION | EXECUTION_PAPER_VERSION
            ),
            "unsupported paper schema version"
        );
        ensure!(
            self.version == 0 || self.version == record.paper_schema_version,
            "paper schema changed inside a session"
        );
        if record.paper_schema_version == RECORDED_PAPER_VERSION {
            ensure!(
                matches!(
                    record.event,
                    PaperEvent::SessionStarted { .. }
                        | PaperEvent::MarketObserved { .. }
                        | PaperEvent::MarketDisconnected { .. }
                        | PaperEvent::Timer { .. }
                        | PaperEvent::SessionEnded { .. }
                ),
                "recorded-market v2 is mark-only; orders and fills are disabled"
            );
        }
        ensure!(
            record.sequence == self.sequence + 1,
            "noncontiguous paper sequence"
        );
        ensure!(
            record.sequence <= MAX_PAPER_RECORDS,
            "paper record-count limit reached"
        );
        ensure!(
            record.monotonic_ns >= self.monotonic_ns,
            "paper monotonic time regressed"
        );
        ensure!(!self.ended, "paper event after session end");
        ensure!(
            self.config.is_some() || matches!(record.event, PaperEvent::SessionStarted { .. }),
            "paper session must start with configuration"
        );
        let mut next = self.clone();
        let update = next.apply_transaction(record)?;
        *self = next;
        Ok(update)
    }

    fn apply_transaction(&mut self, record: &PaperRecord) -> Result<PaperUpdate> {
        self.version = record.paper_schema_version;
        self.sequence = record.sequence;
        self.monotonic_ns = record.monotonic_ns;
        let mut changed = None;
        let mut assumed_fill = None;
        let mut duplicate = false;
        match &record.event {
            PaperEvent::SessionStarted { config } => {
                ensure!(
                    self.config.is_none() && record.sequence == 1,
                    "duplicate paper session start"
                );
                config.validate()?;
                ensure!(
                    matches!(
                        (&config.source, record.paper_schema_version),
                        (
                            PaperSource::Synthetic { .. } | PaperSource::ManualSimulation { .. },
                            PAPER_VERSION
                        ) | (PaperSource::RecordedMarket { .. }, RECORDED_PAPER_VERSION)
                            | (
                                PaperSource::RecordedExecution { .. },
                                EXECUTION_PAPER_VERSION
                            )
                    ),
                    "paper source and schema version disagree"
                );
                self.config = Some(config.clone());
            }
            PaperEvent::MarketObserved { bid, ask } => {
                ensure!(
                    bid.positive() && ask.positive() && bid < ask,
                    "paper market must have positive, uncrossed sides"
                );
                let mid =
                    bid.add_exact(ask.subtract_exact(*bid)?.multiply_exact("0.5".parse()?)?)?;
                self.mark = Some(Mark {
                    price: mid,
                    monotonic_ns: record.monotonic_ns,
                });
                self.market_connected = true;
            }
            PaperEvent::MarketDisconnected { reason: message } => {
                reason(message)?;
                self.market_connected = false;
            }
            PaperEvent::Timer {} => {}
            PaperEvent::OrderRequested {
                id,
                side,
                limit_price,
                quantity,
            } => {
                identity(id)?;
                ensure!(
                    limit_price.positive() && quantity.positive(),
                    "order price/quantity must be positive"
                );
                if let Some(existing) = self.orders.get(id) {
                    ensure!(
                        existing.side == *side
                            && existing.limit_price == *limit_price
                            && existing.quantity == *quantity,
                        "order identity was reused for different intent"
                    );
                    duplicate = true;
                    changed = Some(id.clone());
                } else {
                    ensure!(
                        self.orders.len() < MAX_PAPER_ORDERS,
                        "paper order-count limit reached"
                    );
                    let rejection = self.request_rejection(*side, *limit_price, *quantity)?;
                    self.orders.insert(
                        id.clone(),
                        Order {
                            id: id.clone(),
                            created_sequence: record.sequence,
                            side: *side,
                            limit_price: *limit_price,
                            quantity: *quantity,
                            filled_quantity: Amount::ZERO,
                            remaining_quantity: *quantity,
                            status: if rejection.is_some() {
                                OrderStatus::Rejected
                            } else {
                                OrderStatus::PendingNew
                            },
                            accepted: false,
                            cancel_pending: false,
                            cancel_acknowledged: false,
                            rejection,
                            rejection_detail: None,
                        },
                    );
                    changed = Some(id.clone());
                }
            }
            PaperEvent::OrderAccepted { id } => {
                let order = self.order_mut(id)?;
                if order.accepted {
                    duplicate = true;
                } else {
                    ensure!(
                        order.status == OrderStatus::PendingNew,
                        "acceptance outside pending-new order"
                    );
                    order.accepted = true;
                    order.status = OrderStatus::Open;
                }
                changed = Some(id.clone());
            }
            PaperEvent::OrderRejected {
                id,
                reason: message,
            } => {
                reason(message)?;
                let order = self.order_mut(id)?;
                if order.status == OrderStatus::Rejected
                    && order.rejection == Some(RejectReason::AdapterRejected)
                    && order.rejection_detail.as_deref() == Some(message.as_str())
                {
                    duplicate = true;
                } else {
                    ensure!(
                        order.status == OrderStatus::PendingNew,
                        "rejection outside pending-new order"
                    );
                    order.status = OrderStatus::Rejected;
                    order.rejection = Some(RejectReason::AdapterRejected);
                    order.rejection_detail = Some(message.clone());
                }
                changed = Some(id.clone());
            }
            PaperEvent::CancelRequested { id } => {
                let order = self.order_mut(id)?;
                if order.cancel_pending || order.cancel_acknowledged {
                    duplicate = true;
                } else {
                    ensure!(
                        matches!(
                            order.status,
                            OrderStatus::Open | OrderStatus::PartiallyFilled
                        ),
                        "cancel requires an acknowledged working order"
                    );
                    order.cancel_pending = true;
                    order.status = OrderStatus::PendingCancel;
                }
                changed = Some(id.clone());
            }
            PaperEvent::CancelAccepted { id } => {
                let order = self.order_mut(id)?;
                if order.cancel_acknowledged {
                    duplicate = true;
                } else {
                    ensure!(
                        order.cancel_pending
                            && matches!(
                                order.status,
                                OrderStatus::PendingCancel | OrderStatus::Filled
                            ),
                        "cancel acknowledgement without a pending request"
                    );
                    order.cancel_pending = false;
                    order.cancel_acknowledged = true;
                    if order.status != OrderStatus::Filled {
                        order.status = OrderStatus::Cancelled;
                    }
                }
                changed = Some(id.clone());
            }
            PaperEvent::CancelRejected {
                id,
                reason: message,
            } => {
                reason(message)?;
                let order = self.order_mut(id)?;
                ensure!(
                    order.cancel_pending
                        && matches!(
                            order.status,
                            OrderStatus::PendingCancel | OrderStatus::Filled
                        ),
                    "cancel rejection without a pending request"
                );
                order.cancel_pending = false;
                order.rejection_detail = Some(message.clone());
                if order.status != OrderStatus::Filled {
                    order.status = if order.filled_quantity.positive() {
                        OrderStatus::PartiallyFilled
                    } else {
                        OrderStatus::Open
                    };
                }
                changed = Some(id.clone());
            }
            PaperEvent::AssumedFill {
                fill_id,
                order_id,
                price,
                quantity,
            } => {
                identity(fill_id)?;
                ensure!(
                    price.positive() && quantity.positive(),
                    "assumed fill price/quantity must be positive"
                );
                if let Some(previous) = self.fills.get(fill_id) {
                    ensure!(
                        previous.order_id == *order_id
                            && previous.price == *price
                            && previous.quantity == *quantity,
                        "fill identity was reused for different execution"
                    );
                    duplicate = true;
                    assumed_fill = Some(previous.clone());
                } else {
                    ensure!(
                        self.fills.len() < MAX_PAPER_FILLS,
                        "paper fill-count limit reached"
                    );
                    let order = self
                        .orders
                        .get(order_id)
                        .context("assumed fill references unknown order")?;
                    ensure!(
                        matches!(
                            order.status,
                            OrderStatus::Open
                                | OrderStatus::PartiallyFilled
                                | OrderStatus::PendingCancel
                        ),
                        "fill requires an acknowledged working order"
                    );
                    ensure!(
                        *quantity <= order.remaining_quantity,
                        "assumed fill exceeds remaining order quantity"
                    );
                    ensure!(
                        if order.side == Side::Buy {
                            *price <= order.limit_price
                        } else {
                            *price >= order.limit_price
                        },
                        "assumed fill violates limit price"
                    );
                    let side = order.side;
                    let fee = price
                        .multiply_exact(*quantity)?
                        .multiply_exact(self.config()?.fee_rate)?;
                    let realized = self.apply_lots(side, *price, *quantity)?;
                    self.realized = self.realized.add_exact(realized)?;
                    self.fees = self.fees.add_exact(fee)?;
                    let order = self.order_mut(order_id)?;
                    order.filled_quantity = order.filled_quantity.add_exact(*quantity)?;
                    order.remaining_quantity =
                        order.remaining_quantity.subtract_exact(*quantity)?;
                    if order.remaining_quantity == Amount::ZERO {
                        order.status = OrderStatus::Filled;
                    } else if !order.cancel_pending {
                        order.status = OrderStatus::PartiallyFilled;
                    }
                    let fill = Fill {
                        fill_id: fill_id.clone(),
                        order_id: order_id.clone(),
                        side,
                        price: *price,
                        quantity: *quantity,
                        fee,
                        realized_pnl: realized,
                    };
                    self.fills.insert(fill_id.clone(), fill.clone());
                    assumed_fill = Some(fill);
                }
                changed = Some(order_id.clone());
            }
            PaperEvent::Halt { reason: message } => {
                reason(message)?;
                if self.halt_reason.is_some() {
                    duplicate = true;
                } else {
                    self.halt_reason = Some(format!("manual: {message}"));
                }
            }
            PaperEvent::SessionEnded { reason: message } => {
                reason(message)?;
                self.ended = true;
                self.end_reason = Some(message.clone());
                self.market_connected = false;
            }
        }
        if duplicate {
            self.duplicate_events += 1;
        }
        let account = self.account()?;
        let loss_floor = self
            .config()?
            .starting_collateral
            .subtract_exact(self.config()?.max_loss)?;
        if self.halt_reason.is_none() && account.equity.is_some_and(|equity| equity <= loss_floor) {
            self.halt_reason = Some("session_loss_limit".into());
        }
        Ok(PaperUpdate {
            paper_model_version: self.version,
            mode: "paper",
            source: self.config()?.source.clone(),
            sequence: record.sequence,
            monotonic_ns: record.monotonic_ns,
            event_kind: record.event.kind(),
            duplicate,
            order: changed.map(|id| self.orders[&id].clone()),
            assumed_fill,
            account,
            risk: self.risk()?,
            complete: self.ended,
        })
    }

    fn config(&self) -> Result<&PaperConfig> {
        self.config
            .as_ref()
            .context("paper session has not started")
    }
    fn order_mut(&mut self, id: &str) -> Result<&mut Order> {
        self.orders.get_mut(id).context("unknown paper order")
    }

    fn market_status(&self) -> &'static str {
        match &self.mark {
            None => "missing",
            Some(_) if !self.market_connected => "disconnected",
            Some(mark)
                if self.monotonic_ns - mark.monotonic_ns
                    >= self
                        .config
                        .as_ref()
                        .expect("market requires session")
                        .stale_after_ms
                        * 1_000_000 =>
            {
                "stale"
            }
            Some(_) => "fresh",
        }
    }

    fn position(&self) -> Result<Amount> {
        self.lots.iter().try_fold(Amount::ZERO, |sum, lot| {
            sum.add_exact(lot.side.signed(lot.quantity))
        })
    }

    pub fn account(&self) -> Result<Account> {
        let config = self.config()?;
        let position = self.position()?;
        let cost = self.lots.iter().try_fold(Amount::ZERO, |sum, lot| {
            sum.add_exact(lot.quantity.multiply_exact(lot.entry_price)?)
        })?;
        let balance = config
            .starting_collateral
            .add_exact(self.realized)?
            .subtract_exact(self.fees)?;
        let unrealized = if self.lots.is_empty() {
            Some(Amount::ZERO)
        } else if let Some(mark) = &self.mark {
            Some(self.lots.iter().try_fold(Amount::ZERO, |sum, lot| {
                let change = if lot.side == Side::Buy {
                    mark.price.subtract_exact(lot.entry_price)?
                } else {
                    lot.entry_price.subtract_exact(mark.price)?
                };
                sum.add_exact(change.multiply_exact(lot.quantity)?)
            })?)
        } else {
            None
        };
        let equity = unrealized.map(|pnl| balance.add_exact(pnl)).transpose()?;
        Ok(Account {
            position_quantity: position,
            open_cost_basis: cost,
            lot_count: self.lots.len().try_into()?,
            realized_pnl: self.realized,
            fees: self.fees,
            collateral_balance: balance,
            mark_price: self.mark.as_ref().map(|mark| mark.price),
            mark_fresh: self.market_status() == "fresh",
            unrealized_pnl: unrealized,
            equity,
            net_pnl: equity
                .map(|value| value.subtract_exact(config.starting_collateral))
                .transpose()?,
        })
    }

    pub fn risk(&self) -> Result<RiskState> {
        let position = self.position()?;
        let mut long = position;
        let mut short = position;
        let mut working = 0;
        for order in self.orders.values().filter(|order| order.status.working()) {
            working += 1;
            if order.side == Side::Buy {
                long = long.add_exact(order.remaining_quantity)?;
            } else {
                short = short.subtract_exact(order.remaining_quantity)?;
            }
        }
        Ok(RiskState {
            halted: self.halt_reason.is_some(),
            halt_reason: self.halt_reason.clone(),
            market_status: self.market_status(),
            working_orders: working,
            worst_long_position: long,
            worst_short_position: short,
        })
    }

    fn request_rejection(
        &self,
        side: Side,
        price: Amount,
        quantity: Amount,
    ) -> Result<Option<RejectReason>> {
        let config = self.config()?;
        let risk = self.risk()?;
        if risk.halted {
            return Ok(Some(RejectReason::Halted));
        }
        match risk.market_status {
            "missing" | "disconnected" => return Ok(Some(RejectReason::MissingMarket)),
            "stale" => return Ok(Some(RejectReason::StaleMarket)),
            _ => {}
        }
        if risk.working_orders >= config.max_working_orders {
            return Ok(Some(RejectReason::WorkingOrderLimit));
        }
        if price.multiply_exact(quantity)? > config.max_order_notional {
            return Ok(Some(RejectReason::OrderNotionalLimit));
        }
        let worst = if side == Side::Buy {
            risk.worst_long_position.add_exact(quantity)?
        } else {
            risk.worst_short_position.subtract_exact(quantity)?
        };
        if worst.abs() > config.max_abs_position {
            return Ok(Some(RejectReason::PositionLimit));
        }
        Ok(None)
    }

    fn apply_lots(&mut self, side: Side, price: Amount, quantity: Amount) -> Result<Amount> {
        let mut remaining = quantity;
        let mut realized = Amount::ZERO;
        while remaining.positive() && self.lots.front().is_some_and(|lot| lot.side != side) {
            let lot = self.lots.front_mut().expect("front was checked");
            let closed = remaining.min(lot.quantity);
            let change = if lot.side == Side::Buy {
                price.subtract_exact(lot.entry_price)?
            } else {
                lot.entry_price.subtract_exact(price)?
            };
            realized = realized.add_exact(change.multiply_exact(closed)?)?;
            lot.quantity = lot.quantity.subtract_exact(closed)?;
            remaining = remaining.subtract_exact(closed)?;
            if lot.quantity == Amount::ZERO {
                self.lots.pop_front();
            }
        }
        if remaining.positive() {
            self.lots.push_back(Lot {
                side,
                quantity: remaining,
                entry_price: price,
            });
        }
        Ok(realized)
    }

    pub fn report(&self) -> Result<PaperReport> {
        Ok(PaperReport {
            paper_model_version: self.version,
            mode: "paper",
            fill_model: if self.version == EXECUTION_PAPER_VERSION {
                "assumed_next_fresh_quote_ioc_v1"
            } else if self.version == RECORDED_PAPER_VERSION {
                "disabled_market_marks_only"
            } else {
                "explicit_assumed_fills"
            },
            accounting_model: "linear_contract_fifo_v1",
            config: self.config()?.clone(),
            records: self.sequence,
            assumed_fills: self.fills.len().try_into()?,
            duplicate_events: self.duplicate_events,
            orders: self.orders.values().cloned().collect(),
            open_lots: self.lots.iter().cloned().collect(),
            account: self.account()?,
            risk: self.risk()?,
            complete: self.ended,
            end_reason: self.end_reason.clone(),
        })
    }
}

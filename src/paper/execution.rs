//! Controlled offline IOC scenarios. All acknowledgements and fills are assumptions.
use super::market::{MarketLink, new_directory, new_file, write_line};
use super::*;
use crate::event::{Event, FeedKind};
use crate::hyperliquid::{FeedMessage, parse_feed_message};
use crate::journal::replay_path_observed;
use anyhow::{Context, Result, ensure};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File};
use std::io::{BufRead, BufReader, Read, Write};
use std::path::Path;

const MAX_SCENARIO_BYTES: usize = 64 * 1024;
const MAX_SCENARIO_ORDERS: usize = 64;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IocAssumptions {
    pub fee_rate: Amount,
    pub slippage_bps: Amount,
    pub top_size_fraction: Amount,
    pub latency_ms: u64,
    pub quote_wait_ms: u64,
}

impl IocAssumptions {
    pub fn validate(&self) -> Result<()> {
        ensure!(
            self.fee_rate >= Amount::ZERO && self.fee_rate <= "0.01".parse()?,
            "assumed fee outside 0–1% range"
        );
        ensure!(
            self.slippage_bps >= Amount::ZERO && self.slippage_bps <= "1000".parse()?,
            "assumed adverse slippage outside 0–1000 bps range"
        );
        ensure!(
            self.top_size_fraction.positive() && self.top_size_fraction <= "1".parse()?,
            "top-size fraction must be in (0,1]"
        );
        ensure!(
            self.latency_ms <= 60_000 && self.quote_wait_ms > 0 && self.quote_wait_ms <= 60_000,
            "invalid assumed timing window"
        );
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ScenarioOrder {
    pub id: String,
    /// Submit after processing this original market event. Never a paper sequence.
    pub after_market_sequence: u64,
    pub side: Side,
    pub limit_price: Amount,
    pub quantity: Amount,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExecutionScenario {
    pub scenario_version: u16,
    pub label: String,
    pub assumptions: IocAssumptions,
    pub starting_collateral: Amount,
    pub max_abs_position: Amount,
    pub max_order_notional: Amount,
    pub max_working_orders: u32,
    pub max_loss: Amount,
    pub orders: Vec<ScenarioOrder>,
}

impl ExecutionScenario {
    pub fn validate(&self) -> Result<()> {
        ensure!(
            self.scenario_version == 1,
            "unsupported execution scenario version"
        );
        ensure!(
            !self.label.is_empty()
                && self.label.len() <= 160
                && !self.label.chars().any(char::is_control),
            "invalid scenario label"
        );
        self.assumptions.validate()?;
        ensure!(
            !self.orders.is_empty() && self.orders.len() <= MAX_SCENARIO_ORDERS,
            "scenario requires 1–64 fixed orders"
        );
        let mut ids = BTreeSet::new();
        let mut previous = 0;
        for order in &self.orders {
            ensure!(
                !order.id.is_empty()
                    && order.id.len() <= 48
                    && order
                        .id
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b"_.-".contains(&b)),
                "invalid scenario order identity"
            );
            ensure!(ids.insert(&order.id), "duplicate scenario order identity");
            ensure!(
                order.after_market_sequence > 0 && order.after_market_sequence >= previous,
                "scenario orders must be sorted by original market sequence"
            );
            ensure!(
                order.limit_price.positive() && order.quantity.positive(),
                "scenario price and quantity must be positive"
            );
            previous = order.after_market_sequence;
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ExecutionCosts {
    pub spread_cost: Amount,
    pub slippage_cost: Amount,
    pub fees: Amount,
}

impl Default for ExecutionCosts {
    fn default() -> Self {
        Self {
            spread_cost: Amount::ZERO,
            slippage_cost: Amount::ZERO,
            fees: Amount::ZERO,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ExecutionStep {
    pub paper_sequence: u64,
    pub market_sequence: u64,
    pub phase: &'static str,
    pub order_id: Option<String>,
    pub arrival_ns: Option<u64>,
    pub expiry_ns: Option<u64>,
    pub touch_price: Option<Amount>,
    pub available_quantity: Option<Amount>,
    pub spread_cost: Amount,
    pub slippage_cost: Amount,
    pub fee: Amount,
    pub cumulative_costs: ExecutionCosts,
}

impl ExecutionStep {
    fn new(phase: &'static str, order_id: Option<String>) -> Self {
        Self {
            paper_sequence: 0,
            market_sequence: 0,
            phase,
            order_id,
            arrival_ns: None,
            expiry_ns: None,
            touch_price: None,
            available_quantity: None,
            spread_cost: Amount::ZERO,
            slippage_cost: Amount::ZERO,
            fee: Amount::ZERO,
            cumulative_costs: ExecutionCosts::default(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ExecutionReport {
    pub execution_model_version: u16,
    pub mode: &'static str,
    pub market: MarketReplayReport,
    pub scenario: ExecutionScenario,
    pub scenario_sha256: String,
    pub paper: PaperReport,
    pub spread_cost: Amount,
    pub slippage_cost: Amount,
    pub fees: Amount,
    pub pending_order_ids: Vec<String>,
    pub scenario_orders_enabled: bool,
    pub strategy_enabled: bool,
    pub full_window_verified: bool,
}

#[derive(Debug, Clone)]
struct Top {
    connection: u64,
    exchange_ms: u64,
    bid: Amount,
    ask: Amount,
    bid_size: Amount,
    ask_size: Amount,
}

#[derive(Debug, Default)]
struct Liquidity {
    top: Option<Top>,
    bid_left: Amount,
    ask_left: Amount,
}

impl Liquidity {
    fn observe(&mut self, top: &Top, fraction: Amount) -> Result<()> {
        let bid = top.bid_size.multiply_exact(fraction)?;
        let ask = top.ask_size.multiply_exact(fraction)?;
        match &self.top {
            Some(old) if old.connection == top.connection && old.exchange_ms == top.exchange_ms => {
                if old.bid == top.bid && old.ask == top.ask {
                    self.bid_left = self.bid_left.min(bid);
                    self.ask_left = self.ask_left.min(ask);
                } else {
                    // Ambiguous equal-time price changes cannot replenish liquidity.
                    self.bid_left = Amount::ZERO;
                    self.ask_left = Amount::ZERO;
                }
            }
            _ => {
                self.bid_left = bid;
                self.ask_left = ask;
            }
        }
        self.top = Some(top.clone());
        Ok(())
    }
}

#[derive(Clone)]
struct Pending {
    order: ScenarioOrder,
    sent_sequence: u64,
    arrival: u64,
    expiry: u64,
}

struct Writer {
    engine: PaperEngine,
    records: File,
    updates: File,
    links: File,
    trace: File,
    budget: usize,
    sequence: u64,
    costs: ExecutionCosts,
}

impl Writer {
    fn emit(
        &mut self,
        event: PaperEvent,
        source: &MarketLink,
        mut step: ExecutionStep,
    ) -> Result<PaperUpdate> {
        let sequence = self.sequence + 1;
        let record = PaperRecord {
            paper_schema_version: EXECUTION_PAPER_VERSION,
            sequence,
            monotonic_ns: source.monotonic_ns,
            event,
        };
        write_line(&mut self.records, &record, &mut self.budget)?;
        self.records.sync_data()?;
        let update = self.engine.apply(&record)?;
        self.costs.spread_cost = self.costs.spread_cost.add_exact(step.spread_cost)?;
        self.costs.slippage_cost = self.costs.slippage_cost.add_exact(step.slippage_cost)?;
        self.costs.fees = self.costs.fees.add_exact(step.fee)?;
        step.cumulative_costs = self.costs.clone();
        let mut link = source.clone();
        link.paper_sequence = sequence;
        if step.phase != "market" {
            link.quote = None;
        }
        step.paper_sequence = sequence;
        step.market_sequence = source.market_sequence;
        write_line(&mut self.updates, &update, &mut self.budget)?;
        write_line(&mut self.links, &link, &mut self.budget)?;
        write_line(&mut self.trace, &step, &mut self.budget)?;
        self.sequence = sequence;
        Ok(update)
    }
}

fn read_lines<T: serde::de::DeserializeOwned>(path: &Path) -> Result<Vec<T>> {
    ensure!(
        fs::metadata(path)?.len() <= 32 * 1024 * 1024,
        "derived artifact exceeds input bound"
    );
    BufReader::new(File::open(path)?)
        .lines()
        .map(|line| {
            let line = line?;
            ensure!(
                line.len() <= MAX_PAPER_RECORD_BYTES,
                "derived line exceeds input bound"
            );
            Ok(serde_json::from_str(&line)?)
        })
        .collect()
}

fn tops(
    market_path: &Path,
    market: &MarketReplayReport,
    feed: FeedKind,
) -> Result<BTreeMap<u64, Top>> {
    let policy = &market
        .source_report
        .feeds
        .as_ref()
        .context("missing feed policy")?
        .policy;
    let coin = &market.paper.config.coin;
    let mut result = BTreeMap::new();
    replay_path_observed(market_path, false, |record, observation| {
        if let Some(observation) = observation
            && observation.source() == Some(feed)
            && let Some(quote) = observation.quote()
            && quote.mid.is_some()
            && let Event::TextReceived { text } = &record.event
            && let FeedMessage::Book(kind, book) = parse_feed_message(text, coin, policy)?
        {
            ensure!(kind == feed, "normalized quote and source book disagree");
            let bid = book.bids.first().context("missing source bid")?;
            let ask = book.asks.first().context("missing source ask")?;
            result.insert(
                record.sequence,
                Top {
                    connection: record.connection_id,
                    exchange_ms: book.exchange_time_ms,
                    bid: bid.price.to_string().parse()?,
                    ask: ask.price.to_string().parse()?,
                    bid_size: bid.size.to_string().parse()?,
                    ask_size: ask.size.to_string().parse()?,
                },
            );
        }
        Ok(())
    })?;
    Ok(result)
}

fn attempt_ioc(
    writer: &mut Writer,
    pending: &Pending,
    source: &MarketLink,
    top: &Top,
    liquidity: &mut Liquidity,
    model: &IocAssumptions,
) -> Result<(Amount, Amount, Amount)> {
    let order = &pending.order;
    let mut ack = ExecutionStep::new("assumed_accept", Some(order.id.clone()));
    ack.arrival_ns = Some(pending.arrival);
    ack.expiry_ns = Some(pending.expiry);
    writer.emit(
        PaperEvent::OrderAccepted {
            id: order.id.clone(),
        },
        source,
        ack,
    )?;
    let touch = if order.side == Side::Buy {
        top.ask
    } else {
        top.bid
    };
    let rate = model.slippage_bps.multiply_exact("0.0001".parse()?)?;
    let adjustment = touch.multiply_exact(rate)?;
    let price = if order.side == Side::Buy {
        touch.add_exact(adjustment)?
    } else {
        touch.subtract_exact(adjustment)?
    };
    let capacity = if order.side == Side::Buy {
        liquidity.ask_left
    } else {
        liquidity.bid_left
    };
    let marketable = if order.side == Side::Buy {
        price <= order.limit_price
    } else {
        price >= order.limit_price
    };
    let filled = if marketable {
        order.quantity.min(capacity)
    } else {
        Amount::ZERO
    };
    let mut spread = Amount::ZERO;
    let mut slippage = Amount::ZERO;
    let mut fee = Amount::ZERO;
    if filled.positive() {
        let mid = top.bid.add_exact(
            top.ask
                .subtract_exact(top.bid)?
                .multiply_exact("0.5".parse()?)?,
        )?;
        spread = touch.subtract_exact(mid)?.abs().multiply_exact(filled)?;
        slippage = adjustment.multiply_exact(filled)?;
        fee = price
            .multiply_exact(filled)?
            .multiply_exact(model.fee_rate)?;
        let mut step = ExecutionStep::new("assumed_fill", Some(order.id.clone()));
        step.arrival_ns = Some(pending.arrival);
        step.expiry_ns = Some(pending.expiry);
        step.touch_price = Some(touch);
        step.available_quantity = Some(capacity);
        step.spread_cost = spread;
        step.slippage_cost = slippage;
        step.fee = fee;
        writer.emit(
            PaperEvent::AssumedFill {
                fill_id: format!("ioc-{}", order.id),
                order_id: order.id.clone(),
                price,
                quantity: filled,
            },
            source,
            step,
        )?;
        if order.side == Side::Buy {
            liquidity.ask_left = liquidity.ask_left.subtract_exact(filled)?;
        } else {
            liquidity.bid_left = liquidity.bid_left.subtract_exact(filled)?;
        }
    }
    if filled < order.quantity {
        writer.emit(
            PaperEvent::CancelRequested {
                id: order.id.clone(),
            },
            source,
            ExecutionStep::new("ioc_remainder_cancel", Some(order.id.clone())),
        )?;
        writer.emit(
            PaperEvent::CancelAccepted {
                id: order.id.clone(),
            },
            source,
            ExecutionStep::new("assumed_cancel_ack", Some(order.id.clone())),
        )?;
    }
    Ok((spread, slippage, fee))
}

/// No strategies or venue actions. All decisions depend on past/current source
/// records and a predeclared scenario; derived inputs sync before ledger updates.
pub fn export_execution_scenario(
    input: &Path,
    scenario_path: &Path,
    output: &Path,
    origin: RecordingOrigin,
    feed: FeedKind,
) -> Result<ExecutionReport> {
    let mut raw = Vec::new();
    File::open(scenario_path)?
        .take((MAX_SCENARIO_BYTES + 1) as u64)
        .read_to_end(&mut raw)?;
    ensure!(
        raw.len() <= MAX_SCENARIO_BYTES,
        "scenario exceeds 64 KiB limit"
    );
    let scenario: ExecutionScenario =
        serde_json::from_slice(&raw).context("invalid execution scenario")?;
    scenario.validate()?;
    let scenario_sha256 = format!("{:x}", Sha256::digest(&raw));
    let input = input.canonicalize()?;
    let parent = output
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."))
        .canonicalize()?;
    let output = parent.join(
        output
            .file_name()
            .context("new output directory required")?,
    );
    ensure!(
        !output.starts_with(&input),
        "output must be outside source recording"
    );
    new_directory(&output)?;
    let mut stored_scenario = new_file(&output.join("scenario.json"))?;
    stored_scenario.write_all(&raw)?;
    stored_scenario.sync_all()?;
    let market_path = output.join("market");
    let market = export_recorded_market(&input, &market_path, origin, feed)?;
    ensure!(
        market.source_report.records + scenario.orders.len() as u64 * 6 < MAX_PAPER_RECORDS,
        "scenario could exceed the 10,000 paper-event limit"
    );
    ensure!(
        scenario
            .orders
            .iter()
            .all(|o| o.after_market_sequence < market.source_report.records),
        "scenario order refers to source end or an unknown market sequence"
    );
    let PaperSource::RecordedMarket { network, .. } = market.paper.config.source else {
        unreachable!()
    };
    let config = PaperConfig {
        source: PaperSource::RecordedExecution {
            label: scenario.label.clone(),
            origin,
            recording_sha256: market.source.recording_sha256.clone(),
            scenario_sha256: scenario_sha256.clone(),
            feed,
            network,
            assumptions: Box::new(scenario.assumptions.clone()),
        },
        coin: market.paper.config.coin.clone(),
        quote_currency: "USDC".into(),
        starting_collateral: scenario.starting_collateral,
        fee_rate: scenario.assumptions.fee_rate,
        max_abs_position: scenario.max_abs_position,
        max_order_notional: scenario.max_order_notional,
        max_working_orders: scenario.max_working_orders,
        max_loss: scenario.max_loss,
        stale_after_ms: market.paper.config.stale_after_ms,
    };
    config.validate()?;
    let records: Vec<PaperRecord> = read_lines(&market_path.join("paper-input.jsonl"))?;
    let links: Vec<MarketLink> = read_lines(&market_path.join("market-links.jsonl"))?;
    ensure!(
        records.len() == links.len() && records.len() as u64 == market.source_report.records + 1,
        "market replay records and links disagree"
    );
    let books = tops(&market_path.join("source"), &market, feed)?;
    let mut writer = Writer {
        engine: PaperEngine::default(),
        sequence: 0,
        costs: ExecutionCosts::default(),
        budget: 0,
        records: new_file(&output.join("paper-input.jsonl"))?,
        updates: new_file(&output.join("paper-updates.jsonl"))?,
        links: new_file(&output.join("market-links.jsonl"))?,
        trace: new_file(&output.join("execution-trace.jsonl"))?,
    };
    let mut pending: Vec<Pending> = Vec::new();
    let mut liquidity = Liquidity::default();
    let mut spread_cost = Amount::ZERO;
    let mut slippage_cost = Amount::ZERO;
    let mut fees = Amount::ZERO;
    for (base, source) in records.iter().zip(&links) {
        ensure!(
            base.sequence == source.paper_sequence && base.monotonic_ns == source.monotonic_ns,
            "market replay time or sequence changed"
        );
        let event = if base.sequence == 1 {
            PaperEvent::SessionStarted {
                config: config.clone(),
            }
        } else {
            base.event.clone()
        };
        writer.emit(
            event,
            source,
            ExecutionStep::new(
                if source.generated_end {
                    "replay_end"
                } else {
                    "market"
                },
                None,
            ),
        )?;
        if source.generated_end {
            continue;
        }
        let top = if matches!(base.event, PaperEvent::MarketObserved { .. }) {
            books.get(&source.market_sequence)
        } else {
            None
        };
        if let Some(top) = top {
            liquidity.observe(top, scenario.assumptions.top_size_fraction)?;
        }
        let mut keep = Vec::new();
        for waiting in pending {
            if source.monotonic_ns >= waiting.expiry {
                let mut step =
                    ExecutionStep::new("assumed_expiry_reject", Some(waiting.order.id.clone()));
                step.arrival_ns = Some(waiting.arrival);
                step.expiry_ns = Some(waiting.expiry);
                writer.emit(
                    PaperEvent::OrderRejected {
                        id: waiting.order.id,
                        reason: "simulated IOC expired before a usable quote".into(),
                    },
                    source,
                    step,
                )?;
            } else if source.monotonic_ns >= waiting.arrival
                && source.market_sequence > waiting.sent_sequence
                && let Some(top) = top
            {
                let (spread, slippage, fee) = attempt_ioc(
                    &mut writer,
                    &waiting,
                    source,
                    top,
                    &mut liquidity,
                    &scenario.assumptions,
                )?;
                spread_cost = spread_cost.add_exact(spread)?;
                slippage_cost = slippage_cost.add_exact(slippage)?;
                fees = fees.add_exact(fee)?;
            } else {
                keep.push(waiting);
            }
        }
        pending = keep;
        for order in scenario
            .orders
            .iter()
            .filter(|o| o.after_market_sequence == source.market_sequence)
        {
            let arrival = source
                .monotonic_ns
                .checked_add(scenario.assumptions.latency_ms * 1_000_000)
                .context("arrival time overflow")?;
            let expiry = arrival
                .checked_add(scenario.assumptions.quote_wait_ms * 1_000_000)
                .context("expiry time overflow")?;
            let mut step = ExecutionStep::new("scenario_request", Some(order.id.clone()));
            step.arrival_ns = Some(arrival);
            step.expiry_ns = Some(expiry);
            let update = writer.emit(
                PaperEvent::OrderRequested {
                    id: order.id.clone(),
                    side: order.side,
                    limit_price: order.limit_price,
                    quantity: order.quantity,
                },
                source,
                step,
            )?;
            if update
                .order
                .as_ref()
                .is_some_and(|o| o.status == OrderStatus::PendingNew)
            {
                pending.push(Pending {
                    order: order.clone(),
                    sent_sequence: source.market_sequence,
                    arrival,
                    expiry,
                });
            }
        }
    }
    writer.records.sync_all()?;
    writer.updates.sync_all()?;
    writer.links.sync_all()?;
    writer.trace.sync_all()?;
    let paper = writer.engine.report()?;
    ensure!(
        paper.complete && paper.account.fees == fees,
        "execution ledger and fee totals disagree"
    );
    let report = ExecutionReport {
        execution_model_version: 1,
        mode: "offline_controlled_ioc",
        market,
        scenario,
        scenario_sha256,
        paper,
        spread_cost,
        slippage_cost,
        fees,
        pending_order_ids: pending.iter().map(|p| p.order.id.clone()).collect(),
        scenario_orders_enabled: true,
        strategy_enabled: false,
        full_window_verified: false,
    };
    let mut paper_report = new_file(&output.join("paper-report.json"))?;
    write_line(&mut paper_report, &report.paper, &mut writer.budget)?;
    paper_report.sync_all()?;
    let mut success = new_file(&output.join("execution-replay.json"))?;
    write_line(&mut success, &report, &mut writer.budget)?;
    success.sync_all()?;
    Ok(report)
}

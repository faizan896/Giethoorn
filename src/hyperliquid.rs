//! Hyperliquid l2Book messages contain complete depth snapshots, not deltas.

use anyhow::{Context, Result, bail, ensure};
use rust_decimal::Decimal;
use serde::Deserialize;
use serde_json::{Value, json};

use crate::event::{FeedKind, FeedPolicy};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Level {
    pub price: Decimal,
    pub size: Decimal,
    pub orders: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Book {
    pub exchange_time_ms: u64,
    pub bids: Vec<Level>,
    pub asks: Vec<Level>,
}

#[derive(Debug, PartialEq, Eq)]
pub enum MarketMessage {
    Book(Book),
    Other,
}

#[derive(Deserialize)]
struct WireBook {
    coin: String,
    time: u64,
    levels: [Vec<WireLevel>; 2],
}

#[derive(Deserialize)]
struct WireLevel {
    px: String,
    sz: String,
    n: u64,
}

#[derive(Deserialize)]
struct WireBbo {
    coin: String,
    time: u64,
    bbo: [Option<WireLevel>; 2],
}

#[derive(Debug, PartialEq, Eq)]
pub enum FeedMessage {
    Book(FeedKind, Book),
    Acknowledged(FeedKind),
    Other,
}

pub fn feed_subscription(coin: &str, feed: FeedKind) -> String {
    json!({"method":"subscribe","subscription":{"type":feed.channel(),"coin":coin}}).to_string()
}

pub fn parse_feed_message(
    text: &str,
    expected_coin: &str,
    policy: &FeedPolicy,
) -> Result<FeedMessage> {
    if text == "Websocket connection established." {
        return Ok(FeedMessage::Other);
    }
    let value: Value = serde_json::from_str(text).context("invalid WebSocket JSON")?;
    let channel = value
        .get("channel")
        .and_then(Value::as_str)
        .context("message has no channel")?;
    let kind = match channel {
        "l2Book" => Some(FeedKind::Depth),
        "bbo" => Some(FeedKind::Bbo),
        _ => None,
    };
    if let Some(kind) = kind {
        ensure!(policy.profile.includes(kind), "received an unselected feed");
        if kind == FeedKind::Depth {
            let MarketMessage::Book(book) = parse_message(text, expected_coin)? else {
                unreachable!()
            };
            return Ok(FeedMessage::Book(kind, book));
        }
        let data: WireBbo =
            serde_json::from_value(value.get("data").context("bbo has no data")?.clone())
                .context("invalid bbo shape")?;
        ensure!(
            data.coin == expected_coin,
            "received BBO for unexpected coin {}",
            data.coin
        );
        ensure!(data.time > 0, "exchange timestamp must be positive");
        let [bid, ask] = data.bbo;
        let bids = parse_side(bid.into_iter().collect(), true)?;
        let asks = parse_side(ask.into_iter().collect(), false)?;
        if let (Some(bid), Some(ask)) = (bids.first(), asks.first()) {
            ensure!(bid.price < ask.price, "locked or crossed BBO");
        }
        return Ok(FeedMessage::Book(
            kind,
            Book {
                exchange_time_ms: data.time,
                bids,
                asks,
            },
        ));
    }
    if channel == "subscriptionResponse" {
        let data = value
            .get("data")
            .context("subscription response has no data")?;
        ensure!(
            data.get("method").and_then(Value::as_str) == Some("subscribe"),
            "unexpected subscription method"
        );
        let subscription = data
            .get("subscription")
            .context("subscription response has no subscription")?;
        ensure!(
            subscription.get("coin").and_then(Value::as_str) == Some(expected_coin),
            "subscription coin mismatch"
        );
        let kind = match subscription.get("type").and_then(Value::as_str) {
            Some("l2Book") => FeedKind::Depth,
            Some("bbo") => FeedKind::Bbo,
            _ => bail!("unexpected subscription type"),
        };
        ensure!(
            policy.profile.includes(kind),
            "acknowledgement for an unselected feed"
        );
        return Ok(FeedMessage::Acknowledged(kind));
    }
    if channel == "error" {
        bail!(
            "exchange reported an error: {}",
            value.get("data").unwrap_or(&Value::Null)
        );
    }
    Ok(FeedMessage::Other)
}

pub fn validate_coin(coin: &str) -> Result<()> {
    ensure!(
        !coin.is_empty() && coin.len() <= 64,
        "coin must contain 1–64 characters"
    );
    ensure!(
        coin.bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"@:/._-".contains(&c)),
        "coin contains unsupported characters; use the exchange's exact coin identifier"
    );
    Ok(())
}

pub fn subscription(coin: &str) -> String {
    json!({"method": "subscribe", "subscription": {"type": "l2Book", "coin": coin}}).to_string()
}

pub fn parse_message(text: &str, expected_coin: &str) -> Result<MarketMessage> {
    // The official SDK explicitly handles this connection greeting.
    if text == "Websocket connection established." {
        return Ok(MarketMessage::Other);
    }
    let value: Value = serde_json::from_str(text).context("invalid WebSocket JSON")?;
    let channel = value
        .get("channel")
        .and_then(Value::as_str)
        .context("message has no channel")?;
    match channel {
        "l2Book" => {
            let data: WireBook =
                serde_json::from_value(value.get("data").context("l2Book has no data")?.clone())
                    .context("invalid l2Book shape")?;
            ensure!(
                data.coin == expected_coin,
                "received book for unexpected coin {}",
                data.coin
            );
            ensure!(data.time > 0, "exchange timestamp must be positive");
            let [bids, asks] = data.levels;
            let bids = parse_side(bids, true)?;
            let asks = parse_side(asks, false)?;
            if let (Some(bid), Some(ask)) = (bids.first(), asks.first()) {
                ensure!(bid.price < ask.price, "locked or crossed order book");
            }
            Ok(MarketMessage::Book(Book {
                exchange_time_ms: data.time,
                bids,
                asks,
            }))
        }
        "error" => bail!(
            "exchange reported an error: {}",
            value.get("data").unwrap_or(&Value::Null)
        ),
        "subscriptionResponse" => {
            let data = value
                .get("data")
                .context("subscription response has no data")?;
            ensure!(
                data.get("method").and_then(Value::as_str) == Some("subscribe"),
                "unexpected subscription method"
            );
            let subscription = data
                .get("subscription")
                .context("subscription response has no subscription")?;
            ensure!(
                subscription.get("type").and_then(Value::as_str) == Some("l2Book"),
                "unexpected subscription type"
            );
            ensure!(
                subscription.get("coin").and_then(Value::as_str) == Some(expected_coin),
                "subscription coin mismatch"
            );
            Ok(MarketMessage::Other)
        }
        _ => Ok(MarketMessage::Other),
    }
}

fn parse_side(levels: Vec<WireLevel>, bids: bool) -> Result<Vec<Level>> {
    ensure!(levels.len() <= 256, "book depth exceeds supported limit");
    let mut result: Vec<Level> = Vec::with_capacity(levels.len());
    for level in levels {
        let price = positive_decimal(&level.px).context("invalid price")?;
        let size = positive_decimal(&level.sz).context("invalid size")?;
        ensure!(level.n > 0, "level order count must be positive");
        if let Some(previous) = result.last() {
            ensure!(
                if bids {
                    previous.price > price
                } else {
                    previous.price < price
                },
                "levels must be strictly sorted, without duplicate prices"
            );
        }
        result.push(Level {
            price,
            size,
            orders: level.n,
        });
    }
    Ok(result)
}

fn positive_decimal(text: &str) -> Result<Decimal> {
    // Reject exponents, signs, whitespace and silent decimal rounding.
    ensure!(
        !text.is_empty() && text.bytes().all(|c| c.is_ascii_digit() || c == b'.'),
        "expected an unsigned plain decimal string"
    );
    let decimal =
        Decimal::from_str_exact(text).context("decimal is outside exact supported precision")?;
    ensure!(decimal > Decimal::ZERO, "value must be positive");
    Ok(decimal)
}

impl Book {
    pub fn mid_and_spread(&self) -> Result<Option<(Decimal, Decimal)>> {
        let (Some(bid), Some(ask)) = (self.bids.first(), self.asks.first()) else {
            return Ok(None);
        };
        let spread = ask
            .price
            .checked_sub(bid.price)
            .context("spread overflow")?;
        ensure!(
            bid.price.checked_add(spread) == Some(ask.price)
                && ask.price.checked_sub(spread) == Some(bid.price),
            "spread exceeds exact supported precision"
        );
        // Divide the spread first to avoid overflow when adding two large prices.
        let half = spread
            .checked_div(Decimal::from(2))
            .context("midprice division overflow")?;
        ensure!(
            half.checked_mul(Decimal::from(2)) == Some(spread),
            "midprice exceeds exact supported precision"
        );
        let mid = bid.price.checked_add(half).context("midprice overflow")?;
        ensure!(
            mid.checked_sub(bid.price) == Some(half),
            "midprice exceeds exact supported precision"
        );
        Ok(Some((mid, spread)))
    }
}

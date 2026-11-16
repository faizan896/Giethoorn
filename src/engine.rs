//! Pure state transitions: no clocks, I/O, randomness, or floating point.

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};

use crate::event::{Event, Record, SCHEMA_VERSION};
use crate::hyperliquid::{Book, MarketMessage, parse_message};
use crate::lifecycle::{Lifecycle, Phase};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Quote {
    pub sequence: u64,
    pub connection_id: u64,
    pub local_time_ns: u64,
    pub monotonic_ns: u64,
    pub exchange_time_ms: u64,
    pub coin: String,
    pub bid: Option<String>,
    pub ask: Option<String>,
    pub mid: Option<String>,
    pub spread: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Report {
    pub records: u64,
    pub connections: u64,
    pub snapshots: u64,
    pub stale_snapshots: u64,
    pub other_messages: u64,
    pub complete: bool,
    pub end_reason: Option<String>,
    /// Historical observation, not proof of a currently connected or fresh book.
    pub last_quote: Option<Quote>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub feeds: Option<crate::feeds::FeedReport>,
}

#[derive(Debug, Default)]
pub struct Engine {
    lifecycle: Lifecycle,
    book: Option<Book>,
    snapshots: u64,
    stale_snapshots: u64,
    other_messages: u64,
    last_quote: Option<Quote>,
}

impl Engine {
    pub fn book(&self) -> Option<&Book> {
        self.book.as_ref()
    }

    pub fn report(&self) -> Report {
        Report {
            records: self.lifecycle.sequence,
            connections: self.lifecycle.connection_id,
            snapshots: self.snapshots,
            stale_snapshots: self.stale_snapshots,
            other_messages: self.other_messages,
            complete: self.lifecycle.phase == Phase::Ended,
            end_reason: self.lifecycle.end_reason.clone(),
            last_quote: self.last_quote.clone(),
            feeds: None,
        }
    }

    /// Invalid records are terminal for replay. Capture may subsequently log an
    /// error and a close, but must not use the invalidated book.
    pub fn apply(&mut self, record: &Record) -> Result<Option<Quote>> {
        if self.lifecycle.apply(record, SCHEMA_VERSION)? {
            self.book = None;
        }
        if let Event::TextReceived { text } = &record.event {
            match self.apply_text(record, text) {
                Ok(quote) => return Ok(quote),
                Err(error) => {
                    self.book = None;
                    return Err(error).with_context(|| {
                        format!("invalid market data at sequence {}", record.sequence)
                    });
                }
            }
        }
        Ok(None)
    }

    fn apply_text(&mut self, record: &Record, text: &str) -> Result<Option<Quote>> {
        match parse_message(text, &self.lifecycle.coin)? {
            MarketMessage::Other => {
                self.other_messages += 1;
                Ok(None)
            }
            MarketMessage::Book(book) => {
                if self
                    .book
                    .as_ref()
                    .is_some_and(|old| old.exchange_time_ms > book.exchange_time_ms)
                {
                    self.stale_snapshots += 1;
                    return Ok(None);
                }
                let quote = quote_from_book(record, &self.lifecycle.coin, &book)?;
                self.book = Some(book);
                self.snapshots += 1;
                self.last_quote = Some(quote.clone());
                Ok(Some(quote))
            }
        }
    }
}

pub(crate) fn quote_from_book(record: &Record, coin: &str, book: &Book) -> Result<Quote> {
    let mid_and_spread = book.mid_and_spread()?;
    Ok(Quote {
        sequence: record.sequence,
        connection_id: record.connection_id,
        local_time_ns: record.local_time_ns,
        monotonic_ns: record.monotonic_ns,
        exchange_time_ms: book.exchange_time_ms,
        coin: coin.to_string(),
        bid: book
            .bids
            .first()
            .map(|level| level.price.normalize().to_string()),
        ask: book
            .asks
            .first()
            .map(|level| level.price.normalize().to_string()),
        mid: mid_and_spread.map(|(mid, _)| mid.normalize().to_string()),
        spread: mid_and_spread.map(|(_, spread)| spread.normalize().to_string()),
    })
}

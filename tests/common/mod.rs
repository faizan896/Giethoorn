#![allow(dead_code)]

use giethoorn::event::{Event, Network, Record, SCHEMA_VERSION};
use serde_json::json;

pub fn event(sequence: u64, connection_id: u64, event: Event) -> Record {
    Record {
        schema_version: SCHEMA_VERSION,
        sequence,
        local_time_ns: 1_000 + sequence,
        monotonic_ns: sequence * 10,
        connection_id,
        event,
    }
}

pub fn start() -> Vec<Record> {
    vec![
        event(
            1,
            0,
            Event::SessionStarted {
                coin: "BTC".into(),
                network: Network::Mainnet,
                application_version: "test".into(),
            },
        ),
        event(
            2,
            1,
            Event::ConnectionAttempt {
                endpoint: Network::Mainnet.endpoint().into(),
            },
        ),
        event(3, 1, Event::ConnectionOpened),
    ]
}

pub fn book(time: u64, bid: &str, ask: &str) -> Event {
    Event::TextReceived {
        text: json!({"channel":"l2Book", "data": {
            "coin":"BTC", "time": time, "levels": [
                [{"px":bid,"sz":"0.12345678","n":1}],
                [{"px":ask,"sz":"2","n":2}]
            ]
        }})
        .to_string(),
    }
}

pub fn session() -> Vec<Record> {
    let mut records = start();
    records.push(event(4, 1, book(1_700_000_000_000, "100.1", "100.2")));
    records.push(event(
        5,
        1,
        Event::ConnectionClosed {
            reason: "test".into(),
        },
    ));
    records.push(event(
        6,
        0,
        Event::SessionEnded {
            reason: "duration_elapsed".into(),
        },
    ));
    records
}

pub fn encode(records: &[Record]) -> Vec<u8> {
    records
        .iter()
        .flat_map(|record| {
            let mut bytes = serde_json::to_vec(record).unwrap();
            bytes.push(b'\n');
            bytes
        })
        .collect()
}

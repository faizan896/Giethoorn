mod common;

use std::io::Cursor;

use giethoorn::engine::Engine;
use giethoorn::event::Event;
use giethoorn::hyperliquid::{MarketMessage, parse_message};
use giethoorn::journal::replay_reader;
use serde_json::json;

use common::{book, encode, event, session, start};

fn connected_engine() -> Engine {
    let mut engine = Engine::default();
    for record in start() {
        engine.apply(&record).unwrap();
    }
    engine
}

#[test]
fn exact_decimal_midprice_is_identical_on_repeated_replay() {
    let input = encode(&session());
    let mut first = Vec::new();
    let report = replay_reader(Cursor::new(&input), false, |quote| {
        first.push(serde_json::to_string(quote)?);
        Ok(())
    })
    .unwrap();
    let mut second = Vec::new();
    let repeated = replay_reader(Cursor::new(&input), false, |quote| {
        second.push(serde_json::to_string(quote)?);
        Ok(())
    })
    .unwrap();
    assert_eq!(first, second);
    assert_eq!(report, repeated);
    assert_eq!(report.snapshots, 1);
    let quote = report.last_quote.unwrap();
    assert_eq!(quote.mid.as_deref(), Some("100.15"));
    assert_eq!(quote.spread.as_deref(), Some("0.1"));
}

#[test]
fn older_snapshot_is_ignored_and_equal_timestamp_is_accepted() {
    let mut engine = connected_engine();
    engine.apply(&event(4, 1, book(100, "100", "102"))).unwrap();
    assert!(
        engine
            .apply(&event(5, 1, book(99, "90", "91")))
            .unwrap()
            .is_none()
    );
    let quote = engine
        .apply(&event(6, 1, book(100, "101", "102")))
        .unwrap()
        .unwrap();
    assert_eq!(quote.mid.as_deref(), Some("101.5"));
    assert_eq!(engine.report().stale_snapshots, 1);
    assert_eq!(engine.report().snapshots, 2);
}

#[test]
fn disconnect_invalidates_book_and_new_connection_resets_exchange_time() {
    let mut engine = connected_engine();
    engine.apply(&event(4, 1, book(100, "100", "102"))).unwrap();
    engine
        .apply(&event(
            5,
            1,
            Event::ConnectionClosed {
                reason: "lost".into(),
            },
        ))
        .unwrap();
    assert!(engine.book().is_none());
    engine
        .apply(&event(
            6,
            2,
            Event::ConnectionAttempt {
                endpoint: "test".into(),
            },
        ))
        .unwrap();
    engine.apply(&event(7, 2, Event::ConnectionOpened)).unwrap();
    let quote = engine
        .apply(&event(8, 2, book(50, "50", "52")))
        .unwrap()
        .unwrap();
    assert_eq!(quote.mid.as_deref(), Some("51"));
    assert_eq!(quote.connection_id, 2);
}

#[test]
fn empty_side_replaces_previous_book_instead_of_leaving_stale_levels() {
    let mut engine = connected_engine();
    engine.apply(&event(4, 1, book(100, "100", "102"))).unwrap();
    let text = json!({"channel":"l2Book","data":{"coin":"BTC","time":101,"levels":[[],[{"px":"103","sz":"1","n":1}]]}}).to_string();
    let quote = engine
        .apply(&event(5, 1, Event::TextReceived { text }))
        .unwrap()
        .unwrap();
    assert!(quote.bid.is_none());
    assert!(quote.mid.is_none());
    assert!(quote.spread.is_none());
    assert_eq!(quote.ask.as_deref(), Some("103"));
    assert!(engine.book().unwrap().bids.is_empty());
}

#[test]
fn invalid_market_data_invalidates_the_previous_book() {
    let mut engine = connected_engine();
    engine.apply(&event(4, 1, book(100, "100", "102"))).unwrap();
    assert!(engine.apply(&event(5, 1, book(101, "103", "102"))).is_err());
    assert!(engine.book().is_none());
}

#[test]
fn invalid_numeric_levels_and_crossed_books_are_rejected() {
    for (bid, ask) in [
        ("NaN", "2"),
        ("-1", "2"),
        ("0", "2"),
        ("1e-3", "2"),
        (" 1", "2"),
        ("2", "2"),
        ("3", "2"),
        ("1.00000000000000000000000000001", "2"),
    ] {
        let mut engine = connected_engine();
        assert!(
            engine.apply(&event(4, 1, book(100, bid, ask))).is_err(),
            "accepted {bid}/{ask}"
        );
    }
}

#[test]
fn unsorted_duplicates_negative_size_and_wrong_coin_are_rejected() {
    let good = json!({"channel":"l2Book","data":{"coin":"BTC","time":100,"levels":[
        [{"px":"100","sz":"1","n":1}], [{"px":"102","sz":"1","n":1}]
    ]}});
    let mut cases = Vec::new();
    let mut wrong_coin = good.clone();
    wrong_coin["data"]["coin"] = json!("ETH");
    cases.push(wrong_coin);
    let mut zero_size = good.clone();
    zero_size["data"]["levels"][0][0]["sz"] = json!("0");
    cases.push(zero_size);
    let mut bad_size = good.clone();
    bad_size["data"]["levels"][0][0]["sz"] = json!("-1");
    cases.push(bad_size);
    let mut no_orders = good.clone();
    no_orders["data"]["levels"][0][0]["n"] = json!(0);
    cases.push(no_orders);
    let mut float_price = good.clone();
    float_price["data"]["levels"][0][0]["px"] = json!(100.0);
    cases.push(float_price);
    let mut unsorted = good.clone();
    unsorted["data"]["levels"][0]
        .as_array_mut()
        .unwrap()
        .push(json!({"px":"101","sz":"1","n":1}));
    cases.push(unsorted);
    let mut duplicate = good.clone();
    duplicate["data"]["levels"][0]
        .as_array_mut()
        .unwrap()
        .push(json!({"px":"100","sz":"1","n":1}));
    cases.push(duplicate);
    let mut missing_side = good;
    missing_side["data"]["levels"] = json!([[]]);
    cases.push(missing_side);
    for value in cases {
        assert!(
            parse_message(&value.to_string(), "BTC").is_err(),
            "accepted {value}"
        );
    }
}

#[test]
fn midprice_that_cannot_be_represented_exactly_is_rejected() {
    let mut engine = connected_engine();
    assert!(
        engine
            .apply(&event(
                4,
                1,
                book(
                    100,
                    "0.0000000000000000000000000001",
                    "0.0000000000000000000000000002"
                )
            ))
            .is_err()
    );
}

#[test]
fn book_price_and_size_precision_is_preserved() {
    let mut engine = connected_engine();
    let quote = engine
        .apply(&event(4, 1, book(100, "0.00000001", "0.00000002")))
        .unwrap()
        .unwrap();
    assert_eq!(quote.mid.as_deref(), Some("0.000000015"));
    assert_eq!(
        engine.book().unwrap().bids[0].size.to_string(),
        "0.12345678"
    );
}

#[test]
fn sequence_gaps_duplicates_unknown_schema_and_wrong_connection_fail() {
    for mut record in [
        event(5, 1, book(100, "1", "2")),
        event(3, 1, book(100, "1", "2")),
        event(4, 2, book(100, "1", "2")),
        event(4, 1, book(100, "1", "2")),
    ] {
        if record.sequence == 4 && record.connection_id == 1 {
            record.schema_version = 99;
        }
        assert!(connected_engine().apply(&record).is_err());
    }
}

#[test]
fn wall_clock_can_regress_but_monotonic_clock_cannot() {
    let mut engine = connected_engine();
    let mut record = event(4, 1, book(100, "1", "2"));
    record.local_time_ns = 1;
    assert!(engine.apply(&record).unwrap().is_some());
    let mut record = event(5, 1, book(101, "1", "2"));
    record.monotonic_ns = 0;
    assert!(engine.apply(&record).is_err());
}

#[test]
fn lifecycle_rejects_messages_without_a_connection_and_events_after_end() {
    let mut engine = Engine::default();
    assert!(engine.apply(&event(1, 1, book(100, "1", "2"))).is_err());
    let mut engine = connected_engine();
    assert!(
        engine
            .apply(&event(
                4,
                0,
                Event::SessionEnded {
                    reason: "test".into()
                }
            ))
            .is_err()
    );
    let mut engine = Engine::default();
    for record in session() {
        engine.apply(&record).unwrap();
    }
    assert!(
        engine
            .apply(&event(
                7,
                2,
                Event::ConnectionAttempt {
                    endpoint: "test".into()
                }
            ))
            .is_err()
    );
}

#[test]
fn exchange_errors_and_mismatched_subscriptions_fail_loudly() {
    assert!(
        parse_message(
            r#"{"channel":"error","data":"invalid subscription"}"#,
            "BTC"
        )
        .is_err()
    );
    assert!(parse_message(r#"{"channel":"subscriptionResponse","data":{"method":"subscribe","subscription":{"type":"l2Book","coin":"ETH"}}}"#, "BTC").is_err());
    assert!(parse_message("{", "BTC").is_err());
    assert_eq!(
        parse_message(r#"{"channel":"pong"}"#, "BTC").unwrap(),
        MarketMessage::Other
    );
}

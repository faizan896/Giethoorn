mod common;

use giethoorn::event::{Event, FEED_SCHEMA_VERSION, FeedKind, FeedPolicy, FeedProfile, Record};
use giethoorn::feeds::{FeedStatus, MarketEngine, Observation};
use giethoorn::hyperliquid::{FeedMessage, parse_feed_message};
use giethoorn::journal::replay_reader;
use serde_json::{Value, json};
use std::io::Cursor;

fn policy(profile: FeedProfile) -> FeedPolicy {
    FeedPolicy {
        profile,
        depth_stale_after_ms: 150,
        bbo_stale_after_ms: 50,
        timer_interval_ms: 10,
    }
}

fn record(sequence: u64, connection_id: u64, ms: u64, event: Event) -> Record {
    Record {
        schema_version: FEED_SCHEMA_VERSION,
        sequence,
        connection_id,
        monotonic_ns: ms * 1_000_000,
        local_time_ns: (1000 + ms) * 1_000_000,
        event,
    }
}

fn text(value: Value) -> Event {
    Event::TextReceived {
        text: value.to_string(),
    }
}

fn bbo(time: u64, bid: Value, ask: Value) -> Event {
    text(json!({"channel":"bbo","data":{"coin":"BTC","time":time,"bbo":[bid,ask]}}))
}

fn level(price: &str) -> Value {
    json!({"px":price,"sz":"0.12345678","n":1})
}

fn ack(kind: FeedKind) -> Event {
    text(
        json!({"channel":"subscriptionResponse","data":{"method":"subscribe","subscription":{"type":kind.channel(),"coin":"BTC"}}}),
    )
}

fn engine(profile: FeedProfile) -> MarketEngine {
    let mut engine = MarketEngine::default();
    for record in [
        record(
            1,
            0,
            0,
            Event::FeedSessionStarted {
                coin: "BTC".into(),
                network: giethoorn::event::Network::Mainnet,
                application_version: "synthetic-test".into(),
                policy: policy(profile),
            },
        ),
        record(
            2,
            1,
            1,
            Event::ConnectionAttempt {
                endpoint: "synthetic".into(),
            },
        ),
        record(3, 1, 2, Event::ConnectionOpened),
    ] {
        engine.apply(&record).unwrap();
    }
    engine
}

fn feed(observation: Observation) -> giethoorn::feeds::FeedObservation {
    let Observation::Feed(value) = observation else {
        panic!("expected schema-2 observation")
    };
    value
}

#[test]
fn combined_fixture_matches_its_golden_and_exposes_independent_stalls() {
    let input = std::fs::read("fixtures/hyperliquid-combined-v2.jsonl").unwrap();
    let mut output = Vec::new();
    let report = replay_reader(Cursor::new(&input), false, |observation| {
        serde_json::to_writer(&mut output, observation)?;
        output.push(b'\n');
        Ok(())
    })
    .unwrap();
    assert_eq!(
        output,
        std::fs::read("fixtures/hyperliquid-combined-v2.observations.jsonl").unwrap()
    );
    assert_eq!(report.snapshots, 9);
    assert_eq!(report.stale_snapshots, 2);
    assert!(report.last_quote.is_none());
    let details = report.feeds.unwrap();
    assert!(details.all_required_fresh_observed);
    assert_eq!(details.depth.unwrap().snapshots, 3);
    assert_eq!(details.bbo.unwrap().snapshots, 6);
    let observations: Vec<Value> = output
        .split(|b| *b == b'\n')
        .filter(|l| !l.is_empty())
        .map(|l| serde_json::from_slice(l).unwrap())
        .collect();
    let at = |sequence| {
        observations
            .iter()
            .find(|v| v["sequence"] == sequence)
            .unwrap()
    };
    assert_eq!(at(12)["feeds"]["depth"]["status"], "fresh");
    assert_eq!(at(12)["feeds"]["bbo"]["status"], "stale");
    assert_eq!(at(14)["feeds"]["depth"]["status"], "stale");
    assert_eq!(at(14)["feeds"]["depth"]["latest_sequence"], 8);
    assert_eq!(at(14)["feeds"]["bbo"]["status"], "fresh");
    assert_eq!(at(16)["feeds"]["bbo"]["status"], "empty");
    assert_eq!(at(18)["feeds"]["depth"]["status"], "disconnected");
    assert!(at(18)["feeds"]["depth"]["latest_sequence"].is_null());
    assert_eq!(at(24)["quote"]["exchange_time_ms"], 500);
    assert_eq!(at(25)["quote"]["mid"], "99.3");
    assert!(
        !observations
            .iter()
            .any(|v| v["sequence"] == 10 || v["sequence"] == 26)
    );
    let inspection = giethoorn::inspect::inspect(
        std::path::Path::new("fixtures/hyperliquid-combined-v2.jsonl"),
        false,
    )
    .unwrap();
    let channels = inspection.feeds.unwrap();
    assert_eq!(
        channels.depth.unwrap().max_snapshot_gap_ns,
        Some(170_000_000)
    );
    assert_eq!(channels.bbo.unwrap().max_snapshot_gap_ns, Some(70_000_000));
    assert_eq!(inspection.max_snapshot_gap_ns, Some(170_000_000));
    assert_eq!(inspection.snapshot_age_at_end_ns, Some(31_000_000));
}

#[test]
fn acknowledgements_and_each_selected_feed_are_required_for_usable_data() {
    let mut e = engine(FeedProfile::Combined);
    e.apply(&record(4, 1, 3, ack(FeedKind::Depth))).unwrap();
    e.apply(&record(5, 1, 4, common::book(100, "100", "102")))
        .unwrap();
    e.apply(&record(6, 1, 5, bbo(100, level("101"), level("103"))))
        .unwrap();
    assert!(!e.has_usable_data());
    let update = feed(
        e.apply(&record(7, 1, 6, ack(FeedKind::Bbo)))
            .unwrap()
            .unwrap(),
    );
    assert!(update.feeds.all_required_fresh);
    assert!(e.has_usable_data());
}

#[test]
fn live_data_without_an_acknowledgement_cannot_extend_the_ack_deadline() {
    let mut e = engine(FeedProfile::Bbo);
    for (seq, ms) in [(4, 10), (5, 30), (6, 51)] {
        e.apply(&record(seq, 1, ms, bbo(ms, level("1"), level("2"))))
            .unwrap();
    }
    assert!(!e.has_usable_data());
    e.apply(&record(7, 1, 52, Event::FeedTimer)).unwrap();
    assert_eq!(e.stalled_feed(), Some(FeedKind::Bbo));
}

#[test]
fn empty_updates_do_not_extend_the_two_sided_data_deadline() {
    let mut e = engine(FeedProfile::Bbo);
    e.apply(&record(4, 1, 3, ack(FeedKind::Bbo))).unwrap();
    e.apply(&record(5, 1, 10, bbo(100, level("1"), level("2"))))
        .unwrap();
    e.apply(&record(6, 1, 40, bbo(101, Value::Null, level("2"))))
        .unwrap();
    let update = feed(
        e.apply(&record(7, 1, 60, Event::FeedTimer))
            .unwrap()
            .unwrap(),
    );
    assert_eq!(update.feeds.bbo.unwrap().status, FeedStatus::Stale);
    assert_eq!(e.stalled_feed(), Some(FeedKind::Bbo));
}

#[test]
fn bbo_validation_preserves_exact_decimals_and_explicit_missing_sides() {
    let p = policy(FeedProfile::Bbo);
    let Event::TextReceived { text } = bbo(100, level("0.00000001"), level("0.00000002")) else {
        unreachable!()
    };
    let FeedMessage::Book(FeedKind::Bbo, book) = parse_feed_message(&text, "BTC", &p).unwrap()
    else {
        panic!("expected BBO")
    };
    assert_eq!(
        book.mid_and_spread().unwrap().unwrap().0,
        rust_decimal::Decimal::from_str_exact("0.000000015").unwrap()
    );
    let Event::TextReceived { text } = bbo(101, Value::Null, level("2")) else {
        unreachable!()
    };
    let FeedMessage::Book(_, book) = parse_feed_message(&text, "BTC", &p).unwrap() else {
        panic!("expected book")
    };
    assert!(book.bids.is_empty());
    assert!(book.mid_and_spread().unwrap().is_none());
}

#[test]
fn malformed_bbo_wrong_markets_and_unselected_channels_fail_and_invalidate_state() {
    let mut cases = Vec::new();
    for (bid, ask) in [
        ("2", "1"),
        ("1", "1"),
        ("1e-3", "2"),
        ("0", "2"),
        ("NaN", "2"),
        ("-1", "2"),
        (
            "0.0000000000000000000000000001",
            "0.0000000000000000000000000002",
        ),
    ] {
        cases.push(bbo(101, level(bid), level(ask)));
    }
    for data in [
        json!({"coin":"ETH","time":101,"bbo":[level("1"),level("2")]}),
        json!({"coin":"BTC","time":0,"bbo":[level("1"),level("2")]}),
        json!({"coin":"BTC","time":101,"bbo":[level("1")]}),
        json!({"coin":"BTC","time":101,"bbo":[{"px":"1","sz":"0","n":1},level("2")]}),
        json!({"coin":"BTC","time":101,"bbo":[{"px":1,"sz":"1","n":1},level("2")]}),
        json!({"coin":"BTC","time":101,"bbo":[{"px":"1","sz":"1","n":0},level("2")]}),
    ] {
        cases.push(text(json!({"channel":"bbo","data":data})));
    }
    cases.push(common::book(101, "1", "2"));
    cases.push(ack(FeedKind::Depth));
    for invalid in cases {
        let mut e = engine(FeedProfile::Bbo);
        e.apply(&record(4, 1, 3, ack(FeedKind::Bbo))).unwrap();
        e.apply(&record(5, 1, 4, bbo(100, level("1"), level("2"))))
            .unwrap();
        assert!(e.apply(&record(6, 1, 5, invalid)).is_err());
        assert_eq!(
            e.report().feeds.unwrap().current.bbo.unwrap().status,
            FeedStatus::Disconnected
        );
    }
}

#[test]
fn version_mixing_unknown_versions_and_timer_events_in_legacy_sessions_fail() {
    let mut e = engine(FeedProfile::Depth);
    let mut bad = record(4, 1, 3, Event::FeedTimer);
    bad.schema_version = 1;
    assert!(e.apply(&bad).is_err());
    for version in [0, 3, 99] {
        let mut e = MarketEngine::default();
        let mut first = common::start().remove(0);
        first.schema_version = version;
        assert!(e.apply(&first).is_err());
    }
    let mut e = giethoorn::engine::Engine::default();
    for r in common::start() {
        e.apply(&r).unwrap();
    }
    assert!(e.apply(&common::event(4, 1, Event::FeedTimer)).is_err());
}

#[test]
fn profile_timing_limits_are_validated_without_overflow() {
    for (depth, bbo, timer) in [
        (0, 50, 10),
        (150, u64::MAX, 10),
        (150, 50, 0),
        (150, 50, 51),
        (150, 500, 251),
    ] {
        assert!(
            FeedPolicy {
                profile: FeedProfile::Combined,
                depth_stale_after_ms: depth,
                bbo_stale_after_ms: bbo,
                timer_interval_ms: timer
            }
            .validate()
            .is_err()
        );
    }
}

#[test]
fn single_feed_profiles_require_only_the_selected_channel() {
    for (profile, source) in [
        (FeedProfile::Depth, FeedKind::Depth),
        (FeedProfile::Bbo, FeedKind::Bbo),
    ] {
        let mut e = engine(profile);
        e.apply(&record(4, 1, 3, ack(source))).unwrap();
        let market = if source == FeedKind::Depth {
            common::book(100, "1", "2")
        } else {
            bbo(100, level("1"), level("2"))
        };
        e.apply(&record(5, 1, 4, market)).unwrap();
        assert!(e.has_usable_data());
        let report = e.report().feeds.unwrap();
        assert_eq!(report.current.depth.is_some(), source == FeedKind::Depth);
        assert_eq!(report.current.bbo.is_some(), source == FeedKind::Bbo);
    }
}

#[test]
fn sealed_schema_mismatch_is_rejected_before_any_observation_is_emitted() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("session");
    let records: Vec<Record> = std::fs::read_to_string("fixtures/hyperliquid-combined-v2.jsonl")
        .unwrap()
        .lines()
        .map(|l| serde_json::from_str(l).unwrap())
        .collect();
    let mut journal = giethoorn::journal::Journal::create_versioned(
        &path,
        giethoorn::journal::JournalMode::Segmented(giethoorn::segments::SegmentLimits {
            max_segment_bytes: 4096,
            max_session_bytes: 1024 * 1024,
            min_free_bytes: 0,
        }),
        2,
    )
    .unwrap();
    for record in records {
        journal.append(record.connection_id, record.event).unwrap();
    }
    journal.finish().unwrap();
    drop(journal);
    let index = path.join("index.jsonl");
    let original = std::fs::read_to_string(&index).unwrap();
    std::fs::write(
        index,
        original.replacen(
            "\"event_schema_version\":2",
            "\"event_schema_version\":1",
            1,
        ),
    )
    .unwrap();
    let mut emitted = 0;
    let error = giethoorn::journal::replay(&path, false, |_| {
        emitted += 1;
        Ok(())
    })
    .unwrap_err();
    assert_eq!(emitted, 0);
    assert!(format!("{error:#}").contains("schema differs from container header"));
}

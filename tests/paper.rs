use giethoorn::paper::*;
use serde_json::{Value, json};
use std::io::Cursor;

fn a(value: &str) -> Amount {
    value.parse().unwrap()
}
fn config() -> PaperConfig {
    let first = std::fs::read_to_string("fixtures/paper-synthetic-v1.jsonl").unwrap();
    let record: PaperRecord = serde_json::from_str(first.lines().next().unwrap()).unwrap();
    let PaperEvent::SessionStarted { config } = record.event else {
        panic!("expected start")
    };
    config
}
fn start_with(config: PaperConfig) -> PaperEngine {
    let mut e = PaperEngine::default();
    e.apply(&PaperRecord {
        paper_schema_version: 1,
        sequence: 1,
        monotonic_ns: 0,
        event: PaperEvent::SessionStarted { config },
    })
    .unwrap();
    e
}
fn apply_at(e: &mut PaperEngine, ms: u64, event: PaperEvent) -> PaperUpdate {
    let sequence = e.report().unwrap().records + 1;
    e.apply(&PaperRecord {
        paper_schema_version: 1,
        sequence,
        monotonic_ns: ms * 1_000_000,
        event,
    })
    .unwrap()
}
fn apply(e: &mut PaperEngine, event: PaperEvent) -> PaperUpdate {
    let ms = e.report().unwrap().records + 1;
    apply_at(e, ms, event)
}
fn engine() -> PaperEngine {
    let mut e = start_with(config());
    apply(
        &mut e,
        PaperEvent::MarketObserved {
            bid: a("99"),
            ask: a("101"),
        },
    );
    e
}
fn request(e: &mut PaperEngine, id: &str, side: Side, price: &str, qty: &str) -> PaperUpdate {
    apply(
        e,
        PaperEvent::OrderRequested {
            id: id.into(),
            side,
            limit_price: a(price),
            quantity: a(qty),
        },
    )
}
fn accepted(e: &mut PaperEngine, id: &str, side: Side, price: &str, qty: &str) {
    request(e, id, side, price, qty);
    apply(e, PaperEvent::OrderAccepted { id: id.into() });
}
fn fill(e: &mut PaperEngine, id: &str, order: &str, price: &str, qty: &str) -> PaperUpdate {
    apply(
        e,
        PaperEvent::AssumedFill {
            fill_id: id.into(),
            order_id: order.into(),
            price: a(price),
            quantity: a(qty),
        },
    )
}
fn unchanged_error(e: &mut PaperEngine, event: PaperEvent) {
    let before = e.report().unwrap();
    let record = PaperRecord {
        paper_schema_version: 1,
        sequence: before.records + 1,
        monotonic_ns: (before.records + 1) * 1_000_000,
        event,
    };
    assert!(e.apply(&record).is_err());
    assert_eq!(before, e.report().unwrap());
}

#[test]
fn synthetic_scenario_replays_exactly_and_matches_hand_calculated_fifo_results() {
    let bytes = std::fs::read("fixtures/paper-synthetic-v1.jsonl").unwrap();
    let mut first = Vec::new();
    let report = replay_paper_reader(Cursor::new(&bytes), false, |update| {
        serde_json::to_writer(&mut first, update)?;
        first.push(b'\n');
        Ok(())
    })
    .unwrap();
    assert_eq!(
        first,
        std::fs::read("fixtures/paper-synthetic-v1.updates.jsonl").unwrap()
    );
    assert_eq!(
        serde_json::to_value(&report).unwrap(),
        serde_json::from_slice::<Value>(
            &std::fs::read("fixtures/paper-synthetic-v1.report.json").unwrap()
        )
        .unwrap()
    );
    let mut repeated = Vec::new();
    let second = replay_paper_reader(Cursor::new(bytes), false, |update| {
        serde_json::to_writer(&mut repeated, update)?;
        repeated.push(b'\n');
        Ok(())
    })
    .unwrap();
    assert_eq!(first, repeated);
    assert_eq!(report, second);
    assert_eq!(report.records, 29);
    assert_eq!(report.assumed_fills, 5);
    assert_eq!(report.duplicate_events, 1);
    assert_eq!(report.account.position_quantity, Amount::ZERO);
    assert_eq!(report.account.realized_pnl, a("1.6"));
    assert_eq!(report.account.fees, a("0.0592"));
    assert_eq!(report.account.collateral_balance, a("10001.5408"));
    assert_eq!(report.account.net_pnl, Some(a("1.5408")));
    assert!(report.open_lots.is_empty());
    assert!(report.complete);
    let frames: Vec<Value> = first
        .split(|b| *b == b'\n')
        .filter(|l| !l.is_empty())
        .map(|l| serde_json::from_slice(l).unwrap())
        .collect();
    assert!(
        frames
            .iter()
            .all(|f| f["mode"] == "paper" && f["source"]["kind"] == "synthetic")
    );
    assert_eq!(frames[13]["account"]["realized_pnl"], "3");
    assert_eq!(frames[13]["account"]["unrealized_pnl"], "2.1");
    assert_eq!(frames[13]["account"]["equity"], "10005.05855");
    assert_eq!(frames[21]["account"]["position_quantity"], "-0.1");
    assert_eq!(frames[21]["account"]["realized_pnl"], "1.1");
    assert_eq!(frames[16]["order"]["rejection"], "stale_market");
    assert_eq!(frames[27]["order"]["rejection"], "halted");
}

#[test]
fn opposite_working_orders_do_not_net_away_unconfirmed_exposure() {
    let mut e = engine();
    request(&mut e, "buy", Side::Buy, "100", "2");
    request(&mut e, "sell", Side::Sell, "100", "2");
    let denied = request(&mut e, "extra", Side::Buy, "100", "0.1");
    assert_eq!(
        denied.order.unwrap().rejection,
        Some(RejectReason::PositionLimit)
    );
    assert_eq!(denied.risk.worst_long_position, a("2"));
    assert_eq!(denied.risk.worst_short_position, a("-2"));
}

#[test]
fn cancel_requests_keep_reservations_until_acknowledgement() {
    let mut e = engine();
    accepted(&mut e, "a", Side::Buy, "100", "2");
    apply(&mut e, PaperEvent::CancelRequested { id: "a".into() });
    assert_eq!(
        request(&mut e, "b", Side::Buy, "100", "0.1")
            .order
            .unwrap()
            .rejection,
        Some(RejectReason::PositionLimit)
    );
    apply(&mut e, PaperEvent::CancelAccepted { id: "a".into() });
    let allowed = request(&mut e, "c", Side::Buy, "100", "0.1");
    assert_eq!(allowed.order.unwrap().status, OrderStatus::PendingNew);
    assert_eq!(allowed.risk.worst_long_position, a("0.1"));
}

#[test]
fn partial_fill_during_cancel_and_cancel_rejection_preserve_lifecycle_and_exposure() {
    let mut e = engine();
    accepted(&mut e, "a", Side::Buy, "100", "1");
    fill(&mut e, "f1", "a", "100", "0.2");
    apply(&mut e, PaperEvent::CancelRequested { id: "a".into() });
    let update = fill(&mut e, "f2", "a", "100", "0.3");
    assert_eq!(update.order.unwrap().status, OrderStatus::PendingCancel);
    let update = apply(
        &mut e,
        PaperEvent::CancelRejected {
            id: "a".into(),
            reason: "assumed cancellation rejection".into(),
        },
    );
    assert_eq!(update.order.unwrap().status, OrderStatus::PartiallyFilled);
    assert_eq!(update.account.position_quantity, a("0.5"));
    assert_eq!(update.risk.worst_long_position, a("1"));
    apply(&mut e, PaperEvent::CancelRequested { id: "a".into() });
    let update = apply(&mut e, PaperEvent::CancelAccepted { id: "a".into() });
    assert_eq!(update.risk.worst_long_position, a("0.5"));
    assert_eq!(update.account.position_quantity, a("0.5"));
}

#[test]
fn full_fill_wins_cancel_race_and_late_duplicate_ack_is_idempotent() {
    let mut e = engine();
    accepted(&mut e, "a", Side::Buy, "100", "1");
    apply(&mut e, PaperEvent::CancelRequested { id: "a".into() });
    let filled = fill(&mut e, "f", "a", "100", "1");
    assert_eq!(filled.order.unwrap().status, OrderStatus::Filled);
    let ack = apply(&mut e, PaperEvent::CancelAccepted { id: "a".into() });
    let order = ack.order.unwrap();
    assert_eq!(order.status, OrderStatus::Filled);
    assert!(!order.cancel_pending);
    let again = apply(&mut e, PaperEvent::CancelAccepted { id: "a".into() });
    assert!(again.duplicate);
    assert_eq!(again.account, ack.account);
}

#[test]
fn duplicate_fill_cannot_double_charge_and_changed_payload_fails_atomically() {
    let mut e = engine();
    accepted(&mut e, "a", Side::Buy, "100", "1");
    let first = fill(&mut e, "f", "a", "100", "0.5");
    let repeated = fill(&mut e, "f", "a", "100", "0.5");
    assert!(repeated.duplicate);
    assert_eq!(first.account, repeated.account);
    unchanged_error(
        &mut e,
        PaperEvent::AssumedFill {
            fill_id: "f".into(),
            order_id: "a".into(),
            price: a("99"),
            quantity: a("0.5"),
        },
    );
    assert_eq!(e.report().unwrap().assumed_fills, 1);
}

#[test]
fn unacknowledged_overfilled_off_limit_and_terminal_fills_fail_without_mutation() {
    let mut e = engine();
    request(&mut e, "a", Side::Buy, "100", "1");
    unchanged_error(
        &mut e,
        PaperEvent::AssumedFill {
            fill_id: "early".into(),
            order_id: "a".into(),
            price: a("100"),
            quantity: a("0.1"),
        },
    );
    apply(&mut e, PaperEvent::OrderAccepted { id: "a".into() });
    for (price, qty) in [("100", "1.1"), ("101", "0.1"), ("100", "0"), ("-1", "0.1")] {
        unchanged_error(
            &mut e,
            PaperEvent::AssumedFill {
                fill_id: "invalid".into(),
                order_id: "a".into(),
                price: a(price),
                quantity: a(qty),
            },
        );
    }
    fill(&mut e, "done", "a", "100", "1");
    unchanged_error(
        &mut e,
        PaperEvent::AssumedFill {
            fill_id: "late".into(),
            order_id: "a".into(),
            price: a("100"),
            quantity: a("0.1"),
        },
    );
}

#[test]
fn cancelled_orders_cannot_receive_new_fills_but_known_fill_duplicates_remain_idempotent() {
    let mut e = engine();
    accepted(&mut e, "a", Side::Buy, "100", "1");
    fill(&mut e, "f", "a", "100", "0.2");
    apply(&mut e, PaperEvent::CancelRequested { id: "a".into() });
    apply(&mut e, PaperEvent::CancelAccepted { id: "a".into() });
    unchanged_error(
        &mut e,
        PaperEvent::AssumedFill {
            fill_id: "late".into(),
            order_id: "a".into(),
            price: a("100"),
            quantity: a("0.1"),
        },
    );
    let duplicate = fill(&mut e, "f", "a", "100", "0.2");
    assert!(duplicate.duplicate);
    assert_eq!(duplicate.account.position_quantity, a("0.2"));
}

#[test]
fn duplicate_order_intent_never_reopens_or_changes_a_terminal_order() {
    let mut e = engine();
    accepted(&mut e, "a", Side::Buy, "100", "1");
    fill(&mut e, "f", "a", "100", "1");
    let again = request(&mut e, "a", Side::Buy, "100", "1");
    assert!(again.duplicate);
    assert_eq!(again.order.unwrap().status, OrderStatus::Filled);
    unchanged_error(
        &mut e,
        PaperEvent::OrderRequested {
            id: "a".into(),
            side: Side::Buy,
            limit_price: a("99"),
            quantity: a("1"),
        },
    );
}

#[test]
fn missing_stale_and_disconnected_markets_block_new_orders_without_inventing_cancels() {
    let mut e = start_with(config());
    assert_eq!(
        request(&mut e, "missing", Side::Buy, "100", "1")
            .order
            .unwrap()
            .rejection,
        Some(RejectReason::MissingMarket)
    );
    apply(
        &mut e,
        PaperEvent::MarketObserved {
            bid: a("99"),
            ask: a("101"),
        },
    );
    accepted(&mut e, "a", Side::Buy, "100", "1");
    apply_at(&mut e, 2003, PaperEvent::Timer {});
    let stale = apply_at(
        &mut e,
        2004,
        PaperEvent::OrderRequested {
            id: "stale".into(),
            side: Side::Buy,
            limit_price: a("100"),
            quantity: a("0.1"),
        },
    );
    assert_eq!(
        stale.order.unwrap().rejection,
        Some(RejectReason::StaleMarket)
    );
    apply_at(
        &mut e,
        2005,
        PaperEvent::MarketDisconnected {
            reason: "synthetic loss".into(),
        },
    );
    let missing = apply_at(
        &mut e,
        2006,
        PaperEvent::OrderRequested {
            id: "disconnected".into(),
            side: Side::Buy,
            limit_price: a("100"),
            quantity: a("0.1"),
        },
    );
    assert_eq!(
        missing.order.unwrap().rejection,
        Some(RejectReason::MissingMarket)
    );
    let observed = apply_at(
        &mut e,
        2007,
        PaperEvent::AssumedFill {
            fill_id: "late-known-order".into(),
            order_id: "a".into(),
            price: a("100"),
            quantity: a("0.1"),
        },
    );
    assert_eq!(observed.account.position_quantity, a("0.1"));
    assert!(!observed.account.mark_fresh);
    assert_eq!(observed.risk.working_orders, 1);
}

#[test]
fn loss_limit_latches_and_manual_halt_never_claims_working_orders_are_cancelled() {
    let mut cfg = config();
    cfg.max_loss = a("1");
    let mut e = start_with(cfg);
    apply(
        &mut e,
        PaperEvent::MarketObserved {
            bid: a("99"),
            ask: a("101"),
        },
    );
    accepted(&mut e, "a", Side::Buy, "100", "1");
    fill(&mut e, "f", "a", "100", "1");
    let loss = apply(
        &mut e,
        PaperEvent::MarketObserved {
            bid: a("98"),
            ask: a("100"),
        },
    );
    assert_eq!(loss.risk.halt_reason.as_deref(), Some("session_loss_limit"));
    apply(
        &mut e,
        PaperEvent::MarketObserved {
            bid: a("199"),
            ask: a("201"),
        },
    );
    assert_eq!(
        request(&mut e, "halted", Side::Buy, "100", "0.1")
            .order
            .unwrap()
            .rejection,
        Some(RejectReason::Halted)
    );
    let mut e = engine();
    accepted(&mut e, "pending", Side::Buy, "100", "1");
    let stopped = apply(
        &mut e,
        PaperEvent::Halt {
            reason: "synthetic stop".into(),
        },
    );
    assert!(stopped.risk.halted);
    assert_eq!(stopped.risk.working_orders, 1);
}

#[test]
fn notional_and_working_order_limits_are_independent() {
    let mut e = engine();
    assert_eq!(
        request(&mut e, "huge", Side::Buy, "1000", "2")
            .order
            .unwrap()
            .rejection,
        Some(RejectReason::OrderNotionalLimit)
    );
    for id in ["a", "b", "c", "d"] {
        request(&mut e, id, Side::Buy, "100", "0.1");
    }
    assert_eq!(
        request(&mut e, "e", Side::Buy, "100", "0.1")
            .order
            .unwrap()
            .rejection,
        Some(RejectReason::WorkingOrderLimit)
    );
}

#[test]
fn exact_arithmetic_never_silently_rounds_and_serialization_keeps_strings() {
    assert_eq!(a("0.1").add_exact(a("0.2")).unwrap(), a("0.3"));
    assert_eq!(
        a("0.00000001").multiply_exact(a("0.12345678")).unwrap(),
        a("0.0000000012345678")
    );
    assert!(
        a("0.0000000000000000000000000001")
            .multiply_exact(a("0.1"))
            .is_err()
    );
    assert!(
        a("79228162514264337593543950335")
            .add_exact(a("0.1"))
            .is_err()
    );
    assert!(
        a("79228162514264337593543950335")
            .multiply_exact(a("79228162514264337593543950335"))
            .is_err()
    );
    assert_eq!(serde_json::to_string(&a("1.2300")).unwrap(), "\"1.23\"");
    assert!(serde_json::from_str::<Amount>("1.23").is_err());
    for value in ["NaN", "1e-3", "+1", " 1", "--1", "."] {
        assert!(value.parse::<Amount>().is_err());
    }
}

#[test]
fn an_unrepresentable_fee_rolls_back_positions_order_state_and_sequence() {
    let mut e = engine();
    accepted(
        &mut e,
        "tiny",
        Side::Buy,
        "0.0000000000000000000000000001",
        "1",
    );
    unchanged_error(
        &mut e,
        PaperEvent::AssumedFill {
            fill_id: "tiny-fill".into(),
            order_id: "tiny".into(),
            price: a("0.0000000000000000000000000001"),
            quantity: a("1"),
        },
    );
    assert_eq!(e.account().unwrap().position_quantity, Amount::ZERO);
    assert_eq!(e.account().unwrap().fees, Amount::ZERO);
}

#[test]
fn unsupported_loss_floor_returns_an_error_instead_of_panicking() {
    let mut cfg = config();
    cfg.starting_collateral = a("79228162514264337593543950335");
    cfg.max_loss = a("0.0000000000000000000000000001");
    let mut e = PaperEngine::default();
    assert!(
        e.apply(&PaperRecord {
            paper_schema_version: 1,
            sequence: 1,
            monotonic_ns: 0,
            event: PaperEvent::SessionStarted { config: cfg }
        })
        .is_err()
    );
    assert!(e.report().is_err());
}

#[test]
fn lifecycle_versions_ordering_and_end_marker_are_strict() {
    for version in [0, 2, 99] {
        let mut e = PaperEngine::default();
        assert!(
            e.apply(&PaperRecord {
                paper_schema_version: version,
                sequence: 1,
                monotonic_ns: 0,
                event: PaperEvent::SessionStarted { config: config() }
            })
            .is_err()
        );
    }
    let mut e = engine();
    let before = e.report().unwrap();
    assert!(
        e.apply(&PaperRecord {
            paper_schema_version: 1,
            sequence: before.records + 2,
            monotonic_ns: 100000000,
            event: PaperEvent::Timer {}
        })
        .is_err()
    );
    assert!(
        e.apply(&PaperRecord {
            paper_schema_version: 1,
            sequence: before.records + 1,
            monotonic_ns: 0,
            event: PaperEvent::Timer {}
        })
        .is_err()
    );
    assert_eq!(before, e.report().unwrap());
    apply(
        &mut e,
        PaperEvent::SessionEnded {
            reason: "synthetic end".into(),
        },
    );
    unchanged_error(&mut e, PaperEvent::Timer {});
}

#[test]
fn ending_a_scenario_does_not_flatten_positions_or_release_working_orders() {
    let mut e = engine();
    accepted(&mut e, "a", Side::Buy, "100", "1");
    fill(&mut e, "f", "a", "100", "0.5");
    let update = apply(
        &mut e,
        PaperEvent::SessionEnded {
            reason: "synthetic end with exposure".into(),
        },
    );
    assert!(update.complete);
    assert_eq!(update.account.position_quantity, a("0.5"));
    assert_eq!(update.risk.working_orders, 1);
    assert!(!update.account.mark_fresh);
}

#[test]
fn recovery_never_skips_a_corrupt_complete_record_or_appended_data_after_end() {
    let raw = std::fs::read("fixtures/paper-synthetic-v1.jsonl").unwrap();
    let lines: Vec<_> = raw.split_inclusive(|b| *b == b'\n').collect();
    let mut prefix = lines[..3].concat();
    prefix.extend_from_slice(b"{\"partial\":");
    assert!(replay_paper_reader(Cursor::new(&prefix), false, |_| Ok(())).is_err());
    let report = replay_paper_reader(Cursor::new(&prefix), true, |_| Ok(())).unwrap();
    assert!(!report.complete);
    assert_eq!(report.records, 3);
    let mut corrupt = lines[..3].concat();
    corrupt.extend_from_slice(b"not-json\n");
    assert!(replay_paper_reader(Cursor::new(corrupt), true, |_| Ok(())).is_err());
    let mut appended = raw;
    appended.extend_from_slice(b"partial");
    assert!(replay_paper_reader(Cursor::new(appended), true, |_| Ok(())).is_err());
    assert!(replay_paper_reader(Cursor::new(Vec::<u8>::new()), true, |_| Ok(())).is_err());
}

#[test]
fn numeric_inputs_live_provenance_and_unknown_event_fields_are_rejected() {
    let record = PaperRecord {
        paper_schema_version: 1,
        sequence: 1,
        monotonic_ns: 0,
        event: PaperEvent::SessionStarted { config: config() },
    };
    let mut value = serde_json::to_value(record).unwrap();
    value["event"]["config"]["starting_collateral"] = json!(10000);
    assert!(serde_json::from_value::<PaperRecord>(value.clone()).is_err());
    value["event"]["config"]["starting_collateral"] = json!("10000");
    value["event"]["config"]["source"]["kind"] = json!("live");
    assert!(serde_json::from_value::<PaperRecord>(value).is_err());
    assert!(
        serde_json::from_value::<PaperEvent>(json!({"type":"timer","extra":"ignored?"})).is_err()
    );
}

#[test]
fn derived_output_failure_is_not_reported_as_a_successful_replay() {
    let raw = std::fs::read("fixtures/paper-synthetic-v1.jsonl").unwrap();
    assert!(
        replay_paper_reader(Cursor::new(raw), false, |_| anyhow::bail!(
            "synthetic output failure"
        ))
        .is_err()
    );
}

#[test]
fn production_paper_cli_replays_the_synthetic_golden_without_network_or_order_access() {
    let output = std::process::Command::new(env!("CARGO_BIN_EXE_giethoorn"))
        .args([
            "paper-replay",
            "--input",
            "fixtures/paper-synthetic-v1.jsonl",
        ])
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(
        output.stdout,
        std::fs::read("fixtures/paper-synthetic-v1.updates.jsonl").unwrap()
    );
    let report: Value = serde_json::from_slice(&output.stderr).unwrap();
    assert_eq!(report["mode"], "paper");
    assert_eq!(report["config"]["source"]["kind"], "synthetic");
    assert_eq!(report["account"]["net_pnl"], "1.5408");
}

#[test]
fn paper_cli_cannot_misinterpret_market_recordings_as_execution_events() {
    let output = std::process::Command::new(env!("CARGO_BIN_EXE_giethoorn"))
        .args(["paper-replay", "--input", "fixtures/hyperliquid-btc.jsonl"])
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert!(output.stdout.is_empty());
    assert!(String::from_utf8_lossy(&output.stderr).contains("invalid paper record"));
}

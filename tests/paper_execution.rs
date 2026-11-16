use giethoorn::event::FeedKind;
use giethoorn::paper::*;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

fn fixture(parent: &Path, raw: &[u8]) -> PathBuf {
    let path = parent.join("source");
    fs::create_dir(&path).unwrap();
    fs::write(path.join("segment-00000001.jsonl"), raw).unwrap();
    let count = raw.iter().filter(|&&b| b == b'\n').count();
    let entries = [
        json!({"kind":"header","container_version":1,"event_schema_version":2,"max_segment_bytes":1048576,"max_session_bytes":2097152}),
        json!({"kind":"segment","number":1,"file":"segment-00000001.jsonl","bytes":raw.len(),"first_sequence":1,"last_sequence":count,"sha256":format!("{:x}",Sha256::digest(raw))}),
        json!({"kind":"end","segments":1,"records":count,"data_bytes":raw.len()}),
    ];
    fs::write(
        path.join("index.jsonl"),
        entries
            .iter()
            .map(|e| serde_json::to_string(e).unwrap() + "\n")
            .collect::<String>(),
    )
    .unwrap();
    path
}
fn scenario() -> ExecutionScenario {
    serde_json::from_str(include_str!("../fixtures/paper-ioc-scenario-v1.json")).unwrap()
}
fn order(id: &str, at: u64, side: Side, limit: &str, quantity: &str) -> ScenarioOrder {
    ScenarioOrder {
        id: id.into(),
        after_market_sequence: at,
        side,
        limit_price: limit.parse().unwrap(),
        quantity: quantity.parse().unwrap(),
    }
}
fn run(
    parent: &Path,
    input: &Path,
    plan: &ExecutionScenario,
    name: &str,
) -> (ExecutionReport, PathBuf) {
    let file = parent.join(format!("{name}-scenario.json"));
    fs::write(&file, serde_json::to_vec(plan).unwrap()).unwrap();
    let output = parent.join(name);
    let report = export_execution_scenario(
        input,
        &file,
        &output,
        RecordingOrigin::SyntheticFixture,
        FeedKind::Bbo,
    )
    .unwrap();
    (report, output)
}
fn lines(path: &Path) -> Vec<Value> {
    fs::read_to_string(path)
        .unwrap()
        .lines()
        .map(|l| serde_json::from_str(l).unwrap())
        .collect()
}
fn by_id<'a>(report: &'a PaperReport, id: &str) -> &'a Order {
    report.orders.iter().find(|o| o.id == id).unwrap()
}

#[test]
fn controlled_fixture_matches_golden_and_hand_calculated_costs_without_double_debits() {
    let dir = tempfile::tempdir().unwrap();
    let input = fixture(
        dir.path(),
        include_bytes!("../fixtures/hyperliquid-combined-v2.jsonl"),
    );
    let original = fs::read(input.join("segment-00000001.jsonl")).unwrap();
    let output = dir.path().join("run");
    let report = export_execution_scenario(
        &input,
        Path::new("fixtures/paper-ioc-scenario-v1.json"),
        &output,
        RecordingOrigin::SyntheticFixture,
        FeedKind::Bbo,
    )
    .unwrap();
    for (file, golden) in [
        ("paper-input.jsonl", "input.jsonl"),
        ("paper-updates.jsonl", "updates.jsonl"),
        ("paper-report.json", "report.json"),
        ("market-links.jsonl", "links.jsonl"),
        ("execution-trace.jsonl", "trace.jsonl"),
    ] {
        assert_eq!(
            fs::read(output.join(file)).unwrap(),
            fs::read(format!("fixtures/paper-execution-v3.{golden}")).unwrap()
        );
    }
    assert_eq!(report.paper.assumed_fills, 2);
    assert_eq!(report.paper.account.position_quantity, Amount::ZERO);
    assert_eq!(
        report.paper.account.realized_pnl,
        "-0.0300225".parse().unwrap()
    );
    assert_eq!(report.fees, "0.02511250125".parse().unwrap());
    assert_eq!(report.spread_cost, "0.05".parse().unwrap());
    assert_eq!(report.slippage_cost, "0.0050225".parse().unwrap());
    assert_eq!(
        report.paper.account.net_pnl,
        Some("-0.05513500125".parse().unwrap())
    );
    assert_eq!(
        report.paper.account.collateral_balance,
        "9999.94486499875".parse().unwrap()
    );
    assert!(!report.strategy_enabled && !report.full_window_verified);
    assert_eq!(
        fs::read(input.join("segment-00000001.jsonl")).unwrap(),
        original
    );
    let second = dir.path().join("again");
    let repeated = export_execution_scenario(
        &input,
        Path::new("fixtures/paper-ioc-scenario-v1.json"),
        &second,
        RecordingOrigin::SyntheticFixture,
        FeedKind::Bbo,
    )
    .unwrap();
    assert_eq!(report, repeated);
    assert_eq!(
        fs::read(output.join("paper-updates.jsonl")).unwrap(),
        fs::read(second.join("paper-updates.jsonl")).unwrap()
    );
}

#[test]
fn partial_ioc_remainders_cancel_but_unacknowledged_end_orders_stay_pending() {
    let dir = tempfile::tempdir().unwrap();
    let input = fixture(
        dir.path(),
        include_bytes!("../fixtures/hyperliquid-combined-v2.jsonl"),
    );
    let (r, _) = run(dir.path(), &input, &scenario(), "run");
    for id in ["buy-partial", "sell-partial"] {
        let o = by_id(&r.paper, id);
        assert_eq!(o.status, OrderStatus::Cancelled);
        assert_eq!(o.filled_quantity, "0.25".parse().unwrap());
        assert_eq!(o.remaining_quantity, "0.75".parse().unwrap());
        assert!(o.cancel_acknowledged);
    }
    assert!(r.paper.complete);
    assert_eq!(r.pending_order_ids, vec!["late-pending"]);
    assert_eq!(
        by_id(&r.paper, "late-pending").status,
        OrderStatus::PendingNew
    );
    assert_eq!(r.paper.risk.working_orders, 1);
    assert_eq!(r.paper.risk.worst_long_position, "0.1".parse().unwrap());
}

#[test]
fn missing_stale_risky_and_nonmarketable_requests_do_not_invent_fills() {
    let dir = tempfile::tempdir().unwrap();
    let input = fixture(
        dir.path(),
        include_bytes!("../fixtures/hyperliquid-combined-v2.jsonl"),
    );
    let (r, _) = run(dir.path(), &input, &scenario(), "run");
    assert_eq!(
        by_id(&r.paper, "missing-market").rejection,
        Some(RejectReason::MissingMarket)
    );
    assert_eq!(
        by_id(&r.paper, "stale-send").rejection,
        Some(RejectReason::StaleMarket)
    );
    assert_eq!(
        by_id(&r.paper, "oversized").rejection,
        Some(RejectReason::OrderNotionalLimit)
    );
    for id in ["not-marketable", "ambiguous-time"] {
        let o = by_id(&r.paper, id);
        assert_eq!(o.status, OrderStatus::Cancelled);
        assert_eq!(o.filled_quantity, Amount::ZERO);
    }
}

#[test]
fn latency_uses_next_fresh_selected_quote_never_the_triggering_or_other_feed_quote() {
    let dir = tempfile::tempdir().unwrap();
    let input = fixture(
        dir.path(),
        include_bytes!("../fixtures/hyperliquid-combined-v2.jsonl"),
    );
    let mut plan = scenario();
    plan.orders = vec![order("delayed", 9, Side::Buy, "101", "0.1")];
    plan.assumptions.latency_ms = 50;
    let (r, path) = run(dir.path(), &input, &plan, "run");
    assert_eq!(r.paper.assumed_fills, 1);
    let trace = lines(&path.join("execution-trace.jsonl"));
    let fill = trace.iter().find(|t| t["phase"] == "assumed_fill").unwrap();
    assert_eq!(fill["market_sequence"], 13);
    assert_eq!(fill["arrival_ns"], 70000000);
    let frames = lines(&path.join("paper-updates.jsonl"));
    let links = lines(&path.join("market-links.jsonl"));
    assert!(
        frames
            .iter()
            .zip(&links)
            .all(|(f, l)| l["market_sequence"].as_u64().unwrap() >= 13
                || f["assumed_fill"].is_null())
    );
}

#[test]
fn expiry_boundary_is_exclusive_even_if_a_fresh_quote_arrives_at_that_time() {
    let dir = tempfile::tempdir().unwrap();
    let input = fixture(
        dir.path(),
        include_bytes!("../fixtures/hyperliquid-combined-v2.jsonl"),
    );
    let mut plan = scenario();
    plan.orders = vec![order("expiry", 14, Side::Buy, "101", "0.1")];
    let (r, _) = run(dir.path(), &input, &plan, "expired");
    assert_eq!(r.paper.assumed_fills, 0);
    assert_eq!(by_id(&r.paper, "expiry").status, OrderStatus::Rejected);
    plan.assumptions.quote_wait_ms = 101;
    let (r, _) = run(dir.path(), &input, &plan, "within");
    assert_eq!(r.paper.assumed_fills, 1);
    assert_eq!(by_id(&r.paper, "expiry").status, OrderStatus::Filled);
}

#[test]
fn concurrent_iocs_cannot_each_consume_the_same_top_of_book_capacity() {
    let dir = tempfile::tempdir().unwrap();
    let input = fixture(
        dir.path(),
        include_bytes!("../fixtures/hyperliquid-combined-v2.jsonl"),
    );
    let mut plan = scenario();
    plan.orders = vec![
        order("first", 11, Side::Buy, "101", "1"),
        order("second", 11, Side::Buy, "101", "1"),
    ];
    let (r, _) = run(dir.path(), &input, &plan, "run");
    assert_eq!(r.paper.assumed_fills, 1);
    assert_eq!(
        by_id(&r.paper, "first").filled_quantity,
        "0.25".parse().unwrap()
    );
    assert_eq!(by_id(&r.paper, "second").filled_quantity, Amount::ZERO);
}

#[test]
fn equal_exchange_timestamps_do_not_replenish_spent_liquidity() {
    let dir = tempfile::tempdir().unwrap();
    let mut records = include_str!("../fixtures/hyperliquid-combined-v2.jsonl")
        .lines()
        .map(|l| serde_json::from_str::<Value>(l).unwrap())
        .collect::<Vec<_>>();
    let original: Value =
        serde_json::from_str(records[8]["event"]["text"].as_str().unwrap()).unwrap();
    for i in [10, 12] {
        records[i]["event"]["text"] = json!(serde_json::to_string(&original).unwrap());
    }
    let bytes = records
        .iter()
        .map(|r| serde_json::to_string(r).unwrap() + "\n")
        .collect::<String>();
    let input = fixture(dir.path(), bytes.as_bytes());
    let mut plan = scenario();
    plan.orders = vec![
        order("first", 9, Side::Buy, "101", "1"),
        order("second", 11, Side::Buy, "101", "1"),
        order("new-time", 13, Side::Buy, "101", "1"),
    ];
    let (r, _) = run(dir.path(), &input, &plan, "run");
    assert_eq!(r.paper.assumed_fills, 2);
    assert_eq!(by_id(&r.paper, "second").filled_quantity, Amount::ZERO);
    assert_eq!(
        by_id(&r.paper, "new-time").filled_quantity,
        "0.25".parse().unwrap()
    );
}

#[test]
fn adverse_slippage_cannot_fill_beyond_the_declared_limit() {
    let dir = tempfile::tempdir().unwrap();
    let input = fixture(
        dir.path(),
        include_bytes!("../fixtures/hyperliquid-combined-v2.jsonl"),
    );
    let mut plan = scenario();
    plan.orders = vec![
        order("buy-limit", 11, Side::Buy, "100.505", "0.1"),
        order("sell-limit", 13, Side::Sell, "100.395", "0.1"),
    ];
    let (r, _) = run(dir.path(), &input, &plan, "run");
    assert_eq!(r.paper.assumed_fills, 0);
    assert_eq!(r.fees, Amount::ZERO);
    assert!(
        r.paper
            .orders
            .iter()
            .all(|o| o.status == OrderStatus::Cancelled)
    );
}

#[test]
fn changing_future_prices_cannot_change_earlier_economic_transitions() {
    let first = tempfile::tempdir().unwrap();
    let second = tempfile::tempdir().unwrap();
    let a = fixture(
        first.path(),
        include_bytes!("../fixtures/hyperliquid-combined-v2.jsonl"),
    );
    let mut records = include_str!("../fixtures/hyperliquid-combined-v2.jsonl")
        .lines()
        .map(|l| serde_json::from_str::<Value>(l).unwrap())
        .collect::<Vec<_>>();
    let mut quote: Value =
        serde_json::from_str(records[13]["event"]["text"].as_str().unwrap()).unwrap();
    quote["data"]["bbo"][0]["px"] = json!("120");
    quote["data"]["bbo"][1]["px"] = json!("120.2");
    records[13]["event"]["text"] = json!(serde_json::to_string(&quote).unwrap());
    let bytes = records
        .iter()
        .map(|r| serde_json::to_string(r).unwrap() + "\n")
        .collect::<String>();
    let b = fixture(second.path(), bytes.as_bytes());
    let (_, one) = run(first.path(), &a, &scenario(), "run");
    let (_, two) = run(second.path(), &b, &scenario(), "run");
    fn early(path: &Path) -> Vec<Value> {
        let frames = lines(&path.join("paper-updates.jsonl"));
        let links = lines(&path.join("market-links.jsonl"));
        frames
            .into_iter()
            .zip(links)
            .filter(|(_, l)| l["market_sequence"].as_u64().unwrap() < 14)
            .map(|(mut f, _)| {
                f.as_object_mut().unwrap().remove("source");
                f
            })
            .collect()
    }
    assert_eq!(early(&one), early(&two));
}

#[test]
fn invalid_duplicate_or_unsorted_scenarios_fail_before_output_creation() {
    let dir = tempfile::tempdir().unwrap();
    let input = fixture(
        dir.path(),
        include_bytes!("../fixtures/hyperliquid-combined-v2.jsonl"),
    );
    let mut variants = Vec::new();
    let mut p = scenario();
    p.scenario_version = 99;
    variants.push(p);
    let mut p = scenario();
    p.orders[1].id = p.orders[0].id.clone();
    variants.push(p);
    let mut p = scenario();
    p.orders.swap(0, 1);
    variants.push(p);
    let mut p = scenario();
    p.assumptions.top_size_fraction = Amount::ZERO;
    variants.push(p);
    let mut p = scenario();
    p.assumptions.fee_rate = "0.02".parse().unwrap();
    variants.push(p);
    for (i, p) in variants.iter().enumerate() {
        let plan = dir.path().join(format!("bad-{i}.json"));
        fs::write(&plan, serde_json::to_vec(p).unwrap()).unwrap();
        let out = dir.path().join(format!("out-{i}"));
        assert!(
            export_execution_scenario(
                &input,
                &plan,
                &out,
                RecordingOrigin::SyntheticFixture,
                FeedKind::Bbo
            )
            .is_err()
        );
        assert!(!out.exists());
    }
}

#[test]
fn execution_provenance_requires_version_three_and_exact_fee_agreement() {
    let first = include_str!("../fixtures/paper-execution-v3.input.jsonl")
        .lines()
        .next()
        .unwrap();
    let mut record: PaperRecord = serde_json::from_str(first).unwrap();
    for version in [1, 2] {
        record.paper_schema_version = version;
        assert!(PaperEngine::default().apply(&record).is_err());
    }
    record.paper_schema_version = 3;
    if let PaperEvent::SessionStarted { config } = &mut record.event {
        config.fee_rate = Amount::ZERO;
    }
    assert!(PaperEngine::default().apply(&record).is_err());
}

#[test]
fn active_or_corrupt_sources_keep_diagnostics_without_execution_success() {
    for active in [true, false] {
        let dir = tempfile::tempdir().unwrap();
        let input = fixture(
            dir.path(),
            include_bytes!("../fixtures/hyperliquid-combined-v2.jsonl"),
        );
        let lock = fs::File::open(input.join("index.jsonl")).unwrap();
        if active {
            fs2::FileExt::try_lock_exclusive(&lock).unwrap();
        } else {
            fs::write(input.join("segment-00000001.jsonl"), b"corrupt\n").unwrap();
        }
        let out = dir.path().join("run");
        assert!(
            export_execution_scenario(
                &input,
                Path::new("fixtures/paper-ioc-scenario-v1.json"),
                &out,
                RecordingOrigin::SyntheticFixture,
                FeedKind::Bbo
            )
            .is_err()
        );
        assert!(!out.join("execution-replay.json").exists());
    }
}

#[test]
fn production_cli_and_independent_ledger_replay_match_exact_execution_bytes() {
    let dir = tempfile::tempdir().unwrap();
    let input = fixture(
        dir.path(),
        include_bytes!("../fixtures/hyperliquid-combined-v2.jsonl"),
    );
    let output = dir.path().join("run");
    let run = Command::new(env!("CARGO_BIN_EXE_giethoorn"))
        .args(["paper-execution-replay", "--input"])
        .arg(&input)
        .args([
            "--scenario",
            "fixtures/paper-ioc-scenario-v1.json",
            "--output-dir",
        ])
        .arg(&output)
        .args(["--origin", "synthetic-fixture"])
        .output()
        .unwrap();
    assert!(
        run.status.success(),
        "{}",
        String::from_utf8_lossy(&run.stderr)
    );
    let replay = Command::new(env!("CARGO_BIN_EXE_giethoorn"))
        .args(["paper-replay", "--input"])
        .arg(output.join("paper-input.jsonl"))
        .output()
        .unwrap();
    assert!(replay.status.success());
    assert_eq!(
        replay.stdout,
        fs::read(output.join("paper-updates.jsonl")).unwrap()
    );
}

#[test]
fn loss_halt_blocks_new_intents_but_accounts_for_already_inflight_fills() {
    let dir = tempfile::tempdir().unwrap();
    let input = fixture(
        dir.path(),
        include_bytes!("../fixtures/hyperliquid-combined-v2.jsonl"),
    );
    let mut plan = scenario();
    plan.max_loss = "0.001".parse().unwrap();
    plan.orders = vec![
        order("buy", 11, Side::Buy, "101", "1"),
        order("sell", 11, Side::Sell, "99", "1"),
        order("after-halt", 13, Side::Buy, "101", "0.1"),
    ];
    let (report, _) = run(dir.path(), &input, &plan, "run");
    assert!(report.paper.risk.halted);
    assert_eq!(report.paper.assumed_fills, 2);
    assert_eq!(
        by_id(&report.paper, "after-halt").rejection,
        Some(RejectReason::Halted)
    );
    assert_eq!(report.paper.account.position_quantity, Amount::ZERO);
}

#[test]
fn depth_selected_orders_wait_for_depth_instead_of_executing_on_fast_quotes() {
    let dir = tempfile::tempdir().unwrap();
    let input = fixture(
        dir.path(),
        include_bytes!("../fixtures/hyperliquid-combined-v2.jsonl"),
    );
    let mut plan = scenario();
    plan.orders = vec![order("depth-probe", 10, Side::Buy, "101", "0.1")];
    plan.assumptions.quote_wait_ms = 200;
    let path = dir.path().join("scenario.json");
    fs::write(&path, serde_json::to_vec(&plan).unwrap()).unwrap();
    let output = dir.path().join("run");
    let report = export_execution_scenario(
        &input,
        &path,
        &output,
        RecordingOrigin::SyntheticFixture,
        FeedKind::Depth,
    )
    .unwrap();
    assert_eq!(report.paper.config.stale_after_ms, 150);
    assert_eq!(report.paper.assumed_fills, 1);
    let trace = lines(&output.join("execution-trace.jsonl"));
    let fill = trace.iter().find(|t| t["phase"] == "assumed_fill").unwrap();
    assert_eq!(fill["market_sequence"], 15);
}

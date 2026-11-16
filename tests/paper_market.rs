use giethoorn::event::FeedKind;
use giethoorn::paper::*;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

fn source(parent: &Path, bytes: &[u8], version: u16, finalized: bool) -> PathBuf {
    let path = parent.join("source");
    fs::create_dir(&path).unwrap();
    let records = bytes.iter().filter(|&&b| b == b'\n').count();
    fs::write(path.join("segment-00000001.jsonl"), bytes).unwrap();
    let mut entries = vec![
        json!({"kind":"header","container_version":1,"event_schema_version":version,
               "max_segment_bytes":1048576,"max_session_bytes":2097152}),
        json!({"kind":"segment","number":1,"file":"segment-00000001.jsonl","bytes":bytes.len(),
               "first_sequence":1,"last_sequence":records,"sha256":format!("{:x}",Sha256::digest(bytes))}),
    ];
    if finalized {
        entries.push(json!({"kind":"end","segments":1,"records":records,"data_bytes":bytes.len()}));
    }
    let index = entries
        .iter()
        .map(|entry| serde_json::to_string(entry).unwrap() + "\n")
        .collect::<String>();
    fs::write(path.join("index.jsonl"), index).unwrap();
    path
}

fn fixture(parent: &Path) -> PathBuf {
    source(
        parent,
        include_bytes!("../fixtures/hyperliquid-combined-v2.jsonl"),
        2,
        true,
    )
}

fn values(path: &Path) -> Vec<Value> {
    fs::read_to_string(path)
        .unwrap()
        .lines()
        .map(|l| serde_json::from_str(l).unwrap())
        .collect()
}

#[test]
fn recorded_fixture_matches_versioned_golden_and_replays_exactly_without_orders() {
    let directory = tempfile::tempdir().unwrap();
    let input = fixture(directory.path());
    let original = fs::read(input.join("segment-00000001.jsonl")).unwrap();
    let first = directory.path().join("first");
    let second = directory.path().join("second");
    let a = export_recorded_market(
        &input,
        &first,
        RecordingOrigin::SyntheticFixture,
        FeedKind::Bbo,
    )
    .unwrap();
    let b = export_recorded_market(
        &input,
        &second,
        RecordingOrigin::SyntheticFixture,
        FeedKind::Bbo,
    )
    .unwrap();
    assert_eq!(a, b);
    for (file, golden) in [
        ("paper-input.jsonl", "input.jsonl"),
        ("paper-updates.jsonl", "updates.jsonl"),
        ("paper-report.json", "report.json"),
    ] {
        let bytes = fs::read(first.join(file)).unwrap();
        assert_eq!(bytes, fs::read(second.join(file)).unwrap());
        assert_eq!(
            bytes,
            fs::read(format!("fixtures/paper-recorded-v2.{golden}")).unwrap()
        );
    }
    let mut replayed = Vec::new();
    let report = replay_paper(&first.join("paper-input.jsonl"), false, |update| {
        serde_json::to_writer(&mut replayed, update)?;
        replayed.push(b'\n');
        Ok(())
    })
    .unwrap();
    assert_eq!(
        replayed,
        fs::read(first.join("paper-updates.jsonl")).unwrap()
    );
    assert_eq!(report, a.paper);
    assert_eq!(a.paper.records, 30);
    assert_eq!(a.market_marks, 5);
    assert!(!a.full_window_verified && !a.strategy_enabled);
    assert!(a.paper.orders.is_empty());
    assert_eq!(a.paper.assumed_fills, 0);
    assert_eq!(a.paper.account.net_pnl, Some(Amount::ZERO));
    assert_eq!(
        original,
        fs::read(input.join("segment-00000001.jsonl")).unwrap()
    );
}

#[test]
fn selected_feed_keeps_exact_marks_staleness_empty_and_reconnect_reset() {
    let directory = tempfile::tempdir().unwrap();
    let input = fixture(directory.path());
    let output = directory.path().join("derived");
    export_recorded_market(
        &input,
        &output,
        RecordingOrigin::SyntheticFixture,
        FeedKind::Bbo,
    )
    .unwrap();
    let frames = values(&output.join("paper-updates.jsonl"));
    assert_eq!(frames[8]["account"]["mark_price"], "100.3");
    assert_eq!(frames[9]["account"]["mark_price"], "100.3"); // Depth cannot refresh BBO.
    assert_eq!(frames[11]["risk"]["market_status"], "stale"); // Exact recorded deadline.
    assert_eq!(frames[15]["risk"]["market_status"], "disconnected"); // Empty selected side.
    assert_eq!(frames[23]["risk"]["market_status"], "disconnected"); // New depth cannot inherit old BBO.
    assert_eq!(frames[24]["account"]["mark_price"], "99.3");
    assert!(
        !frames.last().unwrap()["account"]["mark_fresh"]
            .as_bool()
            .unwrap()
    );
    let links = values(&output.join("market-links.jsonl"));
    assert_eq!(links.len(), frames.len());
    assert_eq!(links[8]["market_sequence"], 9);
    assert_eq!(links[8]["quote"]["bid"], "100.2");
    assert_eq!(links[9]["feeds"]["bbo"]["age_ns"], 10000000);
    assert_eq!(links.last().unwrap()["market_sequence"], 29);
    assert_eq!(links.last().unwrap()["generated_end"], true);
}

#[test]
fn selecting_depth_changes_deadline_and_preserves_independent_provenance() {
    let directory = tempfile::tempdir().unwrap();
    let input = fixture(directory.path());
    let output = directory.path().join("depth");
    let report = export_recorded_market(
        &input,
        &output,
        RecordingOrigin::SyntheticFixture,
        FeedKind::Depth,
    )
    .unwrap();
    assert_eq!(report.paper.config.stale_after_ms, 150);
    let PaperSource::RecordedMarket { feed, origin, .. } = report.paper.config.source else {
        panic!("recorded source required")
    };
    assert_eq!(feed, FeedKind::Depth);
    assert_eq!(origin, RecordingOrigin::SyntheticFixture);
    let frames = values(&output.join("paper-updates.jsonl"));
    assert_eq!(frames[7]["account"]["mark_price"], "100.2");
    assert_eq!(frames[8]["account"]["mark_price"], "100.2"); // BBO cannot replace depth mark.
}

#[test]
fn paper_versions_and_provenance_cannot_mix_or_activate_orders() {
    let records = include_str!("../fixtures/paper-recorded-v2.input.jsonl")
        .lines()
        .map(|l| serde_json::from_str::<PaperRecord>(l).unwrap())
        .collect::<Vec<_>>();
    let start = records[0].clone();
    let mut engine = PaperEngine::default();
    let mut wrong = start.clone();
    wrong.paper_schema_version = 1;
    assert!(engine.apply(&wrong).is_err());
    engine.apply(&start).unwrap();
    let before = engine.report().unwrap();
    for event in [
        PaperEvent::OrderRequested {
            id: "probe".into(),
            side: Side::Buy,
            limit_price: "100".parse().unwrap(),
            quantity: "0.1".parse().unwrap(),
        },
        PaperEvent::AssumedFill {
            fill_id: "fake".into(),
            order_id: "probe".into(),
            price: "100".parse().unwrap(),
            quantity: "0.1".parse().unwrap(),
        },
    ] {
        let record = PaperRecord {
            paper_schema_version: 2,
            sequence: 2,
            monotonic_ns: 1,
            event,
        };
        assert!(engine.apply(&record).is_err());
        assert_eq!(engine.report().unwrap(), before);
    }
    let mixed = PaperRecord {
        paper_schema_version: 1,
        sequence: 2,
        monotonic_ns: 1,
        event: PaperEvent::Timer {},
    };
    assert!(engine.apply(&mixed).is_err());
    let mut invalid = start;
    if let PaperEvent::SessionStarted { config } = &mut invalid.event
        && let PaperSource::RecordedMarket {
            recording_sha256, ..
        } = &mut config.source
    {
        *recording_sha256 = "bad-digest".into();
    }
    assert!(PaperEngine::default().apply(&invalid).is_err());
}

#[test]
fn active_recording_lock_prevents_any_derived_output() {
    let directory = tempfile::tempdir().unwrap();
    let input = fixture(directory.path());
    let lock = fs::File::open(input.join("index.jsonl")).unwrap();
    fs2::FileExt::try_lock_exclusive(&lock).unwrap();
    let output = directory.path().join("out");
    assert!(
        export_recorded_market(
            &input,
            &output,
            RecordingOrigin::SyntheticFixture,
            FeedKind::Bbo
        )
        .is_err()
    );
    assert!(!output.exists());
}

#[test]
fn unfinalized_source_and_corrupt_seals_cannot_publish_a_run() {
    for finalized in [false, true] {
        let directory = tempfile::tempdir().unwrap();
        let input = source(
            directory.path(),
            include_bytes!("../fixtures/hyperliquid-combined-v2.jsonl"),
            2,
            finalized,
        );
        if finalized {
            use std::io::Write;
            fs::OpenOptions::new()
                .append(true)
                .open(input.join("segment-00000001.jsonl"))
                .unwrap()
                .write_all(b"corrupt\n")
                .unwrap();
        }
        let output = directory.path().join("out");
        assert!(
            export_recorded_market(
                &input,
                &output,
                RecordingOrigin::SyntheticFixture,
                FeedKind::Bbo
            )
            .is_err()
        );
        assert!(!output.exists());
    }
}

#[test]
fn resealed_invalid_market_record_and_legacy_schema_are_rejected_before_output() {
    for (bytes, version) in [
        (b"not-json\n".as_slice(), 2),
        (
            include_bytes!("../fixtures/hyperliquid-btc.jsonl").as_slice(),
            1,
        ),
    ] {
        let directory = tempfile::tempdir().unwrap();
        let input = source(directory.path(), bytes, version, true);
        let output = directory.path().join("out");
        assert!(
            export_recorded_market(
                &input,
                &output,
                RecordingOrigin::SyntheticFixture,
                FeedKind::Bbo
            )
            .is_err()
        );
        assert!(!output.exists());
    }
}

#[test]
fn existing_outputs_and_nested_source_outputs_are_never_overwritten() {
    let directory = tempfile::tempdir().unwrap();
    let input = fixture(directory.path());
    let output = directory.path().join("out");
    fs::create_dir(&output).unwrap();
    fs::write(output.join("precious"), b"retained").unwrap();
    assert!(
        export_recorded_market(
            &input,
            &output,
            RecordingOrigin::SyntheticFixture,
            FeedKind::Bbo
        )
        .is_err()
    );
    assert_eq!(fs::read(output.join("precious")).unwrap(), b"retained");
    assert!(
        export_recorded_market(
            &input,
            &input.join("nested"),
            RecordingOrigin::SyntheticFixture,
            FeedKind::Bbo
        )
        .is_err()
    );
    assert!(!input.join("nested").exists());
}

#[test]
fn cli_requires_declared_origin_and_exports_replayable_version_two() {
    let directory = tempfile::tempdir().unwrap();
    let input = fixture(directory.path());
    let output = directory.path().join("out");
    let missing = Command::new(env!("CARGO_BIN_EXE_giethoorn"))
        .args(["paper-market-replay", "--input"])
        .arg(&input)
        .arg("--output-dir")
        .arg(&output)
        .output()
        .unwrap();
    assert!(!missing.status.success());
    assert!(!output.exists());
    let run = Command::new(env!("CARGO_BIN_EXE_giethoorn"))
        .args(["paper-market-replay", "--input"])
        .arg(&input)
        .arg("--output-dir")
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
    let report: Value = serde_json::from_slice(&run.stdout).unwrap();
    assert_eq!(
        report["paper"]["config"]["source"]["origin"],
        "synthetic_fixture"
    );
    assert_eq!(report["paper"]["paper_model_version"], 2);
}

#[test]
fn disabled_feed_is_rejected_before_creating_output() {
    let directory = tempfile::tempdir().unwrap();
    let mut records = include_str!("../fixtures/hyperliquid-combined-v2.jsonl")
        .lines()
        .map(|line| serde_json::from_str::<Value>(line).unwrap())
        .collect::<Vec<_>>();
    records[0]["event"]["policy"]["profile"] = json!("depth");
    let bytes = records
        .iter()
        .map(|r| serde_json::to_string(r).unwrap() + "\n")
        .collect::<String>();
    let input = source(directory.path(), bytes.as_bytes(), 2, true);
    let output = directory.path().join("out");
    let error = export_recorded_market(
        &input,
        &output,
        RecordingOrigin::SyntheticFixture,
        FeedKind::Bbo,
    )
    .unwrap_err();
    assert!(format!("{error:#}").contains("selected feed is disabled"));
    assert!(!output.exists());
}

#[test]
fn locked_market_recording_is_rejected_before_paper_output() {
    let directory = tempfile::tempdir().unwrap();
    let mut records = include_str!("../fixtures/hyperliquid-combined-v2.jsonl")
        .lines()
        .map(|line| serde_json::from_str::<Value>(line).unwrap())
        .collect::<Vec<_>>();
    let mut quote: Value =
        serde_json::from_str(records[8]["event"]["text"].as_str().unwrap()).unwrap();
    quote["data"]["bbo"][1]["px"] = json!("100.2");
    records[8]["event"]["text"] = json!(serde_json::to_string(&quote).unwrap());
    let bytes = records
        .iter()
        .map(|r| serde_json::to_string(r).unwrap() + "\n")
        .collect::<String>();
    let input = source(directory.path(), bytes.as_bytes(), 2, true);
    let output = directory.path().join("out");
    let error = export_recorded_market(
        &input,
        &output,
        RecordingOrigin::SyntheticFixture,
        FeedKind::Bbo,
    )
    .unwrap_err();
    assert!(format!("{error:#}").contains("locked or crossed BBO"));
    assert!(!output.exists());
}

#[test]
fn complete_large_recording_is_rejected_instead_of_silently_truncated() {
    let directory = tempfile::tempdir().unwrap();
    let mut records = include_str!("../fixtures/hyperliquid-combined-v2.jsonl")
        .lines()
        .map(|line| serde_json::from_str::<Value>(line).unwrap())
        .collect::<Vec<_>>();
    let ending = records.split_off(27);
    while records.len() < 9998 {
        records.push(json!({"schema_version":2,"sequence":records.len()+1,
            "local_time_ns":1790000000281000000_u64,"monotonic_ns":281000000,
            "connection_id":2,"event":{"type":"feed_timer"}}));
    }
    records.extend(ending);
    for (i, record) in records.iter_mut().enumerate() {
        record["sequence"] = json!(i + 1);
    }
    let bytes = records
        .iter()
        .map(|r| serde_json::to_string(r).unwrap() + "\n")
        .collect::<String>();
    let input = source(directory.path(), bytes.as_bytes(), 2, true);
    let mut index = values(&input.join("index.jsonl"));
    index[0]["max_segment_bytes"] = json!(2097152);
    index[0]["max_session_bytes"] = json!(4194304);
    fs::write(
        input.join("index.jsonl"),
        index
            .iter()
            .map(|r| serde_json::to_string(r).unwrap() + "\n")
            .collect::<String>(),
    )
    .unwrap();
    let output = directory.path().join("out");
    let error = export_recorded_market(
        &input,
        &output,
        RecordingOrigin::SyntheticFixture,
        FeedKind::Bbo,
    )
    .unwrap_err();
    assert!(
        format!("{error:#}").contains("10,000-record limit"),
        "{error:#}"
    );
    assert!(!output.exists());
}

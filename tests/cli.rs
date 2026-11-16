use std::process::Command;

#[test]
fn fixture_replays_to_the_reviewed_golden_output() {
    let output = Command::new(env!("CARGO_BIN_EXE_giethoorn"))
        .args(["replay", "--input", "fixtures/hyperliquid-btc.jsonl"])
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(
        output.stdout,
        std::fs::read("fixtures/hyperliquid-btc.quotes.jsonl").unwrap()
    );
    let report: serde_json::Value = serde_json::from_slice(&output.stderr).unwrap();
    assert_eq!(report["snapshots"], 3);
    assert_eq!(report["stale_snapshots"], 1);
    assert_eq!(report["connections"], 2);
    assert_eq!(report["complete"], true);
}

#[test]
fn schema_two_fixture_uses_explicit_observation_output_and_keeps_legacy_output_separate() {
    let output = Command::new(env!("CARGO_BIN_EXE_giethoorn"))
        .args([
            "replay",
            "--input",
            "fixtures/hyperliquid-combined-v2.jsonl",
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
        std::fs::read("fixtures/hyperliquid-combined-v2.observations.jsonl").unwrap()
    );
    let report: serde_json::Value = serde_json::from_slice(&output.stderr).unwrap();
    assert_eq!(report["feeds"]["normalization_version"], 2);
    assert_eq!(report["feeds"]["all_required_fresh_observed"], true);
}

#[test]
fn invalid_profile_timing_and_ambiguous_legacy_flags_fail_before_creation() {
    for flags in [
        vec!["--feed-profile", "combined", "--bbo-stale-after-ms", "0"],
        vec!["--feed-profile", "bbo", "--feed-timer-ms", "251"],
        vec!["--feed-profile", "combined", "--stale-after-secs", "20"],
        vec!["--bbo-stale-after-ms", "50"],
    ] {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("capture.jsonl");
        let output = Command::new(env!("CARGO_BIN_EXE_giethoorn"))
            .arg("capture")
            .args(flags)
            .arg("--output")
            .arg(&path)
            .output()
            .unwrap();
        assert!(!output.status.success());
        assert!(!path.exists());
    }
}

#[test]
fn corrupt_input_exits_unsuccessfully_with_a_diagnostic() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("invalid.jsonl");
    std::fs::write(&path, b"not-json\n").unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_giethoorn"))
        .args(["replay", "--input"])
        .arg(path)
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).contains("line 1"));
}

#[test]
fn zero_capture_duration_is_rejected_before_creating_a_file() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("capture.jsonl");
    let output = Command::new(env!("CARGO_BIN_EXE_giethoorn"))
        .args(["capture", "--duration-secs", "0", "--output"])
        .arg(&path)
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert!(!path.exists());
}

#[test]
fn inspect_emits_a_single_diagnostic_json_without_quote_stream_or_stderr() {
    let output = Command::new(env!("CARGO_BIN_EXE_giethoorn"))
        .args(["inspect", "--input", "fixtures/hyperliquid-btc.jsonl"])
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(output.stderr.is_empty());
    let report: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(report["status"], "completed");
    assert_eq!(report["two_sided_snapshots"], 3);
    assert_eq!(report["max_snapshot_gap_ns"], 2_000_000);
}

#[test]
fn overflowing_supervisor_scheduling_is_rejected_before_creating_artifacts() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("supervision");
    let output = Command::new(env!("CARGO_BIN_EXE_giethoorn"))
        .args(["supervise", "--output-dir"])
        .arg(&path)
        .args([
            "--duration-secs",
            "2",
            "--sample-interval-secs",
            "18446744073709551615",
        ])
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert!(!path.exists());
    assert!(String::from_utf8_lossy(&output.stderr).contains("sample interval is too large"));
}

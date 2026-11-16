mod common;

use giethoorn::event::Event;
use giethoorn::inspect::{InspectionStatus, inspect};

#[test]
fn fixture_metrics_distinguish_snapshot_gaps_from_reconnection_gaps() {
    let report = inspect(
        std::path::Path::new("fixtures/hyperliquid-btc.jsonl"),
        false,
    )
    .unwrap();
    assert_eq!(report.status, InspectionStatus::Completed);
    assert_eq!(report.session.records, 20);
    assert_eq!(report.recorded_duration_ns, 19_000_000);
    assert_eq!(report.two_sided_snapshots, 3);
    assert_eq!(report.one_sided_snapshots, 0);
    assert_eq!(report.max_snapshot_gap_ns, Some(2_000_000));
    assert_eq!(report.max_first_snapshot_wait_ns, Some(3_000_000));
    assert_eq!(report.max_disconnected_ns, Some(3_000_000));
    assert_eq!(report.snapshot_age_at_end_ns, Some(2_000_000));
    assert_eq!(report.successful_connections, 2);
    assert_eq!(report.connection_errors, 0);
    assert!(report.file_bytes > 0);
}

#[test]
fn completed_failed_session_is_not_reported_as_successful_collection() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("failed.jsonl");
    let mut records = common::start();
    records.push(common::event(
        4,
        1,
        Event::ConnectionError {
            message: "timeout".into(),
        },
    ));
    records.push(common::event(
        5,
        1,
        Event::ConnectionClosed {
            reason: "timeout".into(),
        },
    ));
    records.push(common::event(
        6,
        0,
        Event::SessionEnded {
            reason: "failed".into(),
        },
    ));
    std::fs::write(&path, common::encode(&records)).unwrap();
    let report = inspect(&path, false).unwrap();
    assert_eq!(report.status, InspectionStatus::Failed);
    assert_eq!(report.connection_errors, 1);
    assert!(report.session.complete);
    assert!(report.snapshot_age_at_end_ns.is_none());
}

#[test]
fn recovery_reports_an_incomplete_session_and_preserves_negative_clock_delta() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("crash.jsonl");
    std::fs::write(&path, common::encode(&common::session()[..4])).unwrap();
    assert!(inspect(&path, false).is_err());
    let report = inspect(&path, true).unwrap();
    assert_eq!(report.status, InspectionStatus::Incomplete);
    assert_eq!(report.max_snapshot_gap_ns, None);
    let range = report.observed_source_clock_delta.unwrap();
    assert!(range.min_ms < 0);
    assert_eq!(range.min_ms, range.max_ms);
}

#[test]
fn one_sided_observations_are_not_counted_as_usable_midprices() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("empty-side.jsonl");
    let mut records = common::session();
    records[3].event = Event::TextReceived { text: r#"{"channel":"l2Book","data":{"coin":"BTC","time":100,"levels":[[],[{"px":"102","sz":"1","n":1}]]}}"#.into() };
    std::fs::write(&path, common::encode(&records)).unwrap();
    let report = inspect(&path, false).unwrap();
    assert_eq!(report.status, InspectionStatus::NoUsableData);
    assert_eq!(report.two_sided_snapshots, 0);
    assert_eq!(report.one_sided_snapshots, 1);
}

#[test]
fn recovered_connection_errors_remain_visible_in_a_completed_capture() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("recovered.jsonl");
    let mut records = common::session();
    records.insert(
        3,
        common::event(
            4,
            1,
            Event::ConnectionError {
                message: "diagnostic".into(),
            },
        ),
    );
    for (i, record) in records.iter_mut().enumerate() {
        record.sequence = (i + 1) as u64;
        record.monotonic_ns = record.sequence * 10;
    }
    std::fs::write(&path, common::encode(&records)).unwrap();
    let report = inspect(&path, false).unwrap();
    assert_eq!(
        report.status,
        InspectionStatus::CompletedWithConnectionErrors
    );
    assert_eq!(report.connection_errors, 1);
    assert_eq!(report.two_sided_snapshots, 1);
}

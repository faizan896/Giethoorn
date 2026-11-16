mod common;

use std::io::Cursor;

use giethoorn::event::{Event, MAX_RECORD_BYTES};
use giethoorn::journal::{Journal, JournalLimits, replay, replay_reader};

use common::{encode, session};

#[test]
fn exclusive_creation_preserves_existing_data() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("capture.jsonl");
    std::fs::write(&path, b"precious data").unwrap();
    assert!(Journal::create(&path).is_err());
    assert_eq!(std::fs::read(path).unwrap(), b"precious data");
}

#[test]
fn writer_produces_a_replayable_session_with_contiguous_sequences() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("capture.jsonl");
    let mut journal = Journal::create(&path).unwrap();
    for record in session() {
        journal.append(record.connection_id, record.event).unwrap();
    }
    let report = replay(&path, false, |_| Ok(())).unwrap();
    assert_eq!(report.records, 6);
    assert_eq!(report.snapshots, 1);
    assert!(report.complete);
}

#[test]
fn crash_fragment_is_only_accepted_in_explicit_recovery_mode() {
    let records = session();
    let mut input = encode(&records[..4]);
    input.extend_from_slice(b"{\"schema_version\":1,");
    assert!(replay_reader(Cursor::new(&input), false, |_| Ok(())).is_err());
    let report = replay_reader(Cursor::new(&input), true, |_| Ok(())).unwrap();
    assert_eq!(report.records, 4);
    assert_eq!(report.snapshots, 1);
    assert!(!report.complete);
}

#[test]
fn missing_end_marker_is_not_a_complete_session() {
    let input = encode(&session()[..5]);
    assert!(replay_reader(Cursor::new(&input), false, |_| Ok(())).is_err());
    assert!(
        !replay_reader(Cursor::new(&input), true, |_| Ok(()))
            .unwrap()
            .complete
    );
}

#[test]
fn recovery_never_skips_corruption_in_a_complete_line() {
    let mut input = encode(&session()[..3]);
    input.extend_from_slice(b"not-json\n");
    assert!(replay_reader(Cursor::new(input), true, |_| Ok(())).is_err());
}

#[test]
fn appended_data_after_session_end_is_rejected_including_in_recovery_mode() {
    let mut input = encode(&session());
    input.extend_from_slice(b"{");
    assert!(replay_reader(Cursor::new(input), true, |_| Ok(())).is_err());
    let mut records = session();
    let mut extra = records.last().unwrap().clone();
    extra.sequence += 1;
    extra.event = Event::ConnectionOpened;
    records.push(extra);
    assert!(replay_reader(Cursor::new(encode(&records)), true, |_| Ok(())).is_err());
}

#[test]
fn empty_journal_and_oversized_line_are_rejected() {
    assert!(replay_reader(Cursor::new(b""), true, |_| Ok(())).is_err());
    assert!(
        replay_reader(Cursor::new(vec![b' '; MAX_RECORD_BYTES + 1]), true, |_| Ok(
            ()
        ))
        .is_err()
    );
}

#[test]
fn output_errors_propagate_instead_of_reporting_a_successful_replay() {
    let error = replay_reader(Cursor::new(encode(&session())), false, |_| {
        anyhow::bail!("output failed")
    })
    .unwrap_err();
    assert!(error.to_string().contains("output failed"));
}

#[test]
fn size_guard_keeps_the_previous_valid_prefix_and_never_exceeds_the_limit() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("capture.jsonl");
    let mut journal = Journal::create_with_limits(
        &path,
        JournalLimits {
            max_bytes: 512,
            min_free_bytes: 0,
        },
    )
    .unwrap();
    journal.append(0, session()[0].event.clone()).unwrap();
    let before = std::fs::read(&path).unwrap();
    let error = journal
        .append(
            1,
            Event::TextSent {
                text: "x".repeat(1024),
            },
        )
        .unwrap_err();
    assert!(error.to_string().contains("journal size limit reached"));
    assert_eq!(std::fs::read(&path).unwrap(), before);
    assert!(before.len() <= 512);
    let report = replay(&path, true, |_| Ok(())).unwrap();
    assert_eq!(report.records, 1);
    assert!(!report.complete);
}

#[test]
fn disk_reserve_guard_rejects_startup_without_creating_a_journal() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("capture.jsonl");
    let result = Journal::create_with_limits(
        &path,
        JournalLimits {
            max_bytes: 512,
            min_free_bytes: u64::MAX,
        },
    );
    let error = match result {
        Ok(_) => panic!("impossible reserve accepted"),
        Err(error) => error,
    };
    assert!(error.to_string().contains("free disk space guard"));
    assert!(!path.exists());
}

#[test]
fn zero_size_limit_is_rejected_without_creating_a_journal() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("capture.jsonl");
    assert!(
        Journal::create_with_limits(
            &path,
            JournalLimits {
                max_bytes: 0,
                min_free_bytes: 0
            }
        )
        .is_err()
    );
    assert!(!path.exists());
}

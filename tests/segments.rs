mod common;

use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use giethoorn::engine::Engine;
use giethoorn::event::{Event, Record};
use giethoorn::inspect::{InspectionStatus, inspect};
use giethoorn::journal::{Journal, replay};
use giethoorn::segments::{INDEX_NAME, RecordingFormat, SegmentLimits};
use serde_json::Value;

fn limits() -> SegmentLimits {
    SegmentLimits {
        max_segment_bytes: 600,
        max_session_bytes: 1024 * 1024,
        min_free_bytes: 0,
    }
}

fn completed(path: &Path) -> Vec<u8> {
    let mut journal = Journal::create_segmented(path, limits()).unwrap();
    let mut engine = Engine::default();
    let mut quotes = Vec::new();
    for record in common::session() {
        let record = journal.append(record.connection_id, record.event).unwrap();
        if let Some(quote) = engine.apply(&record).unwrap() {
            serde_json::to_writer(&mut quotes, &quote).unwrap();
            quotes.push(b'\n');
        }
    }
    journal.finish().unwrap();
    quotes
}

fn data_files(path: &Path) -> Vec<PathBuf> {
    let mut files: Vec<_> = fs::read_dir(path)
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .filter(|p| {
            p.file_name()
                .unwrap()
                .to_string_lossy()
                .starts_with("segment-")
        })
        .collect();
    files.sort();
    files
}

fn index(path: &Path) -> Vec<Value> {
    fs::read_to_string(path.join(INDEX_NAME))
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect()
}

fn write_index(path: &Path, entries: &[Value]) {
    let mut file = fs::File::create(path.join(INDEX_NAME)).unwrap();
    for entry in entries {
        serde_json::to_writer(&mut file, entry).unwrap();
        file.write_all(b"\n").unwrap();
    }
}

fn assert_rejected_without_quotes(path: &Path, allow_incomplete: bool) -> String {
    let mut count = 0;
    let error = replay(path, allow_incomplete, |_| {
        count += 1;
        Ok(())
    })
    .unwrap_err();
    assert_eq!(
        count, 0,
        "container validation emitted quotes before rejecting its structure/checksums"
    );
    format!("{error:#}")
}

#[test]
fn rotation_preserves_one_event_sequence_and_byte_identical_quotes() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("session");
    let live = completed(&path);
    let files = data_files(&path);
    assert!(files.len() >= 2);
    let mut records = Vec::new();
    for file in &files {
        assert!(fs::metadata(file).unwrap().len() <= limits().max_segment_bytes);
        for line in fs::read_to_string(file).unwrap().lines() {
            records.push(serde_json::from_str::<Record>(line).unwrap());
        }
    }
    assert_eq!(
        records.iter().map(|r| r.sequence).collect::<Vec<_>>(),
        vec![1, 2, 3, 4, 5, 6]
    );
    let mut replayed = Vec::new();
    let report = replay(&path, false, |quote| {
        serde_json::to_writer(&mut replayed, quote)?;
        replayed.push(b'\n');
        Ok(())
    })
    .unwrap();
    assert_eq!(live, replayed);
    assert_eq!(report.connections, 1);
    let diagnostic = inspect(&path, false).unwrap();
    assert_eq!(diagnostic.storage.format, RecordingFormat::SegmentedV1);
    assert!(diagnostic.storage.finalized);
    assert_eq!(diagnostic.storage.sealed_segments, files.len() as u64);
    let actual: u64 = fs::read_dir(&path)
        .unwrap()
        .map(|e| e.unwrap().metadata().unwrap().len())
        .sum();
    assert_eq!(diagnostic.file_bytes, actual);
}

#[test]
fn corruption_in_a_later_sealed_segment_is_detected_before_any_quote() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("session");
    completed(&path);
    let last = data_files(&path).pop().unwrap();
    let original = fs::read(&last).unwrap();
    let mut records: Vec<Record> = String::from_utf8(original.clone())
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect();
    records[0].local_time_ns -= 1;
    let altered = common::encode(&records);
    assert_eq!(original.len(), altered.len());
    fs::write(&last, altered).unwrap();
    for recovery in [false, true] {
        assert!(assert_rejected_without_quotes(&path, recovery).contains("checksum mismatch"));
    }
}

#[test]
fn missing_truncated_and_extra_segments_are_never_ignored() {
    for mutation in ["missing", "truncated", "extra"] {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("session");
        completed(&path);
        let file = data_files(&path)[0].clone();
        match mutation {
            "missing" => fs::remove_file(file).unwrap(),
            "truncated" => {
                let mut bytes = fs::read(&file).unwrap();
                bytes.pop();
                fs::write(file, bytes).unwrap();
            }
            _ => fs::write(path.join("segment-99999999.jsonl"), b"unexpected").unwrap(),
        }
        assert_rejected_without_quotes(&path, true);
    }
}

#[test]
fn index_rejects_traversal_versions_ranges_and_mismatched_footers() {
    for mutation in ["path", "number", "range", "version", "footer"] {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("session");
        completed(&path);
        let mut entries = index(&path);
        match mutation {
            "path" => entries[1]["file"] = serde_json::json!("../elsewhere.jsonl"),
            "number" => entries[1]["number"] = serde_json::json!(2),
            "range" => entries[1]["first_sequence"] = serde_json::json!(2),
            "version" => entries[0]["container_version"] = serde_json::json!(999),
            _ => {
                let last = entries.last_mut().unwrap();
                last["records"] = serde_json::json!(999);
            }
        }
        write_index(&path, &entries);
        assert_rejected_without_quotes(&path, true);
    }
}

#[test]
fn writer_lock_prevents_replay_and_recovery_of_an_active_container() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("session");
    let mut journal = Journal::create_segmented(&path, limits()).unwrap();
    journal
        .append(0, common::session()[0].event.clone())
        .unwrap();
    assert!(assert_rejected_without_quotes(&path, true).contains("busy"));
    drop(journal);
    let report = replay(&path, true, |_| Ok(())).unwrap();
    assert_eq!(report.records, 1);
    assert!(!report.complete);
}

#[test]
fn interrupted_data_tail_requires_recovery_and_only_discards_a_final_fragment() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("session");
    let mut journal = Journal::create_segmented(&path, limits()).unwrap();
    for record in common::session().into_iter().take(4) {
        journal.append(record.connection_id, record.event).unwrap();
    }
    drop(journal);
    let tail = data_files(&path).pop().unwrap();
    fs::OpenOptions::new()
        .append(true)
        .open(tail)
        .unwrap()
        .write_all(b"{\"schema_version\":")
        .unwrap();
    assert_rejected_without_quotes(&path, false);
    let report = replay(&path, true, |_| Ok(())).unwrap();
    assert_eq!(report.records, 4);
    assert_eq!(report.snapshots, 1);
    assert!(!report.complete);
    let diagnostics = inspect(&path, true).unwrap();
    assert_eq!(diagnostics.status, InspectionStatus::Incomplete);
    assert!(diagnostics.storage.has_unsealed_tail);
}

#[test]
fn corrupt_complete_record_in_an_unsealed_tail_still_fails_recovery() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("session");
    let mut journal = Journal::create_segmented(&path, limits()).unwrap();
    journal
        .append(0, common::session()[0].event.clone())
        .unwrap();
    drop(journal);
    let tail = data_files(&path).pop().unwrap();
    fs::OpenOptions::new()
        .append(true)
        .open(tail)
        .unwrap()
        .write_all(b"not-json\n")
        .unwrap();
    assert!(replay(&path, true, |_| Ok(())).is_err());
}

#[test]
fn an_event_end_without_a_container_footer_remains_incomplete() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("session");
    completed(&path);
    let mut entries = index(&path);
    entries.pop();
    write_index(&path, &entries);
    assert_rejected_without_quotes(&path, false);
    let report = replay(&path, true, |_| Ok(())).unwrap();
    assert_eq!(report.records, 6);
    assert!(!report.complete);
    assert_eq!(report.end_reason.as_deref(), Some("duration_elapsed"));
    assert_eq!(
        inspect(&path, true).unwrap().status,
        InspectionStatus::Incomplete
    );
}

#[test]
fn crash_between_data_sync_and_seal_commit_recovers_the_one_unindexed_file() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("session");
    completed(&path);
    let mut entries = index(&path);
    entries.pop();
    let final_seal = entries.pop().unwrap();
    write_index(&path, &entries);
    let bytes = serde_json::to_vec(&final_seal).unwrap();
    fs::OpenOptions::new()
        .append(true)
        .open(path.join(INDEX_NAME))
        .unwrap()
        .write_all(&bytes[..bytes.len() / 2])
        .unwrap();
    let report = replay(&path, true, |_| Ok(())).unwrap();
    assert_eq!(report.records, 6);
    assert!(!report.complete);
    assert!(inspect(&path, true).unwrap().storage.has_unsealed_tail);
}

#[test]
fn corrupt_index_lines_and_bytes_after_the_footer_are_rejected_in_recovery() {
    for suffix in [b"{\n".as_slice(), b"{".as_slice()] {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("session");
        completed(&path);
        fs::OpenOptions::new()
            .append(true)
            .open(path.join(INDEX_NAME))
            .unwrap()
            .write_all(suffix)
            .unwrap();
        assert_rejected_without_quotes(&path, true);
    }
}

#[test]
fn whole_session_budget_includes_index_growth_and_never_deletes_old_segments() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("session");
    let budget = 4096;
    let mut journal = Journal::create_segmented(
        &path,
        SegmentLimits {
            max_session_bytes: budget,
            ..limits()
        },
    )
    .unwrap();
    for record in common::start() {
        journal.append(record.connection_id, record.event).unwrap();
    }
    let mut successful = 3;
    for i in 0..100 {
        match journal.append(1, common::book(100 + i, "1", "2")) {
            Ok(_) => successful += 1,
            Err(error) => {
                assert!(error.to_string().contains("whole-session storage limit"));
                break;
            }
        }
    }
    assert!(successful > 3 && successful < 103);
    let prior: Vec<_> = data_files(&path)
        .into_iter()
        .map(|p| (p.clone(), fs::read(p).unwrap()))
        .collect();
    assert!(journal.append(1, Event::ConnectionOpened).is_err());
    drop(journal);
    for (file, bytes) in prior {
        assert_eq!(fs::read(file).unwrap(), bytes);
    }
    let total: u64 = fs::read_dir(&path)
        .unwrap()
        .map(|e| e.unwrap().metadata().unwrap().len())
        .sum();
    assert!(total <= budget);
    let report = replay(&path, true, |_| Ok(())).unwrap();
    assert_eq!(report.records, successful);
    assert!(!report.complete);
}

#[test]
fn existing_directory_and_oversized_records_are_not_overwritten_or_split() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("session");
    fs::create_dir(&path).unwrap();
    fs::write(path.join("keep.txt"), b"keep").unwrap();
    assert!(Journal::create_segmented(&path, limits()).is_err());
    assert_eq!(fs::read(path.join("keep.txt")).unwrap(), b"keep");
    let tiny = directory.path().join("tiny");
    let mut writer = Journal::create_segmented(
        &tiny,
        SegmentLimits {
            max_segment_bytes: 10,
            ..limits()
        },
    )
    .unwrap();
    assert!(
        writer
            .append(0, common::session()[0].event.clone())
            .unwrap_err()
            .to_string()
            .contains("whole record")
    );
    assert!(data_files(&tiny).is_empty());
}

#[test]
fn finish_requires_a_session_end_and_cannot_be_repeated() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("session");
    let mut writer = Journal::create_segmented(&path, limits()).unwrap();
    assert!(writer.finish().is_err());
    for record in common::session() {
        writer.append(record.connection_id, record.event).unwrap();
    }
    writer.finish().unwrap();
    assert!(writer.finish().is_err());
    assert!(
        writer
            .append(0, common::session()[0].event.clone())
            .is_err()
    );
}

#[cfg(unix)]
#[test]
fn sealed_segment_symlinks_are_rejected() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("session");
    completed(&path);
    let first = data_files(&path)[0].clone();
    let elsewhere = directory.path().join("outside.jsonl");
    fs::rename(&first, &elsewhere).unwrap();
    std::os::unix::fs::symlink(&elsewhere, &first).unwrap();
    assert!(assert_rejected_without_quotes(&path, true).contains("regular files"));
}

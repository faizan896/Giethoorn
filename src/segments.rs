//! Segmented container v1 around one explicit event schema per recording.
//!
//! A data file is synchronized before its SHA-256 descriptor is appended and
//! synchronized in index.jsonl. At most one unindexed tail can exist after a
//! crash. Recovery never excuses a bad checksum in an indexed segment.

use std::fs::{self, File, OpenOptions};
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::event::{FEED_SCHEMA_VERSION, MAX_RECORD_BYTES, Record, SCHEMA_VERSION};
use crate::journal::JournalLimits;

pub const CONTAINER_VERSION: u16 = 1;
pub const INDEX_NAME: &str = "index.jsonl";
const MAX_INDEX_LINE: usize = 4096;
const MAX_SEGMENTS: u64 = 65_536;
const MAX_INDEX_BYTES: u64 = (MAX_SEGMENTS + 2) * 512;
const FINALIZATION_RESERVE: u64 = 1024;

#[derive(Debug, Clone, Copy)]
pub struct SegmentLimits {
    pub max_segment_bytes: u64,
    /// Sum of index and all data-file lengths, not allocated filesystem blocks.
    pub max_session_bytes: u64,
    pub min_free_bytes: u64,
}

impl Default for SegmentLimits {
    fn default() -> Self {
        Self {
            max_segment_bytes: 64 * 1024 * 1024,
            max_session_bytes: 1024 * 1024 * 1024,
            min_free_bytes: 1024 * 1024 * 1024,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
enum IndexEntry {
    Header {
        container_version: u16,
        event_schema_version: u16,
        max_segment_bytes: u64,
        max_session_bytes: u64,
    },
    Segment {
        number: u64,
        file: String,
        bytes: u64,
        first_sequence: u64,
        last_sequence: u64,
        sha256: String,
    },
    End {
        segments: u64,
        records: u64,
        data_bytes: u64,
    },
}

fn filename(number: u64) -> String {
    format!("segment-{number:08}.jsonl")
}

fn encoded(entry: &IndexEntry) -> Result<Vec<u8>> {
    let mut bytes = serde_json::to_vec(entry)?;
    bytes.push(b'\n');
    ensure!(
        bytes.len() <= MAX_INDEX_LINE,
        "index entry exceeds size limit"
    );
    Ok(bytes)
}

fn sync_directory(path: &Path) -> Result<()> {
    #[cfg(unix)]
    File::open(path)?
        .sync_all()
        .context("sync recording directory")?;
    Ok(())
}

struct ActiveSegment {
    file: File,
    number: u64,
    bytes: u64,
    first_sequence: u64,
    last_sequence: u64,
    hash: Sha256,
}

impl ActiveSegment {
    fn descriptor(&self) -> Result<Vec<u8>> {
        encoded(&IndexEntry::Segment {
            number: self.number,
            file: filename(self.number),
            bytes: self.bytes,
            first_sequence: self.first_sequence,
            last_sequence: self.last_sequence,
            sha256: format!("{:x}", self.hash.clone().finalize()),
        })
    }
}

pub(crate) struct SegmentWriter {
    directory: PathBuf,
    index: File,
    limits: SegmentLimits,
    active: Option<ActiveSegment>,
    sealed: u64,
    records: u64,
    data_bytes: u64,
    total_bytes: u64,
    finished: bool,
    event_schema_version: u16,
}

impl SegmentWriter {
    pub(crate) fn create(
        directory: &Path,
        limits: SegmentLimits,
        event_schema_version: u16,
    ) -> Result<Self> {
        ensure!(
            limits.max_segment_bytes > 0,
            "segment byte limit must be positive"
        );
        let header = encoded(&IndexEntry::Header {
            container_version: CONTAINER_VERSION,
            event_schema_version,
            max_segment_bytes: limits.max_segment_bytes,
            max_session_bytes: limits.max_session_bytes,
        })?;
        ensure!(
            limits.max_session_bytes > header.len() as u64 + FINALIZATION_RESERVE,
            "session budget must exceed the index header and 1024-byte finalization reserve"
        );
        let parent = directory
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
            .unwrap_or(Path::new("."));
        JournalLimits {
            max_bytes: u64::MAX,
            min_free_bytes: limits.min_free_bytes,
        }
        .check_space(parent, header.len() as u64)?;
        // A fresh directory owns all its names. Never adopt or overwrite an old run.
        fs::create_dir(directory)
            .with_context(|| format!("create NEW recording directory {}", directory.display()))?;
        sync_directory(parent)?;
        let mut index = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .open(directory.join(INDEX_NAME))?;
        fs2::FileExt::try_lock_exclusive(&index).context("lock recording writer")?;
        index.write_all(&header)?;
        index.sync_all()?;
        sync_directory(directory)?;
        Ok(Self {
            directory: directory.to_path_buf(),
            index,
            limits,
            active: None,
            sealed: 0,
            records: 0,
            data_bytes: 0,
            total_bytes: header.len() as u64,
            finished: false,
            event_schema_version,
        })
    }

    pub(crate) fn append(&mut self, record: &Record, bytes: &[u8]) -> Result<()> {
        ensure!(!self.finished, "segmented recording is already finalized");
        ensure!(
            record.schema_version == self.event_schema_version,
            "writer schema differs from container header"
        );
        let length = bytes.len() as u64;
        ensure!(
            length <= self.limits.max_segment_bytes,
            "whole record exceeds segment byte limit"
        );
        ensure!(
            record.sequence == self.records + 1,
            "writer sequence is not contiguous"
        );
        let rotate = self.active.as_ref().is_some_and(|active| {
            active
                .bytes
                .checked_add(length)
                .is_none_or(|size| size > self.limits.max_segment_bytes)
        });
        let seal_length = if rotate {
            self.active
                .as_ref()
                .context("missing active segment")?
                .descriptor()?
                .len() as u64
        } else {
            0
        };
        let needed = length
            .checked_add(seal_length)
            .context("recording size overflow")?;
        let projected = self
            .total_bytes
            .checked_add(needed)
            .and_then(|n| n.checked_add(FINALIZATION_RESERVE))
            .context("recording size overflow")?;
        ensure!(
            projected <= self.limits.max_session_bytes,
            "whole-session storage limit reached; capture stopped (recover with --allow-incomplete)"
        );
        let needs_file = self.active.is_none() || rotate;
        if needs_file {
            let next = self.sealed + 1 + u64::from(rotate);
            ensure!(
                next <= MAX_SEGMENTS,
                "recording segment-count limit reached"
            );
        }
        self.check_space(needed)?;
        if rotate {
            self.seal()?;
        }
        if self.active.is_none() {
            let number = self.sealed + 1;
            let file = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(self.directory.join(filename(number)))?;
            file.sync_all()?;
            sync_directory(&self.directory)?;
            self.active = Some(ActiveSegment {
                file,
                number,
                bytes: 0,
                first_sequence: record.sequence,
                last_sequence: record.sequence,
                hash: Sha256::new(),
            });
        }
        let active = self.active.as_mut().context("missing active segment")?;
        active
            .file
            .write_all(bytes)
            .context("write journal segment")?;
        active.file.sync_data().context("sync journal segment")?;
        active.hash.update(bytes);
        active.bytes += length;
        active.last_sequence = record.sequence;
        self.records += 1;
        self.data_bytes += length;
        self.total_bytes += length;
        Ok(())
    }

    fn check_space(&self, incoming: u64) -> Result<()> {
        JournalLimits {
            max_bytes: u64::MAX,
            min_free_bytes: self.limits.min_free_bytes,
        }
        .check_space(&self.directory, incoming)
    }

    fn append_index(&mut self, bytes: &[u8]) -> Result<()> {
        let projected = self
            .total_bytes
            .checked_add(bytes.len() as u64)
            .context("index size overflow")?;
        ensure!(
            projected <= self.limits.max_session_bytes,
            "whole-session storage limit reached while finalizing"
        );
        self.check_space(bytes.len() as u64)?;
        self.index
            .write_all(bytes)
            .context("append recording index")?;
        self.index.sync_data().context("sync recording index")?;
        self.total_bytes = projected;
        Ok(())
    }

    fn seal(&mut self) -> Result<()> {
        let active = self.active.as_ref().context("no segment to seal")?;
        ensure!(active.bytes > 0, "cannot seal empty segment");
        active.file.sync_all()?;
        let descriptor = active.descriptor()?;
        ensure!(
            descriptor.len() as u64 <= FINALIZATION_RESERVE / 2,
            "segment descriptor exceeds reserved space"
        );
        self.append_index(&descriptor)?;
        self.active = None;
        self.sealed += 1;
        Ok(())
    }

    pub(crate) fn finish(&mut self) -> Result<()> {
        ensure!(!self.finished, "segmented recording is already finalized");
        if self.active.is_some() {
            self.seal()?;
        }
        let end = encoded(&IndexEntry::End {
            segments: self.sealed,
            records: self.records,
            data_bytes: self.data_bytes,
        })?;
        ensure!(
            end.len() as u64 <= FINALIZATION_RESERVE / 2,
            "index footer exceeds reserved space"
        );
        self.append_index(&end)?;
        self.index.sync_all()?;
        self.finished = true;
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum RecordingFormat {
    SingleFile,
    SegmentedV1,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct StorageSummary {
    pub format: RecordingFormat,
    /// Sum of data and index bytes; no allocation overhead or redirected output.
    pub file_bytes: u64,
    pub sealed_segments: u64,
    pub has_unsealed_tail: bool,
    pub finalized: bool,
}

/// The shared index lock excludes cooperating writers during validation/replay.
pub(crate) struct RecordingInput {
    pub reader: Box<dyn Read>,
    pub summary: StorageSummary,
    pub expected_records: Option<u64>,
    pub event_schema_version: Option<u16>,
    // Keep the cooperative shared lock until replay/inspection is finished.
    _index_lock: Option<File>,
}

struct FilesReader {
    files: std::collections::VecDeque<(PathBuf, u64)>,
    current: Option<File>,
}

impl Read for FilesReader {
    fn read(&mut self, buffer: &mut [u8]) -> std::io::Result<usize> {
        if buffer.is_empty() {
            return Ok(0);
        }
        loop {
            if self.current.is_none() {
                let Some((path, expected_bytes)) = self.files.pop_front() else {
                    return Ok(0);
                };
                if !fs::symlink_metadata(&path)?.file_type().is_file() {
                    return Err(std::io::Error::other(
                        "recording entry changed during replay",
                    ));
                }
                let file = File::open(path)?;
                if file.metadata()?.len() != expected_bytes {
                    return Err(std::io::Error::other(
                        "recording size changed during replay",
                    ));
                }
                self.current = Some(file);
            }
            let size = self
                .current
                .as_mut()
                .expect("file was opened")
                .read(buffer)?;
            if size > 0 {
                return Ok(size);
            }
            self.current = None;
        }
    }
}

impl RecordingInput {
    pub(crate) fn open(path: &Path, allow_incomplete: bool) -> Result<Self> {
        if path.is_dir() {
            return Self::segmented(path, allow_incomplete);
        }
        let file = File::open(path).with_context(|| format!("open journal {}", path.display()))?;
        let size = file.metadata()?.len();
        Ok(Self {
            reader: Box::new(file),
            summary: StorageSummary {
                format: RecordingFormat::SingleFile,
                file_bytes: size,
                sealed_segments: 0,
                has_unsealed_tail: false,
                finalized: false,
            },
            expected_records: None,
            event_schema_version: None,
            _index_lock: None,
        })
    }

    fn segmented(path: &Path, allow_incomplete: bool) -> Result<Self> {
        // The container directory itself may be chosen via a symlink by a user;
        // entries inside it must be plain files with exactly the canonical names.
        let index_path = path.join(INDEX_NAME);
        ensure_regular(&index_path)?;
        let index = File::open(&index_path)?;
        fs2::FileExt::try_lock_shared(&index)
            .context("recording is busy; stop the writer before replay or recovery")?;
        ensure!(
            index.metadata()?.len() <= MAX_INDEX_BYTES,
            "recording index exceeds size limit"
        );
        let mut input = BufReader::new(index.try_clone()?);
        let header = read_index_line(&mut input, false)?.context("recording index is empty")?;
        let IndexEntry::Header {
            container_version,
            event_schema_version,
            max_segment_bytes,
            max_session_bytes,
        } = header
        else {
            bail!("recording index must begin with a header");
        };
        ensure!(
            container_version == CONTAINER_VERSION,
            "unsupported recording container version"
        );
        ensure!(
            matches!(event_schema_version, SCHEMA_VERSION | FEED_SCHEMA_VERSION),
            "unsupported recording event schema"
        );
        ensure!(
            max_segment_bytes > 0 && max_session_bytes > 0,
            "invalid recording storage limits"
        );
        let mut files = std::collections::VecDeque::new();
        let mut expected_names = std::collections::BTreeSet::from([INDEX_NAME.to_string()]);
        let mut total_bytes = index.metadata()?.len();
        ensure!(
            total_bytes <= max_session_bytes,
            "index exceeds declared whole-session limit"
        );
        let mut data_bytes = 0_u64;
        let mut sealed = 0_u64;
        let mut last_sequence = 0_u64;
        let mut finalized = false;
        let mut expected_records = None;
        while let Some(entry) = read_index_line(&mut input, allow_incomplete && !finalized)? {
            ensure!(!finalized, "unexpected index entry after recording end");
            match entry {
                IndexEntry::Segment {
                    number,
                    file,
                    bytes,
                    first_sequence,
                    last_sequence: last,
                    sha256,
                } => {
                    ensure!(
                        number == sealed + 1 && number <= MAX_SEGMENTS,
                        "segment numbers must be contiguous"
                    );
                    ensure!(file == filename(number), "noncanonical segment filename");
                    ensure!(
                        bytes > 0 && bytes <= max_segment_bytes,
                        "invalid segment byte length"
                    );
                    ensure!(
                        Some(first_sequence) == last_sequence.checked_add(1)
                            && last >= first_sequence,
                        "invalid segment sequence range"
                    );
                    ensure!(
                        sha256.len() == 64
                            && sha256
                                .bytes()
                                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c)),
                        "invalid SHA-256 descriptor"
                    );
                    let segment_path = path.join(&file);
                    ensure_regular(&segment_path)?;
                    let mut segment = File::open(&segment_path)?;
                    ensure!(
                        segment.metadata()?.len() == bytes,
                        "segment length mismatch: {file}"
                    );
                    verify_segment(
                        &mut segment,
                        &file,
                        bytes,
                        first_sequence,
                        last,
                        &sha256,
                        event_schema_version,
                    )?;
                    files.push_back((segment_path, bytes));
                    expected_names.insert(file);
                    total_bytes = total_bytes
                        .checked_add(bytes)
                        .context("container byte count overflow")?;
                    ensure!(
                        total_bytes <= max_session_bytes,
                        "recording exceeds declared whole-session limit"
                    );
                    data_bytes = data_bytes
                        .checked_add(bytes)
                        .context("container byte count overflow")?;
                    last_sequence = last;
                    sealed = number;
                }
                IndexEntry::End {
                    segments,
                    records,
                    data_bytes: expected_bytes,
                } => {
                    ensure!(
                        segments == sealed
                            && records == last_sequence
                            && expected_bytes == data_bytes,
                        "recording footer does not match sealed segments"
                    );
                    ensure!(sealed > 0, "finalized recording has no data");
                    finalized = true;
                    expected_records = Some(records);
                }
                IndexEntry::Header { .. } => bail!("duplicate recording header"),
            }
        }
        ensure!(
            finalized || allow_incomplete,
            "recording is not finalized; use --allow-incomplete for recovery"
        );
        let tail_name = filename(sealed + 1);
        let tail_path = path.join(&tail_name);
        let has_tail = fs::symlink_metadata(&tail_path).is_ok();
        if has_tail {
            ensure!(
                !finalized && allow_incomplete,
                "unexpected unsealed segment in finalized recording"
            );
            ensure!(sealed < MAX_SEGMENTS, "too many recording segments");
            ensure_regular(&tail_path)?;
            let file = File::open(&tail_path)?;
            let length = file.metadata()?.len();
            ensure!(
                length <= max_segment_bytes,
                "unsealed segment exceeds configured size"
            );
            total_bytes = total_bytes
                .checked_add(length)
                .context("container byte count overflow")?;
            files.push_back((tail_path, length));
            expected_names.insert(tail_name);
        }
        for entry in fs::read_dir(path)? {
            let entry = entry?;
            let name = entry
                .file_name()
                .into_string()
                .map_err(|_| anyhow::anyhow!("non-UTF-8 recording entry"))?;
            ensure!(
                expected_names.remove(&name),
                "unexpected recording entry: {name}"
            );
        }
        ensure!(
            expected_names.is_empty(),
            "recording is missing expected files"
        );
        ensure!(
            total_bytes <= max_session_bytes,
            "recording exceeds declared whole-session limit"
        );
        Ok(Self {
            reader: Box::new(FilesReader {
                files,
                current: None,
            }),
            summary: StorageSummary {
                format: RecordingFormat::SegmentedV1,
                file_bytes: total_bytes,
                sealed_segments: sealed,
                has_unsealed_tail: has_tail,
                finalized,
            },
            expected_records,
            event_schema_version: Some(event_schema_version),
            _index_lock: Some(index),
        })
    }
}

fn ensure_regular(path: &Path) -> Result<()> {
    ensure!(
        fs::symlink_metadata(path)
            .with_context(|| format!("missing recording file {}", path.display()))?
            .file_type()
            .is_file(),
        "recording entries must be regular files, not symlinks: {}",
        path.display()
    );
    Ok(())
}

fn read_index_line(reader: &mut impl BufRead, allow_fragment: bool) -> Result<Option<IndexEntry>> {
    let mut line = Vec::new();
    let length = Read::take(reader, (MAX_INDEX_LINE + 1) as u64).read_until(b'\n', &mut line)?;
    if length == 0 {
        return Ok(None);
    }
    ensure!(
        length <= MAX_INDEX_LINE,
        "recording index line exceeds size limit"
    );
    if line.last() != Some(&b'\n') {
        ensure!(allow_fragment, "unterminated recording index line");
        return Ok(None);
    }
    Ok(Some(
        serde_json::from_slice(&line).context("invalid recording index JSON")?,
    ))
}

fn verify_segment(
    file: &mut File,
    name: &str,
    bytes: u64,
    first: u64,
    last: u64,
    expected_hash: &str,
    event_schema_version: u16,
) -> Result<()> {
    let mut reader = BufReader::new(file);
    let mut hash = Sha256::new();
    let mut observed_bytes = 0_u64;
    let mut count = 0_u64;
    let mut first_seen = None;
    let mut last_seen = None;
    loop {
        let mut line = Vec::new();
        let length =
            Read::take(&mut reader, (MAX_RECORD_BYTES + 1) as u64).read_until(b'\n', &mut line)?;
        if length == 0 {
            break;
        }
        ensure!(
            length <= MAX_RECORD_BYTES && line.last() == Some(&b'\n'),
            "invalid record boundary in sealed segment {name}"
        );
        hash.update(&line);
        observed_bytes += length as u64;
        let record: Record = serde_json::from_slice(&line)
            .with_context(|| format!("invalid sealed record in {name}"))?;
        ensure!(
            record.schema_version == event_schema_version,
            "sealed record schema differs from container header: {name}"
        );
        first_seen.get_or_insert(record.sequence);
        last_seen = Some(record.sequence);
        count += 1;
    }
    ensure!(
        format!("{:x}", hash.finalize()) == expected_hash,
        "SHA-256 checksum mismatch: {name}"
    );
    ensure!(
        observed_bytes == bytes
            && first_seen == Some(first)
            && last_seen == Some(last)
            && count == last - first + 1,
        "sealed segment sequence or byte-count mismatch: {name}"
    );
    Ok(())
}

//! Derived paper output is reproducible; malformed complete input is terminal.
use super::*;
use anyhow::{Context, Result, ensure};
use std::fs::File;
use std::io::{BufRead, BufReader, Read};
use std::path::Path;

pub fn replay_paper(
    path: &Path,
    allow_incomplete: bool,
    emit: impl FnMut(&PaperUpdate) -> Result<()>,
) -> Result<PaperReport> {
    replay_paper_reader(
        BufReader::new(
            File::open(path).with_context(|| format!("open paper scenario {}", path.display()))?,
        ),
        allow_incomplete,
        emit,
    )
}

pub fn replay_paper_reader(
    mut reader: impl BufRead,
    allow_incomplete: bool,
    mut emit: impl FnMut(&PaperUpdate) -> Result<()>,
) -> Result<PaperReport> {
    let mut engine = PaperEngine::default();
    let mut line = 0;
    loop {
        let mut bytes = Vec::new();
        let length = Read::take(&mut reader, (MAX_PAPER_RECORD_BYTES + 1) as u64)
            .read_until(b'\n', &mut bytes)?;
        if length == 0 {
            break;
        }
        line += 1;
        ensure!(
            length <= MAX_PAPER_RECORD_BYTES,
            "paper record exceeds size limit at line {line}"
        );
        if bytes.last() != Some(&b'\n') {
            ensure!(
                allow_incomplete && !engine.report()?.complete,
                "unterminated paper record at line {line}"
            );
            break;
        }
        let record: PaperRecord = serde_json::from_slice(&bytes)
            .with_context(|| format!("invalid paper record at line {line}"))?;
        let update = engine
            .apply(&record)
            .with_context(|| format!("paper transition failed at line {line}"))?;
        emit(&update)?;
    }
    let report = engine.report()?;
    ensure!(
        allow_incomplete || report.complete,
        "paper scenario has no end event"
    );
    Ok(report)
}

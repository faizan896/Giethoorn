use std::io::{self, Write};
use std::path::PathBuf;
use std::sync::{
    Arc,
    atomic::{AtomicBool, Ordering},
};
use std::time::Duration;

use anyhow::Result;
use clap::{Args, Parser, Subcommand};
use giethoorn::audit::audit_supervision;
use giethoorn::capture::{CaptureOptions, capture, failure_exit_code};
use giethoorn::event::{FeedPolicy, FeedProfile, Network};
use giethoorn::inspect::inspect;
use giethoorn::journal::{JournalLimits, JournalMode, replay};
use giethoorn::paper::{
    RecordingOrigin, export_execution_scenario, export_recorded_market, replay_paper,
};
use giethoorn::segments::SegmentLimits;
use giethoorn::supervisor::{SupervisorOptions, supervise};

#[derive(Args)]
struct MarketArgs {
    #[arg(long, default_value = "BTC")]
    coin: String,
    #[arg(long, value_enum, default_value = "mainnet")]
    network: Network,
    #[arg(long, default_value_t = 60, value_parser = clap::value_parser!(u64).range(1..))]
    duration_secs: u64,
    #[arg(long, default_value_t = 3, value_parser = clap::value_parser!(u32).range(0..=100))]
    max_reconnects: u32,
    #[arg(long, default_value_t = 15, value_parser = clap::value_parser!(u64).range(1..))]
    stale_after_secs: u64,
    /// Explicit schema-2 profile. Omit to preserve legacy depth-only output.
    #[arg(long, value_enum, conflicts_with = "stale_after_secs")]
    feed_profile: Option<FeedProfile>,
    #[arg(long, requires = "feed_profile")]
    depth_stale_after_ms: Option<u64>,
    #[arg(long, requires = "feed_profile")]
    bbo_stale_after_ms: Option<u64>,
    #[arg(long, requires = "feed_profile")]
    feed_timer_ms: Option<u64>,
    /// Preserve this much free space on the recording filesystem (1 GiB).
    #[arg(long, default_value_t = 1024 * 1024 * 1024)]
    min_free_disk_bytes: u64,
    /// Internal parent-liveness contract for supervised collectors.
    #[arg(long, hide = true)]
    parent_pid: Option<u32>,
}

impl MarketArgs {
    fn feed_policy(&self) -> Option<FeedPolicy> {
        self.feed_profile.map(|profile| FeedPolicy {
            profile,
            depth_stale_after_ms: self.depth_stale_after_ms.unwrap_or(15000),
            bbo_stale_after_ms: self.bbo_stale_after_ms.unwrap_or(2000),
            timer_interval_ms: self.feed_timer_ms.unwrap_or(250),
        })
    }

    fn options(self, output: PathBuf, journal_mode: JournalMode) -> CaptureOptions {
        let feed_policy = self.feed_policy();
        CaptureOptions {
            coin: self.coin,
            network: self.network,
            output,
            duration: Duration::from_secs(self.duration_secs),
            max_reconnects: self.max_reconnects,
            stale_after: Duration::from_secs(self.stale_after_secs),
            journal_mode,
            feed_policy,
        }
    }
}

#[derive(Parser)]
#[command(
    version,
    about = "Public market-data capture and deterministic replay. No trading or wallet access."
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Record public Hyperliquid data; legacy depth or an explicit feed profile.
    Capture {
        #[command(flatten)]
        market: MarketArgs,
        /// A NEW file; existing files are never overwritten.
        #[arg(long)]
        output: PathBuf,
        /// Stop before a journal write would exceed this many bytes (256 MiB).
        #[arg(long, default_value_t = 256 * 1024 * 1024, value_parser = clap::value_parser!(u64).range(1..))]
        max_journal_bytes: u64,
    },
    /// Collect into a NEW directory with checksummed rotating segments.
    Collect {
        #[command(flatten)]
        market: MarketArgs,
        #[arg(long)]
        output_dir: PathBuf,
        #[arg(long, default_value_t = 64 * 1024 * 1024, value_parser = clap::value_parser!(u64).range(1..))]
        max_segment_bytes: u64,
        /// Includes all segment files and the append-only index; reserves finalization space.
        #[arg(long, default_value_t = 1024 * 1024 * 1024, value_parser = clap::value_parser!(u64).range(1..))]
        max_session_bytes: u64,
    },
    /// Supervise bounded collector processes, validate output, and safely restart transient failures.
    Supervise {
        #[command(flatten)]
        market: MarketArgs,
        #[arg(long)]
        output_dir: PathBuf,
        #[arg(long, default_value_t = 300, value_parser = clap::value_parser!(u64).range(1..))]
        run_duration_secs: u64,
        #[arg(long, default_value_t = 3, value_parser = clap::value_parser!(u32).range(0..=100))]
        max_restarts: u32,
        #[arg(long, default_value_t = 64 * 1024 * 1024, value_parser = clap::value_parser!(u64).range(1..))]
        max_segment_bytes: u64,
        #[arg(long, default_value_t = 256 * 1024 * 1024, value_parser = clap::value_parser!(u64).range(2048..))]
        max_run_bytes: u64,
        #[arg(long, default_value_t = 1024 * 1024 * 1024, value_parser = clap::value_parser!(u64).range(2048..))]
        max_total_recording_bytes: u64,
        #[arg(long, default_value_t = 5, value_parser = clap::value_parser!(u64).range(1..))]
        sample_interval_secs: u64,
        #[arg(long, default_value_t = 5, value_parser = clap::value_parser!(u64).range(1..))]
        shutdown_grace_secs: u64,
    },
    /// Validate a journal and emit the same quotes as capture, without networking.
    Replay {
        #[arg(long)]
        input: PathBuf,
        /// Recover a valid prefix after a crash. Never ignores a corrupt full line.
        #[arg(long)]
        allow_incomplete: bool,
    },
    /// Validate a recording and summarize its gaps, errors and storage use.
    Inspect {
        #[arg(long)]
        input: PathBuf,
        #[arg(long)]
        allow_incomplete: bool,
    },
    /// Recompute a finalized supervisor's integrity, lifecycle, totals and output.
    AuditSupervision {
        #[arg(long)]
        input: PathBuf,
    },
    /// Replay an explicitly simulated paper scenario offline. Never sends orders.
    PaperReplay {
        #[arg(long)]
        input: PathBuf,
        #[arg(long)]
        allow_incomplete: bool,
    },
    /// Replay a finalized market recording into offline paper marks; no orders or fills.
    PaperMarketReplay {
        #[arg(long)]
        input: PathBuf,
        /// A NEW directory outside the source; its parent must already exist.
        #[arg(long)]
        output_dir: PathBuf,
        /// Explicit operator declaration, never inferred from file contents.
        #[arg(long, value_enum)]
        origin: RecordingOrigin,
        #[arg(long, value_enum, default_value = "bbo")]
        feed: giethoorn::event::FeedKind,
    },
    /// Run fixed IOC scenarios on recorded data with explicit execution assumptions.
    PaperExecutionReplay {
        #[arg(long)]
        input: PathBuf,
        #[arg(long)]
        scenario: PathBuf,
        #[arg(long)]
        output_dir: PathBuf,
        #[arg(long, value_enum)]
        origin: RecordingOrigin,
        #[arg(long, value_enum, default_value = "bbo")]
        feed: giethoorn::event::FeedKind,
    },
}

fn main() -> std::process::ExitCode {
    match run() {
        Ok(()) => std::process::ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("error: {error:#}");
            std::process::ExitCode::from(failure_exit_code(&error))
        }
    }
}

fn run() -> Result<()> {
    let cli = Cli::parse();
    let mut output = io::stdout().lock();
    let report = match cli.command {
        Command::Capture {
            market,
            output: path,
            max_journal_bytes,
        } => {
            let mode = JournalMode::SingleFile(JournalLimits {
                max_bytes: max_journal_bytes,
                min_free_bytes: market.min_free_disk_bytes,
            });
            let stop = shutdown_signal(market.parent_pid)?;
            capture(&market.options(path, mode), &mut output, stop)?
        }
        Command::Collect {
            market,
            output_dir,
            max_segment_bytes,
            max_session_bytes,
        } => {
            let mode = JournalMode::Segmented(SegmentLimits {
                max_segment_bytes,
                max_session_bytes,
                min_free_bytes: market.min_free_disk_bytes,
            });
            let stop = shutdown_signal(market.parent_pid)?;
            capture(&market.options(output_dir, mode), &mut output, stop)?
        }
        Command::Replay {
            input,
            allow_incomplete,
        } => replay(&input, allow_incomplete, |quote| {
            serde_json::to_writer(&mut output, quote)?;
            output.write_all(b"\n")?;
            Ok(())
        })?,
        Command::Supervise {
            market,
            output_dir,
            run_duration_secs,
            max_restarts,
            max_segment_bytes,
            max_run_bytes,
            max_total_recording_bytes,
            sample_interval_secs,
            shutdown_grace_secs,
        } => {
            let stop = shutdown_signal(market.parent_pid)?;
            let feed_policy = market.feed_policy();
            let report = supervise(
                SupervisorOptions {
                    output_dir: output_dir.clone(),
                    coin: market.coin,
                    network: market.network,
                    duration: Duration::from_secs(market.duration_secs),
                    run_duration: Duration::from_secs(run_duration_secs),
                    max_restarts,
                    max_reconnects: market.max_reconnects,
                    stale_after_secs: market.stale_after_secs,
                    max_segment_bytes,
                    max_run_bytes,
                    max_total_recording_bytes,
                    min_free_bytes: market.min_free_disk_bytes,
                    sample_interval: Duration::from_secs(sample_interval_secs),
                    shutdown_grace: Duration::from_secs(shutdown_grace_secs),
                    feed_policy,
                },
                &stop,
            )?;
            serde_json::to_writer(&mut output, &report)?;
            output.write_all(b"\n")?;
            output.flush()?;
            anyhow::ensure!(
                report.successful(),
                "supervision failed; see {}/summary.json",
                output_dir.display()
            );
            return Ok(());
        }
        Command::Inspect {
            input,
            allow_incomplete,
        } => {
            let inspection = inspect(&input, allow_incomplete)?;
            serde_json::to_writer(&mut output, &inspection)?;
            output.write_all(b"\n")?;
            output.flush()?;
            return Ok(());
        }
        Command::PaperExecutionReplay {
            input,
            scenario,
            output_dir,
            origin,
            feed,
        } => {
            serde_json::to_writer(
                &mut output,
                &export_execution_scenario(&input, &scenario, &output_dir, origin, feed)?,
            )?;
            output.write_all(b"\n")?;
            output.flush()?;
            return Ok(());
        }
        Command::PaperMarketReplay {
            input,
            output_dir,
            origin,
            feed,
        } => {
            let report = export_recorded_market(&input, &output_dir, origin, feed)?;
            serde_json::to_writer(&mut output, &report)?;
            output.write_all(b"\n")?;
            output.flush()?;
            return Ok(());
        }
        Command::PaperReplay {
            input,
            allow_incomplete,
        } => {
            let report = replay_paper(&input, allow_incomplete, |update| {
                serde_json::to_writer(&mut output, update)?;
                output.write_all(b"\n")?;
                Ok(())
            })?;
            output.flush()?;
            eprintln!("{}", serde_json::to_string(&report)?);
            return Ok(());
        }
        Command::AuditSupervision { input } => {
            serde_json::to_writer(&mut output, &audit_supervision(&input)?)?;
            output.write_all(b"\n")?;
            output.flush()?;
            return Ok(());
        }
    };
    output.flush()?;
    eprintln!("{}", serde_json::to_string(&report)?);
    Ok(())
}

fn shutdown_signal(parent_pid: Option<u32>) -> Result<Arc<AtomicBool>> {
    let stop = Arc::new(AtomicBool::new(false));
    let signal = stop.clone();
    ctrlc::set_handler(move || signal.store(true, Ordering::Relaxed))?;
    if let Some(parent_pid) = parent_pid {
        #[cfg(unix)]
        {
            let expected: i32 = parent_pid.try_into()?;
            anyhow::ensure!(
                nix::unistd::getppid().as_raw() == expected,
                "supervised collector's parent already exited"
            );
            let orphan_stop = stop.clone();
            std::thread::spawn(move || {
                loop {
                    if nix::unistd::getppid().as_raw() != expected {
                        orphan_stop.store(true, Ordering::Relaxed);
                        // Normal code can finalize first. If blocked in handshake or
                        // I/O, bound the orphan's lifetime without unsafe pre_exec.
                        std::thread::sleep(Duration::from_secs(2));
                        std::process::exit(13);
                    }
                    std::thread::sleep(Duration::from_millis(100));
                }
            });
        }
        #[cfg(not(unix))]
        anyhow::bail!("supervised parent monitoring requires Unix");
    }
    Ok(stop)
}

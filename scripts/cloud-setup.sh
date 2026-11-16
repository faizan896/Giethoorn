#!/usr/bin/env bash
# Repeatable managed-cloud setup. No repository or lockfile rewrites.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export RUSTUP_HOME=/workspace/.toolchains/rustup
export CARGO_HOME=/workspace/.toolchains/cargo
export PATH="$CARGO_HOME/bin:$PATH"
mkdir -p /workspace/.toolchains

if [[ ! -x "$CARGO_HOME/bin/rustup" ]]; then
  case "$(uname -m)" in
    x86_64) rustup_target=x86_64-unknown-linux-gnu ;;
    aarch64) rustup_target=aarch64-unknown-linux-gnu ;;
    *) echo "Unsupported cloud architecture" >&2; exit 1 ;;
  esac
  rustup_temp=$(mktemp -d)
  trap 'rm -rf "$rustup_temp"' EXIT
  curl --proto '=https' --tlsv1.2 -fsSL --retry 3 \
    "https://static.rust-lang.org/rustup/dist/$rustup_target/rustup-init" -o "$rustup_temp/rustup-init"
  curl --proto '=https' --tlsv1.2 -fsSL --retry 3 \
    "https://static.rust-lang.org/rustup/dist/$rustup_target/rustup-init.sha256" -o "$rustup_temp/rustup-init.sha256"
  (cd "$rustup_temp" && sha256sum --check rustup-init.sha256)
  chmod +x "$rustup_temp/rustup-init"
  "$rustup_temp/rustup-init" -y --no-modify-path --profile minimal --default-toolchain none
fi

rustup toolchain install 1.91.1 --profile minimal --component rustfmt --component clippy
cargo fetch --locked
cargo build --locked --all-targets

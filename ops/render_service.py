#!/usr/bin/env python3
"""Render a reviewable unit file. Never install, start, or enable a service."""
import argparse
import os
from pathlib import Path
import re


def quote(value: str) -> str:
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("control characters are not permitted in unit paths")
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'


def render(binary: Path, runner: Path, state: Path, user: str) -> str:
    if not re.fullmatch(r"[a-z_][a-z0-9_-]*", user):
        raise ValueError("use a plain service account name")
    if not all(p.is_absolute() for p in (binary, runner, state)):
        raise ValueError("all service paths must be absolute")
    # ExecStart expands environment variables even inside quoted arguments.
    # Reject ambiguous paths instead of letting the unit select a different file.
    if any('$' in str(p) for p in (binary, runner, state)):
        raise ValueError("dollar signs are not supported in unit paths")
    if str(state) != str(state).strip() or '\\' in str(state):
        raise ValueError("state path cannot have edge whitespace or backslashes")
    if not binary.is_file() or not runner.is_file():
        raise ValueError("binary and runner must already exist")
    if not os.access(binary, os.X_OK) or not os.access(runner, os.X_OK):
        raise ValueError("binary and runner must be executable")
    template = (Path(__file__).parent / "giethoorn.service.in").read_text()
    replacements = {
        "@BINARY@": quote(str(binary)), "@RUNNER@": quote(str(runner)),
        "@STATE@": quote(str(state)), "@USER@": user,
        # WorkingDirectory is a scalar path, not an ExecStart/list word. Literal
        # quotes become part of its path; only specifiers need escaping here.
        "@WORKING_STATE@": str(state).replace('%', '%%'),
        "@STATE_SETUP@": "StateDirectory=giethoorn\nStateDirectoryMode=0700" if state == Path('/var/lib/giethoorn') else '# Custom state directory must be provisioned by the operator.',
    }
    # Substitute only template tokens, not tokens occurring inside user paths.
    return re.sub(r'@[A-Z_]+@', lambda match: replacements[match.group(0)], template)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--runner', type=Path, default=Path(__file__).resolve().parent / 'run-collector-service')
    parser.add_argument('--state-dir', type=Path, default=Path('/var/lib/giethoorn'))
    parser.add_argument('--user', default='giethoorn')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = render(args.binary, args.runner, args.state_dir, args.user)
    except ValueError as error:
        parser.error(str(error))
    with args.output.open('x') as output:
        output.write(result)
    print(args.output)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Export a source-only Mac setup ZIP, with optional bounded public-data views."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import stat
import zipfile

PROJECT = Path(__file__).resolve().parent.parent
ROOT = 'Giethoorn-Mac/'
SINGLES = ('README.md', 'AGENTS.md', 'Cargo.toml', 'Cargo.lock', 'rust-toolchain.toml', '.gitignore', '.dockerignore')
DIRECTORIES = ('src', 'tests', 'fixtures', 'ops', 'scripts', 'web', 'docs', '.github')
MIB = 1024*1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def bounded(path, limit):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= limit, 'invalid export input: '+path.name)
    with path.open('rb') as source:
        raw = source.read(limit+1)
    require(len(raw) <= limit, 'input grew during export')
    return raw


def package(output, paper_view=None, batch_view=None):
    entries = {}
    paths = [PROJECT/name for name in SINGLES]
    for directory in DIRECTORIES:
        root = PROJECT/directory
        require(not root.is_symlink(), 'source directory symlink is not exportable')
        paths.extend(path for path in root.rglob('*') if path.is_file() or path.is_symlink())
    for path in sorted(paths):
        relative = path.relative_to(PROJECT)
        if any(part in ('__pycache__', '.git', '.ssh', '.aws', '.codex', 'target', 'data') or part.startswith('.env')
               for part in relative.parts) or path.suffix in ('.pyc', '.log', '.pem', '.key', '.p12', '.pfx', '.zip', '.tgz'):
            continue
        require(not path.is_symlink(), 'source symlinks are not exportable')
        entries[relative.as_posix()] = (bounded(path, 8*MIB), 0o755 if path.stat().st_mode & 0o111 else 0o644)
    entries['START-HERE.md'] = (bounded(PROJECT/'docs/local-mac.md', MIB), 0o644)
    for name, source in [('paper-lab.html', paper_view), ('batch-lab.html', batch_view)]:
        if source:
            raw = bounded(source, 16*MIB)
            require(b'<html' in raw.lower() and b'__PAPER_BOOT__' not in raw and b'__BATCH_BOOT__' not in raw,
                    'preview must be a rendered portable HTML view')
            entries['preview/'+name] = (raw, 0o644)
    require(len(entries) <= 2000 and sum(len(raw) for raw, _ in entries.values()) <= 64*MIB, 'export exceeds bounds')
    manifest = dict(bundle_version=1, created_at_utc=datetime.now(timezone.utc).isoformat(),
        purpose='Intel Mac local research and collection setup',
        source_only=True, recording_archive_included=False, credentials_included=False,
        files=[dict(file=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), mode=oct(mode))
               for name, (raw, mode) in sorted(entries.items())])
    entries['TRANSFER-MANIFEST.json'] = (json.dumps(manifest, indent=2).encode()+b'\n', 0o644)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as destination:
        with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, (raw, mode) in sorted(entries.items()):
                entry = zipfile.ZipInfo(ROOT+name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = (stat.S_IFREG | mode) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, raw)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--paper-view', type=Path)
    parser.add_argument('--batch-view', type=Path)
    args = parser.parse_args()
    print(package(args.output, args.paper_view, args.batch_view))

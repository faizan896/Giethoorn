#!/usr/bin/env python3
"""Export a source-traceable offline market-mark replay into Paper Lab."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

PROJECT = Path(__file__).resolve().parent.parent
MAX_FILE = 32 * 1024 * 1024
MAX_HTML = 16 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_FILE,
            'invalid or oversized replay artifact')
    return path.read_bytes()


def generate(binary, recording, output, origin, feed='bbo'):
    binary, recording, output = binary.resolve(), recording.resolve(), output.resolve()
    require(origin in ('captured_public_data', 'synthetic_fixture') and feed in ('bbo', 'depth'),
            'explicit supported origin and feed are required')
    require(binary.is_file() and os.access(binary, os.X_OK), 'existing replay executable required')
    binary_sha256 = hashlib.sha256(binary.read_bytes()).hexdigest()
    require(recording.is_dir(), 'a finalized segmented recording is required')
    require(not output.is_relative_to(recording), 'output must be outside the original recording')
    os.umask(0o077)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    command = [str(binary), 'paper-market-replay', '--input', str(recording),
               '--output-dir', str(output/'replay'), '--origin', origin.replace('_', '-'), '--feed', feed]
    with (output/'command.stdout').open('xb') as stdout, (output/'command.stderr').open('xb') as stderr:
        result = subprocess.run(command, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL, check=False)
    require(result.returncode == 0, 'market replay failed; diagnostic output retained')
    replay = output/'replay'
    market = json.loads(read(replay/'market-replay.json'))
    manifest = json.loads(read(replay/'source-manifest.json'))
    report = json.loads(read(replay/'paper-report.json'))
    frames = [json.loads(line) for line in read(replay/'paper-updates.jsonl').splitlines()]
    links = [json.loads(line) for line in read(replay/'market-links.jsonl').splitlines()]
    require(market['adapter_version'] == 1 and market['mode'] == 'offline_market_marks_only'
            and market['paper'] == report and market['source'] == manifest
            and market['strategy_enabled'] is False and market['full_window_verified'] is False,
            'unsupported or inconsistent market replay envelope')
    require(market['source_report']['complete'] and market['source_storage']['finalized'],
            'market source is not finalized')
    source = report['config']['source']
    require(manifest['manifest_version'] == 1 and source['kind'] == 'recorded_market' and source['origin'] == origin
            and manifest['origin'] == origin and source['feed'] == feed,
            'declared origin/feed disagrees with replay provenance')
    files = manifest['files']
    require(files and [f['file'] for f in files] == sorted({f['file'] for f in files}),
            'source manifest is not sorted or unique')
    for entry in files:
        require(re.fullmatch(r'index\.jsonl|segment-[0-9]{8}\.jsonl', entry['file']) is not None,
                'noncanonical source filename')
        raw = read(replay/'source'/entry['file'])
        require(len(raw) == entry['bytes'] and hashlib.sha256(raw).hexdigest() == entry['sha256'],
                'source copy differs from its manifest')
    canonical = json.dumps(files, separators=(',', ':'), ensure_ascii=False).encode()
    digest = hashlib.sha256(b'giethoorn-recorded-market-v1\0'+canonical).hexdigest()
    require(digest == source['recording_sha256'] == manifest['recording_sha256'],
            'source manifest digest disagrees with paper provenance')
    require(report['paper_model_version'] == 2 and report['fill_model'] == 'disabled_market_marks_only' and report['complete']
            and frames and frames[-1]['complete'] and all(not frame['complete'] for frame in frames[:-1])
            and report['records'] == len(frames) == len(links) and 1 < len(frames) <= 10000,
            'unsupported or incomplete paper frames')
    require([f['sequence'] for f in frames] == list(range(1, len(frames)+1)),
            'paper frames are not contiguous')
    require([link['paper_sequence'] for link in links] == list(range(1, len(links)+1))
            and [link['market_sequence'] for link in links] == list(range(1, len(links)))+[len(links)-1]
            and all(not link['generated_end'] for link in links[:-1]) and links[-1]['generated_end']
            and market['source_report']['records'] == len(links)-1,
            'source-to-paper links are inconsistent')
    require(frames[-1]['account'] == report['account'] and frames[-1]['risk'] == report['risk'],
            'final frame and paper report disagree')
    require(not report['orders'] and report['assumed_fills'] == 0,
            'mark-only replay cannot contain orders or fills')
    for frame in frames:
        require(frame['paper_model_version'] == 2 and frame['mode'] == 'paper' and frame['source'] == source
                and frame['order'] is None and frame['assumed_fill'] is None
                and frame['account']['position_quantity'] == '0' and frame['account']['fees'] == '0',
                'paper frames violate mark-only provenance')
    # Independently replay the persisted paper inputs; do not trust derived caches.
    check_command = [str(binary), 'paper-replay', '--input', str(replay/'paper-input.jsonl')]
    with (output/'replayed-updates.jsonl').open('xb') as stdout, (output/'replayed-report.json').open('xb') as stderr:
        checked = subprocess.run(check_command, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL, check=False)
    require(checked.returncode == 0 and read(output/'replayed-updates.jsonl') == read(replay/'paper-updates.jsonl')
            and json.loads(read(output/'replayed-report.json')) == report,
            'independent paper replay differs from derived frames')
    require(hashlib.sha256(binary.read_bytes()).hexdigest() == binary_sha256,
            'replay executable changed during export')
    evidence = dict(schema_version=1, command=command, replay_check_command=check_command,
                    binary_sha256=binary_sha256,
                    origin=origin, recording_sha256=digest, paper_model_version=2,
                    strategy_enabled=False, full_window_verified=False)
    (output/'run.json').write_text(json.dumps(evidence, indent=2)+'\n')
    boot = json.dumps(dict(report=report, frames=frames, market=dict(links=links, replay=market)),
                      separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    template = (PROJECT/'web/paper.html').read_text()
    require(template.count('__PAPER_BOOT__') == template.count('__GIETHOORN_THEME__') == 1,
            'invalid Paper Lab template')
    html = template.replace('__GIETHOORN_THEME__', (PROJECT/'web/theme.css').read_text()).replace('__PAPER_BOOT__', boot)
    require(len(html.encode()) <= MAX_HTML, 'portable market view exceeds the 16 MiB limit')
    with (output/'paper-lab.html').open('x') as destination:
        destination.write(html)
    return output/'paper-lab.html'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--origin', choices=('captured-public-data', 'synthetic-fixture'), required=True)
    parser.add_argument('--feed', choices=('bbo', 'depth'), default='bbo')
    args = parser.parse_args()
    print(generate(args.binary, args.input, args.output_dir, args.origin.replace('-', '_'), args.feed))

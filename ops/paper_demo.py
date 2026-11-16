#!/usr/bin/env python3
"""Generate a portable Paper Lab from the real offline Rust replay engine."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

PROJECT = Path(__file__).resolve().parent.parent


def generate(binary, scenario, output):
    binary, scenario, output = binary.resolve(), scenario.resolve(), output.resolve()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError('an existing executable replay binary is required')
    raw = scenario.read_bytes()
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError('scenario exceeds the demo input limit')
    if not raw.strip():
        raise ValueError('empty paper scenario')
    first = json.loads(raw.splitlines()[0])
    if first.get('event', {}).get('config', {}).get('source', {}).get('kind') != 'synthetic':
        raise ValueError('this demo exporter accepts explicitly synthetic scenarios only')
    os.umask(0o077)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    command = [str(binary), 'paper-replay', '--input', str(scenario)]
    with (output/'paper-updates.jsonl').open('xb') as stdout, (output/'paper-report.json').open('xb') as stderr:
        result = subprocess.run(command, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL, check=False)
    if result.returncode:
        raise RuntimeError('paper replay failed; retained diagnostic output')
    frames = [json.loads(line) for line in (output/'paper-updates.jsonl').read_bytes().splitlines()]
    report = json.loads((output/'paper-report.json').read_bytes())
    if not frames or report.get('mode') != 'paper' or not report.get('complete'):
        raise ValueError('scenario did not produce a complete paper report')
    if report.get('paper_model_version') != 1 or report.get('records') != len(frames) or not frames[-1].get('complete'):
        raise ValueError('unsupported or inconsistent paper model output')
    if [frame['sequence'] for frame in frames] != list(range(1, len(frames)+1)):
        raise ValueError('noncontiguous derived paper output')
    if frames[-1]['account'] != report['account'] or frames[-1]['risk'] != report['risk']:
        raise ValueError('derived frames disagree with final report')
    if any(frame['mode'] != 'paper' or frame['source']['kind'] != 'synthetic' for frame in frames):
        raise ValueError('paper source labels disagree')
    evidence = dict(schema_version=1, command=command, binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                    input_sha256=hashlib.sha256(raw).hexdigest(), model_version=report['paper_model_version'],
                    mode='paper', source_kind='synthetic')
    (output/'scenario.jsonl').write_bytes(raw)
    (output/'run.json').write_text(json.dumps(evidence,indent=2)+'\n')
    boot = json.dumps(dict(report=report,frames=frames),separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    template = (PROJECT/'web/paper.html').read_text()
    if template.count('__PAPER_BOOT__') != 1 or template.count('__GIETHOORN_THEME__') != 1:
        raise ValueError('invalid Paper Lab template')
    with (output/'paper-lab.html').open('x') as destination:
        destination.write(template.replace('__GIETHOORN_THEME__',(PROJECT/'web/theme.css').read_text()).replace('__PAPER_BOOT__',boot))
    return output/'paper-lab.html'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--input',type=Path,default=PROJECT/'fixtures/paper-synthetic-v1.jsonl')
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    print(generate(args.binary,args.input,args.output_dir))

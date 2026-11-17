#!/usr/bin/env python3
"""Run one fixed prediction study on one frozen retrospective partition."""
import argparse
from datetime import datetime, timezone
import fcntl
from pathlib import Path

if __package__:
    from . import quality_local as QUALITY, review_local as REVIEW, study_core as CORE
else:
    import quality_local as QUALITY
    import review_local as REVIEW
    import study_core as CORE

MIB = 1024*1024
PARTITIONS = ('development', 'validation', 'retrospective_test')
INPUTS = ('dataset-manifest.json', 'quality-report.json', 'source-before.json', 'source-after.json',
          'quality-policy.json', 'research-protocol.md', 'fast-spans.jsonl', 'audit/audit.stdout.json')
require = REVIEW.require


class Writer:
    def __init__(self, stream):
        self.stream, self.bytes = stream, 0

    def write(self, value, flush=False):
        raw = QUALITY.encoded(value)+b'\n'
        self.bytes += len(raw)
        require(self.bytes <= 64*MIB, 'study output budget exceeded')
        self.stream.write(raw)
        if flush:
            self.stream.flush()


def quality_inputs(directory):
    require(directory.is_dir() and not directory.is_symlink(), 'frozen quality directory required')
    require((directory/'audit').is_dir() and not (directory/'audit').is_symlink(), 'regular quality audit directory required')
    hashes, size = {}, 0
    for name in INPUTS:
        path = directory/name
        REVIEW.plain(path)
        size += path.stat().st_size
        require(path.stat().st_size <= 64*MIB and size <= 128*MIB, 'quality evidence exceeds bounds')
        hashes[name] = REVIEW.digest(path)
    return hashes


def frozen(directory, binary, origin, quality_template, theme):
    hashes = quality_inputs(directory)
    manifest = REVIEW.read_json(directory/'dataset-manifest.json')
    report = REVIEW.read_json(directory/'quality-report.json')
    before = REVIEW.read_json(directory/'source-before.json')
    require(manifest.get('quality_manifest_version') == 1 and manifest.get('admitted') is True
            and report.get('quality_report_version') == 1 and report.get('status') == 'completed'
            and report.get('source_unchanged') is True and report.get('origin') == origin
            and manifest.get('origin') == origin and report.get('manifest') == manifest,
            'quality report is not an admitted frozen dataset')
    require(REVIEW.read_json(directory/'source-after.json') == before, 'quality source inventories differ')
    require(REVIEW.read_json(directory/'quality-policy.json') == QUALITY.POLICY == report['policy'],
            'unsupported quality policy')
    for field, name in [('source_inventory_sha256', 'source-before.json'),
                        ('audit_output_sha256', 'audit/audit.stdout.json'),
                        ('policy_sha256', 'quality-policy.json'), ('fast_spans_sha256', 'fast-spans.jsonl')]:
        require(manifest[field] == hashes[name], 'frozen quality artifact fingerprint differs: '+name)
    require(manifest['assets']['protocol'] == hashes['research-protocol.md']
            and manifest['assets']['template'] == REVIEW.digest(quality_template)
            and manifest['assets']['theme'] == REVIEW.digest(theme), 'frozen quality assets differ')
    require(manifest['quality_helper_sha256'] == REVIEW.digest(Path(QUALITY.__file__))
            and manifest['review_helper_sha256'] == REVIEW.digest(Path(REVIEW.__file__))
            and manifest['audit_binary_sha256'] == REVIEW.digest(binary.resolve()),
            'frozen quality verifier version differs')
    parts = manifest['candidate_partitions']
    require(parts == report['partitions'] == QUALITY.partitions(report['runs'])
            and parts['status'] == 'frozen_retrospective', 'frozen partition membership differs')
    require(report['totals'] == QUALITY.summarize(report['runs']), 'quality summary differs from its inventory')
    check_domain(report)
    return hashes, manifest, report, before


def check_domain(report):
    domain = report['audit']['audit']
    require(domain['coin'] == CORE.POLICY['coin'] and domain['network'] == CORE.POLICY['network'],
            'study requires the declared BTC mainnet dataset')


def analyze(child, directory, expected_records, features, samples):
    analyzer = CORE.Analyzer(child)
    normalized = iter(QUALITY.objects(directory/'live-quotes.jsonl'))
    observation = next(normalized, None)
    count = 0
    for record in QUALITY.source_records(directory/'session'):
        count += 1
        require(count <= QUALITY.MAX_RECORDS and record['schema_version'] == 2 and record['sequence'] == count,
                'study source ordering differs from verified records')
        current = None
        if observation is not None:
            require(observation['sequence'] >= count, 'study observation order differs')
            if observation['sequence'] == count:
                require(observation['normalization_version'] == 2
                        and all(record[key] == observation[key] for key in ('monotonic_ns', 'local_time_ns', 'connection_id')),
                        'study observation does not match original event')
                current = observation
                observation = next(normalized, None)
        for kind, value in analyzer.step(record, current):
            (features if kind == 'feature' else samples).write(value, flush=kind == 'feature')
    for kind, value in analyzer.finish():
        samples.write(value)
    require(observation is None and count == expected_records, 'study source count or observation tail differs')
    return analyzer.stats


def generate(binary, experiment, quality, output, partition, origin, quality_template, study_template, theme):
    require(partition in PARTITIONS and origin in ('captured_public_data', 'synthetic_fixture'),
            'explicit supported partition and origin required')
    experiment, quality, output = experiment.absolute(), quality.absolute(), output.resolve()
    require(experiment.is_dir() and not experiment.is_symlink(), 'source experiment directory required')
    require(not output.is_relative_to(experiment.resolve()) and not output.is_relative_to(quality.resolve()),
            'study output must be outside original evidence')
    assets = {name: QUALITY.read_asset(path) for name, path in [('quality_template', quality_template),
              ('study_template', study_template), ('theme', theme)]}
    root = experiment/'supervision'
    require(root.is_dir() and not root.is_symlink(), 'source supervision directory required')
    REVIEW.plain(root/'supervisor.lock')
    with (root/'supervisor.lock').open('rb') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('supervisor is active; study requires stopped evidence') from None
        try:
            hashes, manifest, quality_report, expected_source = frozen(quality, binary, origin, quality_template, theme)
        except (KeyError, TypeError):
            raise ValueError('incomplete or unsupported frozen quality evidence') from None
        require(REVIEW.inventory(experiment) == expected_source, 'original source differs from frozen quality dataset')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.mkdir(mode=0o700)
        backup = output/'input-quality'
        backup.mkdir(mode=0o700)
        for name in INPUTS:
            destination = backup/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with (quality/name).open('rb') as source, destination.open('xb') as target:
                for block in iter(lambda: source.read(MIB), b''):
                    target.write(block)
            require(REVIEW.digest(destination) == hashes[name], 'quality evidence changed during snapshot')
        REVIEW.save(output/'study-policy.json', CORE.POLICY)
        members = manifest['candidate_partitions']
        selected = set(members[partition])
        rows = [dict(child=row['run'], partition=next((name for name in PARTITIONS if row['run'] in members[name]), None),
                     status='not_run' if row['candidate'] else 'excluded', metrics=None,
                     previously_inspected=row['previously_inspected'], reason=None if row['candidate'] else row['reason'])
                for row in quality_report['runs']]
        report = dict(study_report_version=1, study_id=CORE.POLICY['study_id'],
            created_at_utc=datetime.now(timezone.utc).isoformat(), origin=origin,
            status='analysis_failed', selected_partition=partition, policy=CORE.POLICY,
            metrics=None, rows=rows, source_unchanged=False, quality_unchanged=False,
            orders_enabled=False, profit_evaluated=False, full_window_verified=False,
            error=None, partitions={name: dict(status='not_run', children=members[name], metrics=None) for name in PARTITIONS})
        fresh = None
        try:
            fresh = QUALITY.generate(binary, experiment, output/'quality-check', origin,
                                      quality_template, theme, backup/'research-protocol.md', manifest['inspected_children'])
            require(fresh['status'] == 'completed' and fresh['manifest']['admitted'], 'fresh quality verification failed')
            check_domain(fresh)
            require(fresh['partitions'] == members
                    and fresh['manifest']['source_inventory_sha256'] == manifest['source_inventory_sha256']
                    and fresh['manifest']['audit_output_sha256'] == manifest['audit_output_sha256'],
                    'fresh evidence differs from frozen dataset or partitions')
            by_child = {row['run']: row for row in fresh['runs']}
            aggregate = CORE.Stats()
            with (output/'features.jsonl').open('xb') as feature_stream, (output/'samples.jsonl').open('xb') as sample_stream:
                features, samples = Writer(feature_stream), Writer(sample_stream)
                for row in rows:
                    if row['child'] not in selected:
                        continue
                    checked = by_child[row['child']]
                    stats = analyze(row['child'], root/checked['directory'], checked['measurements']['source_records'], features, samples)
                    row.update(status='completed', metrics=stats.report())
                    aggregate.merge(stats)
            report.update(status='completed', metrics=aggregate.report())
            report['partitions'][partition].update(status='completed', metrics=aggregate.report())
        except (ValueError, OSError, KeyError, TypeError) as error:
            report['error'] = str(error)
        after = REVIEW.inventory(experiment)
        REVIEW.save(output/'source-after.json', after)
        same_source = after == expected_source and REVIEW.digest(binary.resolve()) == manifest['audit_binary_sha256']
        try:
            same_quality = quality_inputs(quality) == hashes
        except (ValueError, OSError):
            same_quality = False
        report.update(source_unchanged=same_source, quality_unchanged=same_quality)
        if not same_source or not same_quality:
            report.update(status='source_changed', error='source, quality evidence or auditor changed')
        if report['status'] != 'completed':
            report['metrics'] = None
            for row in rows:
                if row['status'] == 'completed':
                    row.update(status='not_run', metrics=None, reason='study_not_verified')
            for part in report['partitions'].values():
                part.update(status='not_run', metrics=None)
        report['audit'] = None if fresh is None else fresh['audit']
        report['provenance'] = dict(input_quality_hashes=hashes, study_policy_sha256=REVIEW.digest(output/'study-policy.json'),
            study_core_sha256=REVIEW.digest(Path(CORE.__file__)), study_runner_sha256=REVIEW.digest(Path(__file__)),
            auditor_sha256=manifest['audit_binary_sha256'],
            features_sha256=REVIEW.digest(output/'features.jsonl') if (output/'features.jsonl').exists() else None,
            samples_sha256=REVIEW.digest(output/'samples.jsonl') if (output/'samples.jsonl').exists() else None,
            quality_template_sha256=REVIEW.digest(quality_template), study_template_sha256=REVIEW.digest(study_template),
            theme_sha256=REVIEW.digest(theme))
        raw = QUALITY.encoded(report)+b'\n'
        require(len(raw) <= 6*MIB, 'study report exceeds limit')
        with (output/'study-report.json').open('xb') as stream:
            stream.write(raw)
        (output/'study.html').write_text(QUALITY.render(report, assets['study_template'].decode(), assets['theme'].decode()))
        return report


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('binary', 'experiment', 'quality', 'output-dir', 'quality-template', 'study-template', 'theme'):
        parser.add_argument('--'+option, type=Path, required=True)
    parser.add_argument('--origin', choices=('captured-public-data', 'synthetic-fixture'), required=True)
    parser.add_argument('--partition', choices=PARTITIONS, default='development')
    args = parser.parse_args()
    try:
        report = generate(args.binary, args.experiment, args.quality, args.output_dir, args.partition,
                          args.origin.replace('-', '_'), args.quality_template, args.study_template, args.theme)
    except (ValueError, OSError) as error:
        parser.exit(2, 'Study preflight failed: '+str(error)+'\n')
    print(json.dumps({key: report[key] for key in ('status', 'selected_partition', 'source_unchanged',
        'quality_unchanged', 'metrics', 'error')}, indent=2))
    print('Study view: '+str(args.output_dir/'study.html'))
    return 0 if report['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())

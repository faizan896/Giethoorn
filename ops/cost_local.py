#!/usr/bin/env python3
"""Bounded exploratory R001 execution probes on a frozen, stopped archive."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import time

if __package__:
    from . import cost_core as CORE, paper_execution as EXECUTION, study_local as STUDY
else:
    import cost_core as CORE
    import paper_execution as EXECUTION
    import study_local as STUDY

QUALITY, REVIEW = STUDY.QUALITY, STUDY.REVIEW
require = REVIEW.require
MIB = 1024*1024
LIMITS = dict(max_output_bytes=2048*MIB, min_free_bytes=1024*MIB, suite_timeout_seconds=900,
              native_timeout_seconds=30, case_allowance_bytes=256*MIB, report_reserve_bytes=8*MIB)


def used_bytes(root):
    total = 0
    for path in root.rglob('*'):
        require(not path.is_symlink(), 'output symlink refused')
        if path.is_file():
            total += path.stat().st_size
    return total


def admit(root, deadline, allowance):
    require(time.monotonic() < deadline, 'suite time budget exhausted')
    reserve = allowance+LIMITS['report_reserve_bytes']
    require(used_bytes(root)+reserve <= LIMITS['max_output_bytes'], 'output budget cannot admit next operation')
    require(shutil.disk_usage(root).free >= LIMITS['min_free_bytes']+reserve, 'free-space reserve cannot admit next operation')


def feature(child, directory):
    analyzer = CORE.SIGNAL.Analyzer(child)
    observations = iter(QUALITY.objects(directory/'live-quotes.jsonl'))
    observation = next(observations, None)
    for record in QUALITY.source_records(directory/'session'):
        current = None
        if observation is not None and observation['sequence'] == record['sequence']:
            current, observation = observation, next(observations, None)
        for kind, value in analyzer.step(record, current):
            if (kind == 'feature' and value['monotonic_ns'] >= analyzer.first+CORE.POLICY['warmup_ns']
                    and value['prediction'] != 'abstain'):
                return value
    return None


def read_execution(root):
    execution = REVIEW.read_json(root/'replay/execution-replay.json')
    frames = list(QUALITY.objects(root/'replay/paper-updates.jsonl'))
    links = list(QUALITY.objects(root/'replay/market-links.jsonl'))
    trace = list(QUALITY.objects(root/'replay/execution-trace.jsonl'))
    require(len(frames) == len(links) == len(trace) == execution['paper']['records'], 'execution trace length differs')
    return execution, list(zip(frames, links, trace))


def match_source(execution, source_inventory, child):
    manifest = execution['market']['source']
    prefix = f'supervision/run-{child:06d}/session/'
    expected = {name[len(prefix):]: {key: entry[key] for key in ('bytes', 'sha256')}
                for name, entry in source_inventory.items() if name.startswith(prefix)}
    copied = {entry['file']: {key: entry[key] for key in ('bytes', 'sha256')} for entry in manifest['files']}
    require(expected and copied == expected, 'execution source differs from frozen archive')
    return manifest['recording_sha256']


def run_case(binary, source, feature_value, profile, directory, expected, deadline):
    directory.mkdir(mode=0o700)
    entry = CORE.entry_scenario(feature_value, profile['assumptions'])
    REVIEW.save(directory/'entry-scenario.json', entry)
    remaining = deadline-time.monotonic()
    require(remaining > 0, 'suite time budget exhausted')
    EXECUTION.generate(binary, source, directory/'entry-scenario.json', directory/'control', expected['origin'],
        render_view=False, timeout_secs=min(LIMITS['native_timeout_seconds'], remaining/4))
    control, control_rows = read_execution(directory/'control')
    source_sha = match_source(control, expected['inventory'], feature_value['child'])
    market = zip(QUALITY.objects(directory/'control/replay/market/paper-updates.jsonl'),
                 QUALITY.objects(directory/'control/replay/market/market-links.jsonl'))
    decision = CORE.close_decision(feature_value, market)
    compiled, receipt = CORE.compile_close(entry, decision, control_rows)
    receipt.update(control_scenario_sha256=REVIEW.digest(directory/'entry-scenario.json'),
                   control_updates_sha256=REVIEW.digest(directory/'control/replay/paper-updates.jsonl'),
                   policy_sha256=expected['policy_sha256'])
    # Persist the decision, known exposure and complete materialized intent before
    # the replay with a close can apply any derived transition.
    REVIEW.save(directory/'causal-prefix.json', receipt)
    REVIEW.save(directory/'compiled-scenario.json', compiled)
    reused = compiled == entry
    final_root, final, final_rows = directory/'control', control, control_rows
    if not reused:
        remaining = deadline-time.monotonic()
        require(remaining > 0, 'suite time budget exhausted')
        final_root = directory/'compiled'
        EXECUTION.generate(binary, source, directory/'compiled-scenario.json', final_root, expected['origin'],
            render_view=False, timeout_secs=min(LIMITS['native_timeout_seconds'], remaining/2))
        final, final_rows = read_execution(final_root)
        require(match_source(final, expected['inventory'], feature_value['child']) == source_sha,
                'control and compiled recording differ')
    prefix_sha = CORE.verify_prefix(control_rows, final_rows, decision)
    require(prefix_sha == receipt['prefix_sha256'], 'prefix certificate differs')
    result = dict(status='verified', recording_sha256=source_sha,
        policy_sha256=expected['policy_sha256'], compiled_scenario_sha256=REVIEW.digest(directory/'compiled-scenario.json'),
        prefix_verified=True, control_reused=reused, final_replay=str(final_root.relative_to(directory)),
        metrics=CORE.metrics(final, final_rows, receipt), causal_prefix=receipt,
        cost_audit=REVIEW.read_json(final_root/'cost-audit.json'))
    REVIEW.save(directory/'case-result.json', result)
    return result


def comparisons(cases):
    result = []
    for case in cases:
        base = next(row for row in cases if row['child'] == case['child'] and row['profile'] == 'baseline')
        pair = dict(child=case['child'], profile=case['profile'], closed_case_net_pnl_delta=None,
                    entry_quantity_changed=None, close_quantity_changed=None, outcome_changed=None,
                    execution_path_changed=None, unavailable_reason=None)
        if base['status'] != 'verified' or case['status'] != 'verified':
            pair['unavailable_reason'] = 'Both cases must verify.'
        else:
            a, b = base['metrics'], case['metrics']
            pair.update(entry_quantity_changed=a['entry_quantity'] != b['entry_quantity'],
                close_quantity_changed=a['close_requested_quantity'] != b['close_requested_quantity'],
                outcome_changed=a['outcome'] != b['outcome'],
                execution_path_changed=a['execution_path_sha256'] != b['execution_path_sha256'])
            if a['closed_case_net_pnl'] is not None and b['closed_case_net_pnl'] is not None:
                with localcontext() as context:
                    context.prec = 100
                    pair['closed_case_net_pnl_delta'] = CORE.text(Decimal(b['closed_case_net_pnl'])-Decimal(a['closed_case_net_pnl']))
            else:
                pair['unavailable_reason'] = 'Closed-case P&L requires both independent probes to finish closed.'
        result.append(pair)
    return result


def summarize(cases):
    result = dict(cases=len(cases), verified=0, failed=0, not_run=0, no_signal=0,
                  closed=0, unresolved=0, no_entry_fill=0, entry_rejected=0)
    for row in cases:
        result[row['status']] += 1
        if row['status'] == 'verified':
            result[row['metrics']['outcome']] += 1
    return result


def generate(binary, experiment, quality, output, origin, quality_template, cost_template, theme):
    binary, experiment, quality, output = binary.resolve(), experiment.absolute(), quality.absolute(), output.resolve()
    require(binary.is_file() and os.access(binary, os.X_OK) and binary.stat().st_size <= 128*MIB, 'bounded executable required')
    require(origin in ('captured_public_data', 'synthetic_fixture'), 'explicit source origin required')
    require(experiment.is_dir() and not experiment.is_symlink(), 'stopped source experiment required')
    require(not output.is_relative_to(experiment.resolve()) and not output.is_relative_to(quality.resolve()),
            'cost output must be outside original evidence')
    assets = {key: QUALITY.read_asset(path) for key, path in [('template', cost_template), ('theme', theme)]}
    code = {name: Path(module.__file__) for name, module in [('cost_core', CORE),
        ('execution', EXECUTION), ('study', STUDY), ('signal', CORE.SIGNAL), ('quality', QUALITY), ('review', REVIEW)]}
    code.update(cost_local=Path(__file__), quality_template=quality_template, cost_template=cost_template, theme=theme)
    code_hashes = {name: REVIEW.digest(path) for name, path in code.items()}
    root = experiment/'supervision'
    REVIEW.plain(root/'supervisor.lock')
    with (root/'supervisor.lock').open('rb') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('supervisor is active; cost probes require stopped evidence') from None
        try:
            hashes, manifest, frozen_report, expected_source = STUDY.frozen(quality, binary, origin, quality_template, theme)
        except (KeyError, TypeError):
            raise ValueError('incomplete frozen quality evidence') from None
        require(REVIEW.inventory(experiment) == expected_source, 'source differs from frozen quality dataset')
        os.umask(0o077)
        output.parent.mkdir(parents=True, exist_ok=True)
        require(shutil.disk_usage(output.parent).free >= LIMITS['min_free_bytes']+384*MIB,
                'insufficient initial free-space reserve')
        output.mkdir(mode=0o700)
        deadline = time.monotonic()+LIMITS['suite_timeout_seconds']
        backup = output/'input-quality'
        backup.mkdir()
        for name in STUDY.INPUTS:
            destination = backup/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(quality/name, destination)
            require(REVIEW.digest(destination) == hashes[name], 'quality changed during snapshot')
        pinned = output/'replay.bin'
        shutil.copyfile(binary, pinned)
        pinned.chmod(0o700)
        require(REVIEW.digest(pinned) == manifest['audit_binary_sha256'], 'binary changed during pinning')
        policy = dict(policy=CORE.POLICY, profiles=CORE.PROFILES, limits=LIMITS)
        REVIEW.save(output/'cost-policy.json', policy)
        policy_sha = CORE.fingerprint(policy)
        selected = manifest['candidate_partitions']['development'][:CORE.POLICY['max_children']]
        rows = [dict(child=r['run'], partition=next((p for p in STUDY.PARTITIONS if r['run'] in manifest['candidate_partitions'][p]), None),
                     status='selected' if r['run'] in selected else 'not_run', previously_inspected=r['previously_inspected'],
                     reason=None if r['run'] in selected else 'outside bounded development suite', feature=None)
                for r in frozen_report['runs']]
        cases = [dict(id=f'run-{child:06d}--{profile["id"]}', child=child, profile=profile['id'],
                      status='not_run', reason='Not admitted.', metrics=None) for child in selected for profile in CORE.PROFILES]
        report = dict(cost_report_version=1, created_at_utc=datetime.now(timezone.utc).isoformat(),
            policy_id=CORE.POLICY['policy_id'], policy_sha256=policy_sha, policy=policy,
            origin=origin, scope='independent_flat_start_exploratory_probes', status='incomplete',
            selected_children=selected, rows=rows, cases=cases, totals=None, comparisons=[],
            source_unchanged=False, quality_unchanged=False, code_unchanged=False, audit=None,
            live_orders_enabled=False, portfolio_profit_evaluated=False, full_window_verified=False, error=None)
        try:
            admit(output, deadline, 128*MIB)
            fresh = QUALITY.generate(pinned, experiment, output/'quality-check', origin,
                                      quality_template, theme, backup/'research-protocol.md', manifest['inspected_children'])
            report['audit'] = fresh['audit']
            require(fresh['status'] == 'completed' and fresh['manifest']['admitted'], 'fresh quality verification failed')
            require(fresh['partitions'] == manifest['candidate_partitions']
                    and fresh['manifest']['source_inventory_sha256'] == manifest['source_inventory_sha256']
                    and fresh['manifest']['audit_output_sha256'] == manifest['audit_output_sha256'],
                    'fresh source evidence or membership differs')
            for row in rows:
                if row['child'] not in selected:
                    continue
                directory = root/f'run-{row["child"]:06d}'
                admit(output, deadline, MIB)
                value = feature(row['child'], directory)
                row.update(feature=value, status='selected' if value else 'no_signal')
                child_cases = [case for case in cases if case['child'] == row['child']]
                if value is None:
                    for case in child_cases:
                        case.update(status='no_signal', reason='No directional feature after the fixed warmup.')
                    continue
                # A feature is fixed before any profile is executed or outcome read.
                feature_dir = output/f'run-{row["child"]:06d}'
                feature_dir.mkdir()
                REVIEW.save(feature_dir/'feature.json', value)
                for case, profile in zip(child_cases, CORE.PROFILES):
                    try:
                        admit(output, deadline, LIMITS['case_allowance_bytes'])
                    except ValueError as error:
                        case['reason'] = str(error)
                        continue
                    try:
                        result = run_case(pinned, directory/'session', value, profile, output/case['id'],
                            dict(origin=origin, inventory=expected_source, policy_sha256=policy_sha), deadline)
                        case.update(result, reason=None)
                    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
                        case.update(status='failed', reason=str(error), metrics=None)
                row['status'] = 'completed' if all(c['status'] == 'verified' for c in child_cases) else 'incomplete'
            if all(case['status'] in ('verified', 'no_signal') for case in cases):
                report['status'] = 'completed'
        except (ValueError, OSError, KeyError, TypeError) as error:
            report['error'] = str(error)
        try:
            after = REVIEW.inventory(experiment)
            REVIEW.save(output/'source-after.json', after)
            report['source_unchanged'] = after == expected_source and REVIEW.digest(binary) == REVIEW.digest(pinned) == manifest['audit_binary_sha256']
            report['quality_unchanged'] = STUDY.quality_inputs(quality) == hashes
            report['code_unchanged'] = {name: REVIEW.digest(path) for name, path in code.items()} == code_hashes
        except (ValueError, OSError) as error:
            report['error'] = str(error)
        if not all(report[key] for key in ('source_unchanged', 'quality_unchanged', 'code_unchanged')):
            report.update(status='source_changed', error='source, frozen quality, executable or helper assets changed')
            for case in cases:
                if case['status'] == 'verified':
                    case.update(status='failed', reason='Evidence changed; metrics not admitted.', metrics=None)
        report['totals'], report['comparisons'] = summarize(cases), comparisons(cases)
        report['provenance'] = dict(input_quality_hashes=hashes, code_hashes=code_hashes,
            auditor_sha256=manifest['audit_binary_sha256'], source_inventory_sha256=manifest['source_inventory_sha256'],
            cost_policy_file_sha256=REVIEW.digest(output/'cost-policy.json'))
        bundle = {str(path.relative_to(output)): dict(bytes=path.stat().st_size, sha256=REVIEW.digest(path))
                  for path in sorted(output.rglob('*')) if path.is_file()}
        REVIEW.save(output/'bundle-inventory.json', bundle)
        report['provenance']['bundle_inventory_sha256'] = REVIEW.digest(output/'bundle-inventory.json')
        require(used_bytes(output) <= LIMITS['max_output_bytes']-LIMITS['report_reserve_bytes'], 'output exceeded report reserve')
        require(len(CORE.encoded(report)) <= 2*MIB, 'cost report exceeds bound')
        REVIEW.save(output/'cost-report.json', report)
        html = QUALITY.render(report, assets['template'].decode(), assets['theme'].decode())
        require(len(html.encode()) <= 4*MIB, 'cost view exceeds bound')
        with (output/'cost.html').open('x') as stream:
            stream.write(html)
        return report


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'experiment', 'quality', 'output-dir', 'quality-template', 'cost-template', 'theme'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--origin', choices=('captured-public-data', 'synthetic-fixture'), required=True)
    args = parser.parse_args()
    try:
        report = generate(args.binary, args.experiment, args.quality, args.output_dir, args.origin.replace('-', '_'),
                          args.quality_template, args.cost_template, args.theme)
    except (ValueError, OSError) as error:
        parser.exit(2, 'Cost probe preflight failed: '+str(error)+'\n')
    print(json.dumps({key: report[key] for key in ('status', 'source_unchanged', 'quality_unchanged', 'totals', 'error')}, indent=2))
    print('Cost view: '+str(args.output_dir/'cost.html'))
    return 0 if report['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())

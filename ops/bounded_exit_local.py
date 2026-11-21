#!/usr/bin/env python3
"""Bounded extra-close experiment on the unchanged frozen development cohort."""
import argparse
import copy
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import fcntl
import json
import os
from pathlib import Path
import shutil
import time

if __package__:
    from . import bounded_exit_core as CORE, evaluation_local as EVAL
else:
    import bounded_exit_core as CORE
    import evaluation_local as EVAL

CYCLE = EVAL.CYCLE
MODEL = CYCLE.MODEL
REVIEW, QUALITY, COST, STUDY, ORIGINAL = EVAL.REVIEW, EVAL.QUALITY, EVAL.COST, EVAL.STUDY, EVAL.ORIGINAL
require = REVIEW.require
MIB = 1024*1024
LIMITS = dict(output_bytes=16*1024*MIB, free_reserve_bytes=1024*MIB, report_reserve_bytes=32*MIB,
    source_allowance_bytes=128*MIB, case_allowance_bytes=384*MIB, extra_replay_allowance_bytes=128*MIB,
    suite_seconds=3600, native_seconds=30, max_children=128, max_cases=768, max_requests_per_case=3)


def admit(root, deadline, allowance):
    require(time.monotonic() < deadline, 'bounded exit time budget exhausted')
    reserve = allowance+LIMITS['report_reserve_bytes']
    require(COST.used_bytes(root)+reserve <= LIMITS['output_bytes'], 'bounded exit output admission exhausted')
    require(shutil.disk_usage(root).free >= LIMITS['free_reserve_bytes']+reserve, 'bounded exit free-space reserve insufficient')


def run_case(binary, market, entry, feature, output, deadline, budget_root=None):
    output.mkdir()
    control = CYCLE.run_case(binary, market, entry, feature, output/'single-close', deadline, budget_root)
    control_plan = ORIGINAL.obj(output/'single-close/compiled-scenario.json')
    control_folder = output/'single-close'/('control' if control['control_reused'] else 'final')
    control_rows = CYCLE.ledger_rows(control_folder)
    plan, receipt = CORE.compile_retry(control_plan, market['events'], control_rows)
    receipt.update(control_plan_sha256=REVIEW.digest(output/'single-close/compiled-scenario.json'),
        control_inputs_sha256=REVIEW.digest(control_folder/'paper-input.jsonl'),
        control_updates_sha256=REVIEW.digest(control_folder/'paper-updates.jsonl'),
        control_case_sha256=REVIEW.digest(output/'single-close/policy-case.json'))
    REVIEW.save(output/'retry-compilation.json', receipt)
    REVIEW.save(output/'compiled-scenario.json', plan)
    reused = plan == control_plan
    if reused:
        final, final_rows = control, control_rows
    else:
        if budget_root is not None:
            admit(budget_root, deadline, LIMITS['extra_replay_allowance_bytes'])
        final = MODEL.proxy(binary, market, plan, output/'retry', deadline, budget_root)
        final_rows = CYCLE.ledger_rows(output/'retry')
    audit = CORE.verify_retry(control_plan, plan, market['events'], receipt, control_rows, final_rows)
    require(receipt['control_plan_sha256'] == REVIEW.digest(output/'single-close/compiled-scenario.json')
        and receipt['control_inputs_sha256'] == REVIEW.digest(control_folder/'paper-input.jsonl')
        and receipt['control_updates_sha256'] == REVIEW.digest(control_folder/'paper-updates.jsonl')
        and receipt['control_case_sha256'] == REVIEW.digest(output/'single-close/policy-case.json'),
        'original one-close control artifacts changed during extra replay')
    REVIEW.save(output/'retry-prefix-audit.json', audit)
    by_id = {d['order']['id']: d for d in final['orders']}
    first, retry = by_id.get('close'), by_id.get('close-retry')
    metrics = copy.deepcopy(final['metrics'])
    metrics.update(entry_quantity=by_id['entry']['native_final_order']['filled_quantity'], entry_outcome=by_id['entry']['outcome'],
        close_requested_quantity=None if first is None else first['order']['quantity'],
        close_quantity=None if first is None else first['native_final_order']['filled_quantity'],
        close_outcome=None if first is None else first['outcome'],
        close_decision_status=control['metrics']['close_decision_status'],
        known_position_at_decision=control['metrics']['known_position_at_decision'],
        retry_decision_status=receipt['status'], retry_known_position=receipt['known_position'],
        retry_requested_quantity=None if retry is None else retry['order']['quantity'],
        retry_quantity=None if retry is None else retry['native_final_order']['filled_quantity'],
        retry_outcome=None if retry is None else retry['outcome'])
    with localcontext() as context:
        context.prec = 100
        metrics['total_close_quantity'] = None if first is None else str(sum(
            (Decimal(o['native_final_order']['filled_quantity']) for o in final['orders'] if o['order']['id'] != 'entry'), Decimal(0)))
    result = dict(bounded_exit_policy_version=1, policy_id=CORE.POLICY['policy_id'], status='verified',
        actual_execution='unknown', exploratory=True, control_reused=reused, single_close_control=control,
        close_compilation=control['close_compilation'], causal_prefix_audit=control['causal_prefix_audit'],
        causal_prefix_verified=True, retry_compilation=ORIGINAL.CORE.stamps(receipt),
        retry_prefix_audit=audit, retry_prefix_verified=True, metrics=metrics, orders=final['orders'],
        native_checkpoints=control['native_checkpoints']+(0 if reused else final['native_checkpoints']))
    REVIEW.save(output/'bounded-case.json', result)
    return result


def compact(value):
    result = EVAL.compact(value)
    result.update(retry_prefix_verified=value['retry_prefix_verified'], retry_prefix_audit=value['retry_prefix_audit'],
        retry_compilation={key: value['retry_compilation'][key] for key in ('status', 'decision', 'known_position',
            'entry_filled_quantity', 'working_orders', 'risk_at_decision', 'prefix_records', 'prefix_sha256', 'delay_from_first_request_ns')})
    first = value['retry_compilation']['first_close_state']
    result['retry_compilation']['first_close_state'] = None if first is None else {
        key: first[key] for key in ('id', 'status', 'filled_quantity', 'cancel_pending')}
    return result


def code_files(quality_template, cost_template, template, theme, protocol):
    files = EVAL.code_files(quality_template, cost_template, template, theme, protocol)
    files.pop('evaluation_template'); files.pop('evaluation_protocol')
    return dict(files, bounded_exit_core=Path(CORE.__file__), bounded_exit_local=Path(__file__),
        bounded_exit_template=template, bounded_exit_protocol=protocol)


def generate(binary, experiment, quality, output, origin, quality_template, cost_template, template, theme, protocol):
    binary, experiment, quality, output = binary.resolve(), experiment.absolute(), quality.absolute(), output.resolve()
    require(binary.is_file() and os.access(binary, os.X_OK) and binary.stat().st_size <= 128*MIB, 'bounded installed executable required')
    require(origin in ('captured_public_data', 'synthetic_fixture'), 'explicit source origin required')
    require(not output.exists() and not output.is_relative_to(experiment.resolve()) and not output.is_relative_to(quality.resolve()),
        'bounded exit output must be new and outside original evidence')
    assets = dict(template=QUALITY.read_asset(template), theme=QUALITY.read_asset(theme), protocol=QUALITY.read_asset(protocol))
    require(REVIEW.digest(protocol) == CORE.PROTOCOL_SHA256, 'frozen bounded exit protocol differs')
    source = experiment/'supervision'
    REVIEW.plain(source/'supervisor.lock')
    with (source/'supervisor.lock').open('rb') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('supervisor is active; bounded exit requires stopped evidence') from None
        hashes, manifest, frozen, before = STUDY.frozen(quality, binary, origin, quality_template, theme)
        selected = EVAL.CORE.cohort(manifest)
        require(REVIEW.inventory(experiment) == before, 'source differs from frozen quality dataset')
        files = code_files(quality_template, cost_template, template, theme, protocol)
        code = {key: REVIEW.digest(path) for key, path in files.items()}; binary_sha = REVIEW.digest(binary)
        os.umask(0o077)
        output.parent.mkdir(parents=True, exist_ok=True)
        require(shutil.disk_usage(output.parent).free >= LIMITS['free_reserve_bytes']+LIMITS['case_allowance_bytes'],
            'bounded exit initial free-space reserve insufficient')
        output.mkdir(mode=0o700)
        for folder in ('input-quality', 'markets', 'cases'): (output/folder).mkdir()
        deadline = time.monotonic()+LIMITS['suite_seconds']
        for name in STUDY.INPUTS:
            destination = output/'input-quality'/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(quality/name, destination)
            require(REVIEW.digest(destination) == hashes[name], 'quality changed during snapshot')
        pinned = output/'replay.bin'
        shutil.copyfile(binary, pinned); pinned.chmod(0o700)
        require(REVIEW.digest(pinned) == binary_sha, 'installed executable changed during pinning')
        (output/'bounded-exit-protocol.md').write_bytes(assets['protocol'])
        REVIEW.save(output/'bounded-exit-policy.json', dict(policy=CORE.POLICY, limits=LIMITS,
            profiles=EVAL.CORE.PROFILES, original_cost_policy=CORE.FROZEN.POLICY,
            control_policy=CORE.CYCLE.POLICY, protocol_sha256=CORE.PROTOCOL_SHA256))
        cases = [dict(case_id=f'run-{child:06d}--{p["id"]}', child=child, profile=p['id'], previously_cost_probed=child in selected[:4],
            status='not_run', reason='Not admitted.', control=None, policy=None) for child in selected for p in EVAL.CORE.PROFILES]
        rows = [dict(child=r['run'], selected=r['run'] in selected, previously_cost_probed=r['run'] in selected[:4],
            status='not_run', reason='Not admitted.' if r['run'] in selected else 'Outside fixed development cohort.', feature=None)
            for r in frozen['runs']]
        report = dict(bounded_exit_report_version=1, experiment_id=CORE.POLICY['policy_id'],
            created_at_utc=datetime.now(timezone.utc).isoformat(), status='incomplete', origin=origin,
            selected_children=selected, previously_cost_probed_children=selected[:4], policy=CORE.POLICY, limits=LIMITS,
            rows=rows, cases=cases, totals=None, control_totals=None, comparisons=[], audit=None, error=None,
            source_unchanged=False, quality_unchanged=False, code_unchanged=False, actual_execution_known=False,
            portfolio_profit_evaluated=False, live_orders_enabled=False, full_window_verified=False, exploratory=True)
        try:
            admit(output, deadline, LIMITS['source_allowance_bytes'])
            report['audit'] = EVAL.fresh_quality(pinned, experiment, output/'quality-check', frozen, manifest, before, deadline)
            for row in rows:
                if not row['selected']: continue
                child_cases = [c for c in cases if c['child'] == row['child']]
                try:
                    admit(output, deadline, LIMITS['source_allowance_bytes'])
                except (ValueError, OSError) as error:
                    row['reason'] = str(error)
                    for c in child_cases: c['reason'] = str(error)
                    EVAL.progress(row, child_cases); continue
                folder = output/'markets'/f'run-{row["child"]:06d}'
                try:
                    market = EVAL.load_market(pinned, source/f'run-{row["child"]:06d}/session', folder,
                        row['child'], before, origin, deadline)
                    require(COST.used_bytes(folder) <= LIMITS['source_allowance_bytes'], 'source exceeded reserved output bound')
                    row['feature'] = market['feature']
                    if market['feature'] is None:
                        row.update(status='no_signal', reason='No directional feature after the fixed warmup.')
                        for c in child_cases: c.update(status='no_signal', reason=row['reason'])
                        EVAL.progress(row, child_cases); continue
                    REVIEW.save(folder/'selected-feature.json', market['feature'])
                except EVAL.ERRORS as error:
                    row.update(status='unavailable', reason=str(error)[:1200])
                    for c in child_cases: c.update(status='unavailable', reason=row['reason'])
                    EVAL.progress(row, child_cases); continue
                for case, profile in zip(child_cases, EVAL.CORE.PROFILES):
                    try:
                        admit(output, deadline, LIMITS['case_allowance_bytes'])
                    except (ValueError, OSError) as error:
                        case['reason'] = str(error); continue
                    folder = output/'cases'/case['case_id']; folder.mkdir()
                    try:
                        entry = CORE.FROZEN.entry_scenario(market['feature'], profile['assumptions'])
                        value = run_case(pinned, market, entry, market['feature'], folder/'policy', deadline, folder)
                        require(COST.used_bytes(folder) <= LIMITS['case_allowance_bytes'], 'case exceeded reserved output bound')
                        case.update(status='verified', reason=None, control=EVAL.compact(value['single_close_control']), policy=compact(value))
                        REVIEW.save(folder/'case-result.json', case)
                    except EVAL.ERRORS as error:
                        case.update(status='unavailable', reason=str(error)[:1200], control=None, policy=None)
                row.update(status='completed' if all(c['status'] == 'verified' for c in child_cases) else 'incomplete', reason=None)
                EVAL.progress(row, child_cases)
        except EVAL.ERRORS as error:
            report['error'] = str(error)[:1200]
        try:
            after = REVIEW.inventory(experiment); REVIEW.save(output/'source-after.json', after)
            report['source_unchanged'] = before == after
            report['quality_unchanged'] = STUDY.quality_inputs(quality) == hashes
            report['code_unchanged'] = code == {key: REVIEW.digest(path) for key, path in files.items()} \
                and binary_sha == REVIEW.digest(binary) == REVIEW.digest(pinned)
        except EVAL.ERRORS as error:
            report['error'] = str(error)[:1200]
        if not all(report[k] for k in ('source_unchanged', 'quality_unchanged', 'code_unchanged')):
            report.update(status='source_changed', error='Source, quality, executable or bounded exit producer changed.')
            for c in cases: c.update(status='unavailable', reason='Changed evidence; metrics not admitted.', control=None, policy=None)
        elif report['audit'] is not None and all(c['status'] in ('verified', 'no_signal') for c in cases):
            report['status'] = 'completed'
        report['totals'], report['control_totals'], report['comparisons'] = CORE.summarize(cases)
        inventory = {p.relative_to(output).as_posix(): REVIEW.digest(p) for p in sorted(output.rglob('*')) if p.is_file()}
        REVIEW.save(output/'audit-inventory.json', dict(audit_inventory_version=1, files=inventory))
        report['provenance'] = dict(source_inventory_sha256=manifest['source_inventory_sha256'], input_quality_hashes=hashes,
            installed_binary_sha256=binary_sha, code_hashes=code, protocol_sha256=CORE.PROTOCOL_SHA256,
            audit_inventory=dict(file='audit-inventory.json', files=len(inventory), sha256=REVIEW.digest(output/'audit-inventory.json')))
        require(COST.used_bytes(output) <= LIMITS['output_bytes']-LIMITS['report_reserve_bytes'], 'bounded exit exceeded report reserve')
        require(len(QUALITY.encoded(report)) <= 6*MIB, 'bounded exit report exceeds limit')
        REVIEW.save(output/'bounded-exit-report.json', report)
        with (output/'bounded-exit.html').open('x') as stream:
            stream.write(QUALITY.render(report, assets['template'].decode(), assets['theme'].decode()))
        return report


def readout(report):
    result = {k: report[k] for k in ('status', 'experiment_id', 'source_unchanged', 'quality_unchanged', 'code_unchanged',
        'selected_children', 'totals', 'control_totals', 'error')}
    result.update(actual_execution='unknown', exploratory=True, retry_cases=[], baseline_cases=[], nonverified_cases=[])
    for c in report['cases']:
        if c['status'] not in ('verified', 'no_signal'):
            result['nonverified_cases'].append(dict(case=c['case_id'], status=c['status'], reason=c['reason']))
        if c['status'] != 'verified': continue
        old, m = c['control']['metrics'], c['policy']['metrics']
        if m['retry_requested_quantity'] is not None or c['profile'] == 'baseline':
            row = dict(case=c['case_id'],control_outcome=old['outcome'],control_position=old['ending_position_quantity'],
                retry_decision=m['retry_decision_status'],retry_known_position=m['retry_known_position'],
                retry_requested=m['retry_requested_quantity'],retry_filled=m['retry_quantity'],retry_outcome=m['retry_outcome'],
                outcome=m['outcome'],ending_position=m['ending_position_quantity'],pending_orders=m['pending_order_ids'],
                conditional_closed_pnl=m['conditional_closed_pnl'],fees=m['fees'],retry_prefix_verified=c['policy']['retry_prefix_verified'])
            if m['retry_requested_quantity'] is not None: result['retry_cases'].append(row)
            if c['profile'] == 'baseline': result['baseline_cases'].append(row)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'experiment', 'quality', 'output-dir', 'quality-template', 'cost-template', 'template', 'theme', 'protocol'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--origin', choices=('captured-public-data', 'synthetic-fixture'), required=True)
    args = parser.parse_args()
    try:
        report = generate(args.binary, args.experiment, args.quality, args.output_dir, args.origin.replace('-', '_'),
            args.quality_template, args.cost_template, args.template, args.theme, args.protocol)
    except EVAL.ERRORS as error:
        parser.exit(2, 'Bounded exit refused: '+str(error)+'\n')
    print(json.dumps(readout(report), indent=2))
    return 0 if report['status'] == 'completed' else 1


if __name__ == '__main__': raise SystemExit(main())

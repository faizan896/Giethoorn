#!/usr/bin/env python3
"""Offline R002 research on the full frozen development cohort."""
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
    from . import momentum_core as CORE, bounded_exit_local as BOUND
else:
    import momentum_core as CORE
    import bounded_exit_local as BOUND

EVAL = BOUND.EVAL
CYCLE, MODEL = EVAL.CYCLE, EVAL.CYCLE.MODEL
REVIEW, QUALITY, COST, STUDY, ORIGINAL = EVAL.REVIEW, EVAL.QUALITY, EVAL.COST, EVAL.STUDY, EVAL.ORIGINAL
require, MIB, LIMITS = REVIEW.require, 1024*1024, CORE.LIMITS


class AdmissionError(ValueError):
    pass


def admit(root, deadline, allowance):
    reserve = allowance+LIMITS['report_reserve_bytes']
    if time.monotonic() >= deadline: raise AdmissionError('R002 time budget exhausted')
    if COST.used_bytes(root)+reserve > LIMITS['output_bytes']: raise AdmissionError('R002 output admission exhausted')
    if shutil.disk_usage(root).free < LIMITS['free_reserve_bytes']+reserve: raise AdmissionError('R002 free-space reserve insufficient')


def load_market(binary, source, output, child, expected_source, origin, deadline):
    output.mkdir()
    ORIGINAL.native(binary, ['paper-market-replay','--input',str(source),'--output-dir',str(output/'market'),
        '--origin',origin.replace('_','-'),'--feed','bbo'],output/'market.stdout.json',output/'market.stderr',deadline)
    report = ORIGINAL.obj(output/'market/market-replay.json')
    require(report == ORIGINAL.obj(output/'market.stdout.json'), 'R002 native market report differs')
    COST.match_source(dict(market=report),expected_source,child)
    require(report['paper']['config']['coin'] == CORE.POLICY['coin']
        and report['paper']['config']['source']['network'] == CORE.POLICY['network'], 'R002 requires BTC mainnet')
    original = list(QUALITY.source_records(output/'market/source'))
    require(len(original) < 10000 and len(original) == report['source_report']['records'], 'R002 source count differs')
    frames, links = ORIGINAL.lines(output/'market/paper-updates.jsonl'), ORIGINAL.lines(output/'market/market-links.jsonl')
    events = ORIGINAL.CORE.market_events(original,frames,links)
    ORIGINAL.native(binary,['replay','--input',str(output/'market/source')],
        output/'normalized.jsonl',output/'normalized-report.json',deadline)
    require(ORIGINAL.obj(output/'normalized-report.json') == report['source_report'], 'R002 normalization differs')
    normalization = CORE.verify_normalization(events,ORIGINAL.lines(output/'normalized.jsonl'))
    REVIEW.save(output/'normalization-audit.json',normalization)
    selection = CORE.select(events,child)
    audit = CORE.verify_selection(events,child,selection)
    REVIEW.save(output/'selection.json',ORIGINAL.CORE.stamps(selection))
    REVIEW.save(output/'selection-audit.json',audit)
    REVIEW.save(output/'selected-feature.json',ORIGINAL.CORE.stamps(selection['feature']))
    selection_hashes = {name:REVIEW.digest(output/name) for name in ('selection.json','selection-audit.json','selected-feature.json')}
    # The feature is immutable on disk before reading any forward label or fill.
    label = CORE.label(events,selection['feature'])
    REVIEW.save(output/'prediction-diagnostic.json',ORIGINAL.CORE.stamps(label))
    require(all(REVIEW.digest(output/name) == sha for name,sha in selection_hashes.items()), 'R002 selected feature changed during diagnostic')
    return dict(directory=output/'market',report=report,frames=frames,links=links,events=events,
        feature=selection['feature'],selection=selection,label=label,selection_hashes=selection_hashes,selection_folder=output)


def run_case(binary, market, entry, feature, output, deadline, budget_root=None):
    output.mkdir()
    REVIEW.save(output/'entry-audit.json',CORE.verify_entry(feature,entry))
    REVIEW.save(output/'entry-scenario.json',entry)
    control = MODEL.proxy(binary,market,entry,output/'entry-control',deadline,budget_root)
    control_rows = CYCLE.ledger_rows(output/'entry-control')
    decision = CORE.close_decision(market['events'],feature)
    plan, receipt = CORE.compile_close(entry,decision,control_rows)
    original_files = [output/'entry-scenario.json',output/'entry-audit.json']+[
        p for p in sorted((output/'entry-control').rglob('*')) if p.is_file()]
    hashes = {p.relative_to(output).as_posix():REVIEW.digest(p) for p in original_files}
    REVIEW.save(output/'first-close-compilation.json',receipt)
    REVIEW.save(output/'first-close-scenario.json',plan)
    first_reused = plan == entry
    if first_reused:
        single, single_rows, single_folder = control, control_rows, output/'entry-control'
    else:
        if budget_root is not None: admit(budget_root,deadline,128*MIB)
        single_folder = output/'first-close'
        single = MODEL.proxy(binary,market,plan,single_folder,deadline,budget_root)
        single_rows = CYCLE.ledger_rows(single_folder)
    first_audit = CORE.verify_close(entry,plan,market['events'],feature,receipt,control_rows,single_rows)
    REVIEW.save(output/'first-close-prefix-audit.json',first_audit)
    extra, retry = CORE.BOUND.compile_retry(plan,market['events'],single_rows)
    for p in [output/'first-close-scenario.json',output/'first-close-compilation.json',
        output/'first-close-prefix-audit.json']+[p for p in sorted(single_folder.rglob('*')) if p.is_file()]:
        name, sha = p.relative_to(output).as_posix(), REVIEW.digest(p)
        require(name not in hashes or hashes[name] == sha, 'R002 retained control artifacts changed')
        hashes[name] = sha
    retry['retained_control_hashes'] = hashes
    REVIEW.save(output/'retry-compilation.json',retry)
    REVIEW.save(output/'compiled-scenario.json',extra)
    reused = extra == plan
    if reused:
        final, final_rows = single, single_rows
    else:
        if budget_root is not None: admit(budget_root,deadline,128*MIB)
        final = MODEL.proxy(binary,market,extra,output/'retry',deadline,budget_root)
        final_rows = CYCLE.ledger_rows(output/'retry')
    retry_audit = CORE.BOUND.verify_retry(plan,extra,market['events'],retry,single_rows,final_rows)
    require(all(REVIEW.digest(output/p) == sha for p,sha in hashes.items()), 'R002 retained control artifacts changed')
    REVIEW.save(output/'retry-prefix-audit.json',retry_audit)
    by_id = {o['order']['id']:o for o in final['orders']}
    first, extra_order = by_id.get('close'), by_id.get('close-retry')
    metrics = copy.deepcopy(final['metrics'])
    metrics.update(entry_quantity=by_id['entry']['native_final_order']['filled_quantity'],
        entry_outcome=by_id['entry']['outcome'],close_requested_quantity=None if first is None else first['order']['quantity'],
        close_quantity=None if first is None else first['native_final_order']['filled_quantity'],
        close_outcome=None if first is None else first['outcome'],close_decision_status=receipt['status'],
        known_position_at_decision=receipt['known_position'],retry_decision_status=retry['status'],
        retry_known_position=retry['known_position'],retry_requested_quantity=None if extra_order is None else extra_order['order']['quantity'],
        retry_quantity=None if extra_order is None else extra_order['native_final_order']['filled_quantity'],
        retry_outcome=None if extra_order is None else extra_order['outcome'])
    with localcontext() as ctx:
        ctx.prec = 100
        metrics['total_close_quantity'] = None if first is None else str(sum(
            (Decimal(o['native_final_order']['filled_quantity']) for o in final['orders'] if o['order']['id'] != 'entry'),Decimal(0)))
    result = dict(r002_policy_version=1,policy_id=CORE.POLICY['experiment_id'],status='verified',actual_execution='unknown',
        exploratory=True,control_reused=first_reused,close_compilation=ORIGINAL.CORE.stamps(receipt),
        causal_prefix_audit=first_audit,causal_prefix_verified=True,retry_compilation=ORIGINAL.CORE.stamps(retry),
        retry_prefix_audit=retry_audit,retry_prefix_verified=True,metrics=metrics,orders=final['orders'],
        native_checkpoints=control['native_checkpoints']+(0 if first_reused else single['native_checkpoints'])
            +(0 if reused else final['native_checkpoints']))
    REVIEW.save(output/'momentum-case.json',result)
    return result


def code_files(quality_template, cost_template, template, theme, protocol, policy_spec):
    files = BOUND.code_files(quality_template,cost_template,template,theme,protocol)
    files.pop('bounded_exit_template'); files.pop('bounded_exit_protocol')
    return dict(files,momentum_core=Path(CORE.__file__),momentum_local=Path(__file__),
        momentum_template=template,momentum_protocol=protocol,momentum_policy_spec=policy_spec)


def compact(value):
    return BOUND.compact(value)


def generate(binary, experiment, quality, output, origin, quality_template, cost_template, template, theme, protocol, policy_spec):
    binary, experiment, quality, output = binary.resolve(), experiment.absolute(), quality.absolute(), output.resolve()
    require(binary.is_file() and os.access(binary, os.X_OK) and binary.stat().st_size <= 128*MIB, 'bounded installed executable required')
    require(origin in ('captured_public_data', 'synthetic_fixture'), 'explicit source origin required')
    require(not output.exists() and not output.is_relative_to(experiment.resolve()) and not output.is_relative_to(quality.resolve()),
        'R002 output must be new and outside original evidence')
    assets = dict(template=QUALITY.read_asset(template), theme=QUALITY.read_asset(theme), protocol=QUALITY.read_asset(protocol), policy_spec=QUALITY.read_asset(policy_spec))
    require(REVIEW.digest(protocol) == CORE.PROTOCOL_SHA256 and REVIEW.digest(policy_spec) == CORE.POLICY_SHA256, 'frozen R002 specification differs')
    require(json.loads(assets['policy_spec']) == CORE.POLICY and CORE.PROFILES == EVAL.CORE.PROFILES, 'R002 constants or profiles differ')
    source = experiment/'supervision'
    REVIEW.plain(source/'supervisor.lock')
    with (source/'supervisor.lock').open('rb') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('supervisor is active; R002 requires stopped evidence') from None
        hashes, manifest, frozen, before = STUDY.frozen(quality, binary, origin, quality_template, theme)
        selected = EVAL.CORE.cohort(manifest)
        require(REVIEW.inventory(experiment) == before, 'source differs from frozen quality dataset')
        files = code_files(quality_template, cost_template, template, theme, protocol, policy_spec)
        code = {key: REVIEW.digest(path) for key, path in files.items()}; binary_sha = REVIEW.digest(binary)
        os.umask(0o077)
        output.parent.mkdir(parents=True, exist_ok=True)
        require(shutil.disk_usage(output.parent).free >= LIMITS['free_reserve_bytes']+LIMITS['case_allowance_bytes'],
            'R002 initial free-space reserve insufficient')
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
        (output/'momentum-protocol.md').write_bytes(assets['protocol'])
        (output/'momentum-policy.json').write_bytes(assets['policy_spec'])
        cases = [dict(case_id=f'run-{child:06d}--{p["id"]}', child=child, profile=p['id'], previously_cost_probed=child in selected[:4],
            status='not_run', reason='Not admitted.', policy=None) for child in selected for p in EVAL.CORE.PROFILES]
        rows = [dict(child=r['run'], selected=r['run'] in selected, previously_cost_probed=r['run'] in selected[:4],
            status='not_run', reason='Not admitted.' if r['run'] in selected else 'Outside fixed development cohort.', feature=None)
            for r in frozen['runs']]
        report = dict(r002_report_version=1, experiment_id=CORE.POLICY['experiment_id'],
            created_at_utc=datetime.now(timezone.utc).isoformat(), status='incomplete', origin=origin,
            selected_children=selected, previously_cost_probed_children=selected[:4], policy=CORE.POLICY, limits=LIMITS,
            rows=rows, cases=cases, totals=None, screen=None, audit=None, error=None, verification_failed=False,
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
                    market = load_market(pinned, source/f'run-{row["child"]:06d}/session', folder,
                        row['child'], before, origin, deadline)
                    require(COST.used_bytes(folder) <= LIMITS['source_allowance_bytes'], 'source exceeded reserved output bound')
                    row['feature'] = market['feature']
                    row['selection_counts'] = market['selection']['counts']
                    row['prediction_diagnostic'] = market['label']
                    if market['feature'] is None:
                        row.update(status='no_signal', reason='No qualifying R002 momentum feature.')
                        for c in child_cases: c.update(status='no_signal', reason=row['reason'])
                        EVAL.progress(row, child_cases); continue
                except EVAL.ERRORS as error:
                    report['verification_failed'] = True
                    report['error'] = report['error'] or str(error)[:1200]
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
                        entry = CORE.entry_scenario(market['feature'], profile)
                        value = run_case(pinned, market, entry, market['feature'], folder/'policy', deadline, folder)
                        require(all(REVIEW.digest(market['selection_folder']/name) == sha for name,sha in market['selection_hashes'].items()),
                            'R002 selected feature changed during execution')
                        require(COST.used_bytes(folder) <= LIMITS['case_allowance_bytes'], 'case exceeded reserved output bound')
                        case.update(status='verified', reason=None, policy=compact(value))
                        REVIEW.save(folder/'case-result.json', case)
                    except EVAL.ERRORS as error:
                        report['verification_failed'] = True
                        report['error'] = report['error'] or str(error)[:1200]
                        case.update(status='unavailable', reason=str(error)[:1200], policy=None)
                row.update(status='completed' if all(c['status'] == 'verified' for c in child_cases) else 'incomplete', reason=None)
                EVAL.progress(row, child_cases)
        except AdmissionError as error:
            report['error'] = str(error)[:1200]
        except EVAL.ERRORS as error:
            report['verification_failed'] = True
            report['error'] = str(error)[:1200]
        try:
            after = REVIEW.inventory(experiment); REVIEW.save(output/'source-after.json', after)
            report['source_unchanged'] = before == after
            report['quality_unchanged'] = STUDY.quality_inputs(quality) == hashes
            report['code_unchanged'] = code == {key: REVIEW.digest(path) for key, path in files.items()} \
                and binary_sha == REVIEW.digest(binary) == REVIEW.digest(pinned)
        except EVAL.ERRORS as error:
            report['verification_failed'] = True
            report['error'] = str(error)[:1200]
        if report['verification_failed'] or not all(report[k] for k in ('source_unchanged', 'quality_unchanged', 'code_unchanged')):
            report.update(status='invalid', error=report['error'] or 'Source, quality, executable, producer or R002 verification changed.')
            for c in cases: c.update(status='unavailable', reason='Unverified R002 evidence or execution; metrics not admitted.', policy=None)
        elif report['audit'] is not None and all(c['status'] in ('verified', 'no_signal') for c in cases):
            report['status'] = 'completed'
        report['totals'], report['screen'] = CORE.summarize(cases, selected, invalid=report['status'] == 'invalid')
        report = ORIGINAL.CORE.stamps(report)
        inventory = {p.relative_to(output).as_posix(): REVIEW.digest(p) for p in sorted(output.rglob('*')) if p.is_file()}
        REVIEW.save(output/'audit-inventory.json', dict(audit_inventory_version=1, files=inventory))
        report['provenance'] = dict(source_inventory_sha256=manifest['source_inventory_sha256'], input_quality_hashes=hashes,
            installed_binary_sha256=binary_sha, code_hashes=code, protocol_sha256=CORE.PROTOCOL_SHA256, policy_sha256=CORE.POLICY_SHA256,
            audit_inventory=dict(file='audit-inventory.json', files=len(inventory), sha256=REVIEW.digest(output/'audit-inventory.json')))
        require(COST.used_bytes(output) <= LIMITS['output_bytes']-LIMITS['report_reserve_bytes'], 'R002 exceeded report reserve')
        require(len(QUALITY.encoded(report)) <= 6*MIB, 'R002 report exceeds limit')
        REVIEW.save(output/'momentum-report.json', report)
        with (output/'momentum.html').open('x') as stream:
            stream.write(QUALITY.render(report, assets['template'].decode(), assets['theme'].decode()))
        return report


def readout(report):
    result = {k:report[k] for k in ('status','experiment_id','source_unchanged','quality_unchanged','code_unchanged',
        'selected_children','totals','screen','error')}
    result.update(actual_execution='unknown',exploratory=True,selected_features=[],baseline_cases=[],unresolved_cases=[])
    for row in report['rows']:
        if row['selected']:
            result['selected_features'].append({k:row.get(k) for k in ('child','status','feature','selection_counts','prediction_diagnostic','reason')})
    for case in report['cases']:
        if case['status'] != 'verified': continue
        m = case['policy']['metrics']
        row = dict(case=case['case_id'],outcome=m['outcome'],conditional_closed_pnl=m['conditional_closed_pnl'],
            fees=m['fees'],ending_position=m['ending_position_quantity'],pending_orders=m['pending_order_ids'],
            entry_filled=m['entry_quantity'],first_close_filled=m['close_quantity'],retry_requested=m['retry_requested_quantity'],
            retry_filled=m['retry_quantity'],first_close_decision=m['close_decision_status'],retry_decision=m['retry_decision_status'])
        if case['profile'] == 'baseline': result['baseline_cases'].append(row)
        if m['conditional_closed_pnl'] is None: result['unresolved_cases'].append(row)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary','experiment','quality','output-dir','quality-template','cost-template','template','theme','protocol','policy-spec'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--origin',choices=('captured-public-data','synthetic-fixture'),required=True)
    args = parser.parse_args()
    try:
        report = generate(args.binary,args.experiment,args.quality,args.output_dir,args.origin.replace('-','_'),
            args.quality_template,args.cost_template,args.template,args.theme,args.protocol,args.policy_spec)
    except EVAL.ERRORS as error:
        parser.exit(2,'R002 refused: '+str(error)+'\n')
    print(json.dumps(readout(report),indent=2))
    return 0 if report['status'] == 'completed' else 1


if __name__ == '__main__': raise SystemExit(main())

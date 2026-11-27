#!/usr/bin/env python3
"""Explain a completed retained R002 bundle; replay saved inputs, never run policy."""
import argparse
import copy
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import time

if __package__:
    from . import momentum_local as RUN, momentum_explain_core as CORE
else:
    import momentum_local as RUN
    import momentum_explain_core as CORE

REVIEW, QUALITY, ORIGINAL = RUN.REVIEW, RUN.QUALITY, RUN.ORIGINAL
require, MIB = REVIEW.require, 1024*1024
PROTOCOL_SHA256 = '5260b5d0fef6eb890c40ead542b40c52932c11bd1612479550659f4b9250a1f6'
LIMITS = dict(input_bytes=17*1024*MIB,max_files=100000,max_file_bytes=128*MIB,
    output_bytes=1024*MIB,free_reserve_bytes=1024*MIB,report_reserve_bytes=32*MIB,
    operation_allowance_bytes=128*MIB,suite_seconds=3600,native_seconds=30)
ERRORS = (ValueError,OSError,KeyError,TypeError,IndexError,ArithmeticError,TimeoutError,subprocess.TimeoutExpired)


def path_in(root, name):
    require(type(name) is str and name and '\\' not in name and '\n' not in name, 'invalid evidence path')
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and not set(relative.parts).intersection(('.', '..'))
        and relative.as_posix() == name, 'unsafe evidence path')
    return root/name


def inventory(root, deadline):
    require(root.is_dir() and root.absolute() == root.resolve(), 'regular canonical evidence directory required')
    result, size = {}, 0
    for path in sorted(root.rglob('*')):
        require(time.monotonic() < deadline, 'diagnostic time budget exhausted during inventory')
        info = path.lstat()
        require(not path.is_symlink(), 'evidence symlink refused')
        if stat.S_ISDIR(info.st_mode): continue
        require(stat.S_ISREG(info.st_mode), 'evidence artifacts must be regular files')
        size += info.st_size
        require(len(result) < LIMITS['max_files'] and size <= LIMITS['input_bytes']
            and info.st_size <= LIMITS['max_file_bytes'], 'evidence inventory exceeds diagnostic bounds')
        name = path.relative_to(root).as_posix(); path_in(root,name)
        result[name] = dict(bytes=info.st_size,mtime_ns=info.st_mtime_ns,sha256=REVIEW.digest(path))
    return result


def fingerprints(rows):
    return {name:{key:value[key] for key in ('bytes','sha256')} for name,value in rows.items()}


def admit(output, deadline):
    require(time.monotonic() < deadline, 'diagnostic time budget exhausted')
    reserve = LIMITS['operation_allowance_bytes']+LIMITS['report_reserve_bytes']
    require(RUN.COST.used_bytes(output)+reserve <= LIMITS['output_bytes'], 'diagnostic output admission exhausted')
    require(shutil.disk_usage(output).free >= LIMITS['free_reserve_bytes']+reserve, 'diagnostic free-space reserve insufficient')


def frozen(source, binary, assets, deadline):
    before = inventory(source,deadline)
    report = ORIGINAL.obj(source/'momentum-report.json',6*MIB)
    require(report.get('r002_report_version') == 1 and report.get('experiment_id') == CORE.POLICY['experiment_id']
        and report.get('status') == 'completed' and report.get('verification_failed') is False
        and all(report.get(k) is True for k in ('source_unchanged','quality_unchanged','code_unchanged')),
        'completed unchanged version-1 R002 bundle required')
    require(all(report.get(k) is False for k in ('actual_execution_known','portfolio_profit_evaluated','live_orders_enabled','full_window_verified'))
        and report.get('exploratory') is True and report['policy'] == ORIGINAL.CORE.stamps(RUN.CORE.POLICY)
        and report['limits'] == RUN.LIMITS and report['error'] is None
        and report['origin'] in ('captured_public_data','synthetic_fixture'), 'unsupported original R002 scope or policy')
    p = report['provenance']; bound = p['audit_inventory']
    require(bound['file'] == 'audit-inventory.json' and before[bound['file']]['sha256'] == bound['sha256'],
        'original inventory fingerprint differs')
    sealed = ORIGINAL.obj(source/bound['file'],32*MIB)
    require(sealed['audit_inventory_version'] == 1 and len(sealed['files']) == bound['files'], 'original inventory count differs')
    for name, sha in sealed['files'].items():
        path_in(source,name)
        require(name in before and before[name]['sha256'] == sha, 'original artifact fingerprint differs: '+name)
    require(set(before) == set(sealed['files']) | {'audit-inventory.json','momentum-report.json','momentum.html'},
        'unbound or missing original artifacts')
    binary_sha = REVIEW.digest(binary)
    require(binary_sha == p['installed_binary_sha256'] == before['replay.bin']['sha256'], 'installed original executable differs')
    require(p['protocol_sha256'] == RUN.CORE.PROTOCOL_SHA256 == before['momentum-protocol.md']['sha256']
        and p['policy_sha256'] == RUN.CORE.POLICY_SHA256 == before['momentum-policy.json']['sha256']
        and ORIGINAL.obj(source/'momentum-policy.json') == RUN.CORE.POLICY, 'frozen original specifications differ')
    producers = RUN.code_files(assets['quality_template'],assets['cost_template'],assets['momentum_template'],
        assets['theme'],assets['original_protocol'],assets['policy_spec'])
    require({key:REVIEW.digest(path) for key,path in producers.items()} == p['code_hashes'], 'original producer/assets differ')
    hashes, manifest, quality, expected_source = RUN.STUDY.frozen(source/'input-quality',binary,
        report['origin'],assets['quality_template'],assets['theme'])
    require(hashes == p['input_quality_hashes'] and manifest['source_inventory_sha256'] == p['source_inventory_sha256']
        and ORIGINAL.obj(source/'source-after.json',16*MIB) == expected_source, 'copied original quality/source identity differs')
    selected = RUN.EVAL.CORE.cohort(manifest)
    require(report['selected_children'] == selected and report['previously_cost_probed_children'] == selected[:4], 'frozen cohort differs')
    require([r['child'] for r in report['rows']] == [r['run'] for r in quality['runs']]
        and all(type(r['selected']) is bool and r['selected'] == (r['child'] in selected) for r in report['rows']), 'original row membership differs')
    expected_slots = [(child,profile['id']) for child in selected for profile in RUN.CORE.PROFILES]
    require([(c['child'],c['profile']) for c in report['cases']] == expected_slots
        and all(c['case_id'] == f'run-{c["child"]:06d}--{c["profile"]}' for c in report['cases'])
        and all(c['status'] in ('verified','no_signal') for c in report['cases']), 'complete original case membership differs')
    require(report['audit'] is not None, 'original quality audit receipt missing')
    require(RUN.CORE.summarize(report['cases'],selected) == (report['totals'],report['screen']), 'original totals or classification differ')
    return report,before,expected_source,producers


def equal_file(actual, expected):
    require(actual.stat().st_size == expected.stat().st_size and REVIEW.digest(actual) == REVIEW.digest(expected),
        'native replay differs from retained output: '+expected.name)
    return dict(bytes=actual.stat().st_size,sha256=REVIEW.digest(actual))


def verify_market(binary, folder, scratch, child, expected_source, origin, deadline):
    """Only native source replay; selection is recomputed solely for equality."""
    scratch.mkdir()
    ORIGINAL.native(binary,['paper-market-replay','--input',str(folder/'market/source'),
        '--output-dir',str(scratch/'market'),'--origin',origin.replace('_','-'),'--feed','bbo'],
        scratch/'market.stdout.json',scratch/'market.stderr',deadline)
    report = ORIGINAL.obj(folder/'market/market-replay.json')
    require(report == ORIGINAL.obj(scratch/'market.stdout.json') == ORIGINAL.obj(folder/'market.stdout.json'), 'retained native market report differs')
    require(report['source']['origin'] == origin and report['paper']['config']['coin'] == 'BTC'
        and report['paper']['config']['source']['network'] == 'mainnet', 'retained market origin or domain differs')
    RUN.COST.match_source(dict(market=report),expected_source,child)
    expected = fingerprints(inventory(folder/'market',deadline))
    require(fingerprints(inventory(scratch/'market',deadline)) == expected, 'native market replay files differ from retained cache')
    ORIGINAL.native(binary,['replay','--input',str(folder/'market/source')],scratch/'normalized.jsonl',scratch/'normalized-report.json',deadline)
    equal_file(scratch/'normalized.jsonl',folder/'normalized.jsonl')
    equal_file(scratch/'normalized-report.json',folder/'normalized-report.json')
    original = list(QUALITY.source_records(folder/'market/source'))
    require(0 < len(original) < 10000 and len(original) == report['source_report']['records'], 'retained source count differs')
    frames, links = ORIGINAL.lines(folder/'market/paper-updates.jsonl'), ORIGINAL.lines(folder/'market/market-links.jsonl')
    events = ORIGINAL.CORE.market_events(original,frames,links)
    normalization = RUN.CORE.verify_normalization(events,ORIGINAL.lines(folder/'normalized.jsonl'))
    require(normalization == ORIGINAL.obj(folder/'normalization-audit.json'), 'original normalization audit differs')
    selection = RUN.CORE.select(events,child)
    require(ORIGINAL.CORE.stamps(selection) == ORIGINAL.obj(folder/'selection.json')
        and RUN.CORE.verify_selection(events,child,selection) == ORIGINAL.obj(folder/'selection-audit.json')
        and ORIGINAL.CORE.stamps(selection['feature']) == ORIGINAL.parse(ORIGINAL.read(folder/'selected-feature.json')),
        'original selection/feature differs; no replacement admitted')
    label = RUN.CORE.label(events,selection['feature'])
    require(ORIGINAL.CORE.stamps(label) == ORIGINAL.obj(folder/'prediction-diagnostic.json'), 'original label diagnostic differs')
    receipt = dict(status='verified',child=child,source_records=len(events),source_files=expected,
        native_market_files_byte_equal=True,normalization=normalization,
        normalized_sha256=REVIEW.digest(folder/'normalized.jsonl'),selection_verified=True,label_verified=True)
    shutil.rmtree(scratch)  # New scratch only, after all exact comparisons succeed.
    return dict(events=events,directory=folder/'market',feature=selection['feature'],selection=selection,label=label),receipt


def verify_ledger(binary, market, folder, scratch, deadline):
    scratch.mkdir()
    ORIGINAL.native(binary,['paper-replay','--input',str(folder/'paper-input.jsonl')],
        scratch/'updates.jsonl',scratch/'report.json',deadline)
    updates = equal_file(scratch/'updates.jsonl',folder/'paper-updates.jsonl')
    native = equal_file(scratch/'report.json',folder/'paper-report.json')
    records, links, frames = RUN.CYCLE.ledger_rows(folder)
    scenario, report = ORIGINAL.obj(folder/'scenario.json'), ORIGINAL.obj(folder/'paper-report.json')
    decisions = ORIGINAL.obj(folder/'decisions.json')
    require(decisions['proxy_model_version'] == 1 and ORIGINAL.obj(folder/'proxy-policy.json') == RUN.MODEL.CORE.POLICY,
        'retained manual model version differs')
    metrics = RUN.MODEL.VERIFY.verify(market['events'],ORIGINAL.lines(market['directory']/'paper-input.jsonl'),
        scenario,records,links,frames,report,decisions['decisions'])
    require(metrics == ORIGINAL.obj(folder/'cost-audit.json'), 'original independent ledger audit differs')
    paths = sorted((folder/'checkpoints').glob('*.receipt.json'))
    require(0 < len(paths) <= RUN.MODEL.LIMITS['max_checkpoints']
        and [p.name for p in paths] == [f'{n:04d}.receipt.json' for n in range(1,len(paths)+1)], 'checkpoint membership differs')
    receipts = [ORIGINAL.obj(path) for path in paths]
    require([r['records'] for r in receipts] == sorted(set(r['records'] for r in receipts))
        and receipts[-1]['records'] == len(records), 'checkpoint prefix order differs')
    for receipt in receipts:
        path = path_in(folder,receipt['native_report']); require(REVIEW.digest(path) == receipt['native_report_sha256'], 'checkpoint report fingerprint differs')
        prefix_report, last = ORIGINAL.obj(path), frames[receipt['records']-1]
        require(prefix_report['records'] == receipt['records'] and prefix_report['account'] == last['account']
            and prefix_report['risk'] == last['risk'] and prefix_report['config'] == report['config'], 'checkpoint native state differs')
    RUN.MODEL.verify_prefixes(folder/'paper-input.jsonl',receipts,'input')
    RUN.MODEL.verify_prefixes(folder/'paper-updates.jsonl',receipts,'updates')
    receipt = dict(status='verified',native_updates=updates,native_report=native,checkpoints=len(receipts),
        source_decimal_audit=metrics,original_input_sha256=REVIEW.digest(folder/'paper-input.jsonl'))
    shutil.rmtree(scratch)
    return dict(metrics=metrics,orders=decisions['decisions'],native_checkpoints=len(receipts)),(records,links,frames),receipt


def verify_case(binary, market, folder, scratch, deadline):
    scratch.mkdir(); ledgers = {}
    entry, first, final = [ORIGINAL.obj(folder/name) for name in ('entry-scenario.json','first-close-scenario.json','compiled-scenario.json')]
    feature = market['feature']; events = market['events']
    require(RUN.CORE.verify_entry(feature,entry) == ORIGINAL.obj(folder/'entry-audit.json'), 'original entry audit differs')
    control, control_rows, audit = verify_ledger(binary,market,folder/'entry-control',scratch/'entry-control',deadline)
    ledgers['entry-control'] = audit
    require(entry == ORIGINAL.obj(folder/'entry-control/scenario.json'), 'entry control plan differs')
    first_reused = first == entry
    if first_reused: single,single_rows,single_folder = control,control_rows,folder/'entry-control'
    else:
        single_folder = folder/'first-close'
        single,single_rows,audit = verify_ledger(binary,market,single_folder,scratch/'first-close',deadline)
        ledgers['first-close'] = audit
    require(first == ORIGINAL.obj(single_folder/'scenario.json'), 'first close ledger plan differs')
    first_receipt = ORIGINAL.obj(folder/'first-close-compilation.json')
    first_audit = RUN.CORE.verify_close(entry,first,events,feature,first_receipt,control_rows,single_rows)
    require(first_audit == ORIGINAL.obj(folder/'first-close-prefix-audit.json'), 'first close prefix audit differs')
    retry = ORIGINAL.obj(folder/'retry-compilation.json')
    expected_controls = [folder/'entry-scenario.json',folder/'entry-audit.json']+list((folder/'entry-control').rglob('*'))
    expected_controls += [folder/name for name in ('first-close-scenario.json','first-close-compilation.json','first-close-prefix-audit.json')]
    expected_controls += list(single_folder.rglob('*'))
    expected_hashes = {p.relative_to(folder).as_posix():REVIEW.digest(p) for p in expected_controls if p.is_file()}
    require(retry['retained_control_hashes'] == expected_hashes, 'complete retained control fingerprint set differs')
    reused = final == first
    if reused: value,final_rows = single,single_rows
    else:
        value,final_rows,audit = verify_ledger(binary,market,folder/'retry',scratch/'retry',deadline)
        require(final == ORIGINAL.obj(folder/'retry/scenario.json'), 'retry ledger plan differs')
        ledgers['retry'] = audit
    retry_audit = RUN.CORE.BOUND.verify_retry(first,final,events,retry,single_rows,final_rows)
    require(retry_audit == ORIGINAL.obj(folder/'retry-prefix-audit.json'), 'retry prefix audit differs')
    by_id = {o['order']['id']:o for o in value['orders']}; close, extra = by_id.get('close'), by_id.get('close-retry')
    metrics = copy.deepcopy(value['metrics'])
    metrics.update(entry_quantity=by_id['entry']['native_final_order']['filled_quantity'],entry_outcome=by_id['entry']['outcome'],
        close_requested_quantity=None if close is None else close['order']['quantity'],
        close_quantity=None if close is None else close['native_final_order']['filled_quantity'],
        close_outcome=None if close is None else close['outcome'],close_decision_status=first_receipt['status'],
        known_position_at_decision=first_receipt['known_position'],retry_decision_status=retry['status'],
        retry_known_position=retry['known_position'],retry_requested_quantity=None if extra is None else extra['order']['quantity'],
        retry_quantity=None if extra is None else extra['native_final_order']['filled_quantity'],retry_outcome=None if extra is None else extra['outcome'])
    with localcontext() as context:
        context.prec = 100
        metrics['total_close_quantity'] = None if close is None else str(sum(
            (Decimal(o['native_final_order']['filled_quantity']) for o in value['orders'] if o['order']['id'] != 'entry'),Decimal(0)))
    expected = dict(r002_policy_version=1,policy_id=CORE.POLICY['experiment_id'],status='verified',actual_execution='unknown',
        exploratory=True,control_reused=first_reused,close_compilation=ORIGINAL.CORE.stamps(first_receipt),
        causal_prefix_audit=first_audit,causal_prefix_verified=True,retry_compilation=ORIGINAL.CORE.stamps(retry),
        retry_prefix_audit=retry_audit,retry_prefix_verified=True,metrics=metrics,orders=value['orders'],
        native_checkpoints=sum(v['checkpoints'] for v in ledgers.values()))
    require(expected == ORIGINAL.obj(folder/'momentum-case.json'), 'retained full R002 case differs from native revalidation')
    explanation = CORE.explain_case(events,feature,final,expected)
    receipt = dict(status='verified',ledgers=ledgers,entry_verified=True,first_prefix=first_audit,retry_prefix=retry_audit,
        full_case_verified=True,cost_identity_verified=explanation['closed_decomposition'] is not None)
    shutil.rmtree(scratch)
    return expected,explanation,receipt


def generate(binary, source, output, assets):
    binary,source,output = binary.resolve(),source.absolute(),output.resolve()
    require(binary.is_file() and os.access(binary,os.X_OK) and binary.stat().st_size <= 128*MIB, 'bounded installed executable required')
    require(not binary.is_relative_to(source.resolve()), 'never execute an evidence-bundle binary; use the installed original executable')
    require(not output.exists() and not output.is_relative_to(source.resolve()), 'diagnostic output must be new and outside original evidence')
    deadline = time.monotonic()+LIMITS['suite_seconds']
    require(REVIEW.digest(assets['protocol']) == PROTOCOL_SHA256, 'diagnostic contract fingerprint differs')
    original,before,expected_source,producer_files = frozen(source,binary,assets,deadline)
    files = dict(producer_files,diagnostic_core=Path(CORE.__file__),diagnostic_local=Path(__file__),
        diagnostic_template=assets['template'],diagnostic_protocol=assets['protocol'],installed_binary=binary)
    code = {key:REVIEW.digest(path) for key,path in files.items()}
    output.parent.mkdir(parents=True,exist_ok=True)
    require(shutil.disk_usage(output.parent).free >= LIMITS['free_reserve_bytes']+LIMITS['operation_allowance_bytes'], 'diagnostic initial free-space reserve insufficient')
    os.umask(0o077); output.mkdir(mode=0o700)
    for name in ('verification','scratch'): (output/name).mkdir()
    REVIEW.save(output/'input-before.json',before)
    shutil.copyfile(assets['protocol'],output/'diagnostic-contract.md')
    cases = [dict(case_id=c['case_id'],child=c['child'],profile=c['profile'],original_status=c['status'],
        status='not_checked',explanation=None) for c in original['cases']]
    report = dict(**CORE.POLICY,created_at_utc=datetime.now(timezone.utc).isoformat(),status='incomplete',origin=original['origin'],
        input_report_sha256=before['momentum-report.json']['sha256'],selected_children=original['selected_children'],
        original_status=original['status'],original_totals=original['totals'],original_screen=original['screen'],
        cases=cases,source_checks=0,ledger_checks=0,cost_identities=0,input_unchanged=False,code_unchanged=False,error=None,
        verification_scope='Retained selected recordings and manual ledgers; copied original quality audit is a historical bound receipt.',
        limits=LIMITS,provenance=dict(installed_binary_sha256=code['installed_binary'],code_hashes=code,diagnostic_contract_sha256=PROTOCOL_SHA256))
    try:
        for row in original['rows']:
            if not row['selected']: continue
            admit(output,deadline); child = row['child']; key = f'run-{child:06d}'
            market,receipt = verify_market(binary,source/'markets'/key,output/'scratch'/key,
                child,expected_source,original['origin'],deadline)
            REVIEW.save(output/'verification'/(key+'.json'),receipt); report['source_checks'] += 1
            require(ORIGINAL.CORE.stamps(market['feature']) == row['feature'] and market['selection']['counts'] == row['selection_counts']
                and ORIGINAL.CORE.stamps(market['label']) == row['prediction_diagnostic'], 'original report feature/count/label differs')
            originals = [c for c in original['cases'] if c['child'] == child]
            diagnostics = [c for c in cases if c['child'] == child]
            if market['feature'] is None:
                require(row['status'] == 'no_signal' and all(c['status'] == 'no_signal' and c['policy'] is None for c in originals), 'no-signal case gained a policy')
                for case in diagnostics: case['status'] = 'verified_no_signal'
            else:
                require(row['status'] == 'completed' and all(c['status'] == 'verified' for c in originals), 'original selected case missing')
                for old,case in zip(originals,diagnostics):
                    admit(output,deadline)
                    value,explanation,receipt = verify_case(binary,market,source/'cases'/case['case_id']/'policy',
                        output/'scratch'/case['case_id'],deadline)
                    require(ORIGINAL.CORE.stamps(RUN.compact(value)) == old['policy']
                        and ORIGINAL.obj(source/'cases'/case['case_id']/'case-result.json') == old, 'original compact case differs')
                    REVIEW.save(output/'verification'/(case['case_id']+'.json'),receipt)
                    report['ledger_checks'] += len(receipt['ledgers']); report['cost_identities'] += receipt['cost_identity_verified']
                    case.update(status='verified',explanation=explanation)
            print(json.dumps(dict(child=child,status='verified',case_slots=len(diagnostics))),flush=True)
        report['status'] = 'completed'
    except ERRORS as error:
        report.update(status='invalid',error=str(error)[:1200])
    try:
        after = inventory(source,deadline); REVIEW.save(output/'input-after.json',after)
        report['input_unchanged'] = before == after
        report['code_unchanged'] = code == {key:REVIEW.digest(path) for key,path in files.items()}
        require(report['input_unchanged'] and report['code_unchanged'], 'original bundle, installed binary or diagnostic code changed')
    except ERRORS as error:
        report.update(status='invalid',error=report['error'] or str(error)[:1200])
    if report['status'] != 'completed':
        for case in cases: case.update(status='unavailable',explanation=None)
    report = ORIGINAL.CORE.stamps(report)
    require(len(QUALITY.encoded(report)) <= 16*MIB and RUN.COST.used_bytes(output) <= LIMITS['output_bytes']-LIMITS['report_reserve_bytes'],
        'diagnostic report reserve exceeded')
    sealed = {p.relative_to(output).as_posix():REVIEW.digest(p) for p in sorted(output.rglob('*')) if p.is_file()}
    REVIEW.save(output/'diagnostic-inventory.json',dict(diagnostic_inventory_version=1,files=sealed))
    report['provenance']['audit_inventory_sha256'] = REVIEW.digest(output/'diagnostic-inventory.json')
    REVIEW.save(output/'momentum-explain-report.json',report)
    with (output/'momentum-explain.html').open('x') as stream:
        stream.write(QUALITY.render(report,QUALITY.read_asset(assets['template']).decode(),QUALITY.read_asset(assets['theme']).decode()))
    return report


def readout(report):
    keys = ('status','diagnostic_id','input_unchanged','code_unchanged','source_checks','ledger_checks','cost_identities','error')
    result = {key:report[key] for key in keys}
    result.update(original_classification=report['original_screen']['classification'],exceptions=[],baseline_costs=[])
    for case in report['cases']:
        e = case['explanation']
        if e is None: continue
        if case['profile'] == 'baseline': result['baseline_costs'].append(dict(case=case['case_id'],outcome=e['outcome'],closed_decomposition=e['closed_decomposition']))
        if e['outcome'] != 'closed_under_assumptions':
            result['exceptions'].append(dict(case=case['case_id'],outcome=e['outcome'],ending_position=e['ending_position_quantity'],
                closed_decomposition=None,window=e['close_window']['status'],
                actual_source_end_ns=e['close_window']['actual_source_end_ns'],
                window_start_ns=e['close_window']['window_start_ns'],window_end_ns=e['close_window']['window_end_ns'],
                first_close=e['first_close_status'],retry=e['retry_status'],
                orders=[{k:o[k] for k in ('id','outcome','explanation','requested_quantity','filled_quantity','nominal_top_capacity',
                    'remaining_shared_capacity','marketable','limit_price','assumed_fill_price','reference_age_ns','native_rejection_detail')} for o in e['orders']]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary','source','output-dir','quality-template','cost-template','momentum-template','theme','original-protocol','policy-spec','protocol','template'):
        parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    assets = {key:getattr(args,key) for key in ('quality_template','cost_template','momentum_template','theme','original_protocol','policy_spec','protocol','template')}
    try: report = generate(args.binary,args.source,args.output_dir,assets)
    except ERRORS as error: parser.exit(2,'R002 diagnostic refused: '+str(error)+'\n')
    print(json.dumps(readout(report),indent=2))
    return 0 if report['status'] == 'completed' else 1


if __name__ == '__main__': raise SystemExit(main())

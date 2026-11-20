#!/usr/bin/env python3
"""Inspect a saved cost probe with fresh source/ledger checks; no new policy run."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import resource
import shutil
import stat
import subprocess
import time

if __package__:
    from . import cost_local as COST, expiry_core as CORE
else:
    import cost_local as COST
    import expiry_core as CORE

REVIEW, QUALITY, EXECUTION = COST.REVIEW, COST.QUALITY, COST.EXECUTION
require = REVIEW.require
MIB = 1024*1024
LIMITS = dict(input_bytes=2048*MIB, output_bytes=2048*MIB, max_files=8192,
    free_reserve_bytes=1024*MIB, report_reserve_bytes=16*MIB,
    source_allowance_bytes=128*MIB, case_allowance_bytes=128*MIB,
    suite_seconds=600, native_seconds=30)


def parse(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: require(False, 'nonfinite JSON number'))


def read(path, limit=4*MIB):
    REVIEW.plain(path)
    require(path.stat().st_size <= limit, 'oversized diagnostic input: '+path.name)
    with path.open('rb') as stream:
        raw = stream.read(limit+1)
    require(len(raw) <= limit, 'diagnostic input grew beyond bound')
    return raw


def obj(path, limit=4*MIB):
    value = parse(read(path, limit))
    require(type(value) is dict, 'JSON object required')
    return value


def lines(path):
    raw = read(path, 32*MIB)
    rows = raw.splitlines(keepends=True)
    require(0 < len(rows) <= 10000 and all(len(row) <= 64*1024 and row.endswith(b'\n') for row in rows),
            'record stream exceeds native bounds or is incomplete')
    result = [parse(row) for row in rows]
    require(all(type(row) is dict for row in result), 'record object required')
    return result


def inventory(root):
    require(root.is_dir() and not root.is_symlink(), 'regular cost-report directory required')
    result, size = {}, 0
    for path in sorted(root.rglob('*')):
        info = path.lstat()
        require(not path.is_symlink(), 'cost artifact symlink refused')
        if stat.S_ISDIR(info.st_mode):
            continue
        require(stat.S_ISREG(info.st_mode), 'cost artifacts must be regular files')
        size += info.st_size
        require(len(result) < LIMITS['max_files'] and size <= LIMITS['input_bytes'] and info.st_size <= 128*MIB,
                'cost artifact inventory exceeds bounds')
        result[path.relative_to(root).as_posix()] = dict(bytes=info.st_size, sha256=REVIEW.digest(path), mtime_ns=info.st_mtime_ns)
    return result


def admit(root, deadline, allowance):
    require(time.monotonic() < deadline, 'diagnostic time budget exhausted')
    reserve = allowance+LIMITS['report_reserve_bytes']
    require(COST.used_bytes(root)+reserve <= LIMITS['output_bytes'], 'diagnostic output budget cannot admit next audit')
    require(shutil.disk_usage(root).free >= LIMITS['free_reserve_bytes']+reserve, 'diagnostic free-space reserve insufficient')


def child_limit():
    resource.setrlimit(resource.RLIMIT_FSIZE, (32*MIB, 32*MIB))


def native(binary, arguments, stdout, stderr, deadline):
    remaining = deadline-time.monotonic()
    require(remaining > 0, 'diagnostic time budget exhausted')
    command = [str(binary), *arguments]
    with stdout.open('xb') as out, stderr.open('xb') as err:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
            check=False, timeout=min(LIMITS['native_seconds'], remaining), preexec_fn=child_limit)
    require(result.returncode == 0, 'native diagnostic audit failed; diagnostics retained')
    return command


def old_code(quality_template, cost_template, theme):
    modules = dict(cost_core=COST.CORE, cost_local=COST, execution=EXECUTION, study=COST.STUDY,
                   signal=COST.CORE.SIGNAL, quality=QUALITY, review=REVIEW)
    return dict(**{name: Path(module.__file__) for name, module in modules.items()},
                quality_template=quality_template, cost_template=cost_template, theme=theme)


def frozen(root, binary, quality_template, cost_template, theme):
    before = inventory(root)
    report = obj(root/'cost-report.json', 2*MIB)
    require(report.get('cost_report_version') == 1 and report.get('status') in ('completed', 'incomplete')
            and all(report.get(key) is True for key in ('source_unchanged', 'quality_unchanged', 'code_unchanged')),
            'preserved version-1 cost report required')
    require(report['live_orders_enabled'] is False and report['portfolio_profit_evaluated'] is False
            and report['full_window_verified'] is False, 'unsupported cost scope')
    require(report['policy'] == dict(policy=COST.CORE.POLICY, profiles=COST.CORE.PROFILES, limits=COST.LIMITS)
            and report['policy_sha256'] == COST.CORE.fingerprint(report['policy'])
            and report['origin'] in ('captured_public_data', 'synthetic_fixture'), 'unsupported cost policy/origin')
    provenance = report['provenance']
    bundle = obj(root/'bundle-inventory.json')
    require(REVIEW.digest(root/'bundle-inventory.json') == provenance['bundle_inventory_sha256'], 'bundle fingerprint differs')
    require(set(before) == set(bundle)|{'cost-report.json', 'cost.html', 'bundle-inventory.json'}, 'unexpected or missing cost artifact')
    for name, expected in bundle.items():
        path = PurePosixPath(name)
        require(name == path.as_posix() and not path.is_absolute() and '..' not in path.parts
                and all(part not in ('', '.') for part in path.parts), 'unsafe bundle path')
        require({key: before[name][key] for key in ('bytes', 'sha256')} == expected, 'cost bundle member changed: '+name)
    require(obj(root/'cost-policy.json') == report['policy']
            and REVIEW.digest(root/'cost-policy.json') == provenance['cost_policy_file_sha256'], 'cost policy receipt differs')
    require(provenance['code_hashes'] == {name: REVIEW.digest(path) for name, path in old_code(quality_template,cost_template,theme).items()},
            'unsupported cost verifier/assets version')
    hashes, manifest, _, source = COST.STUDY.frozen(root/'input-quality',binary,report['origin'],quality_template,theme)
    require(hashes == provenance['input_quality_hashes'] and obj(root/'source-after.json',64*MIB) == source
            and REVIEW.digest(binary) == REVIEW.digest(root/'replay.bin') == provenance['auditor_sha256'] == manifest['audit_binary_sha256'],
            'frozen source, quality or executable differs')
    selected = manifest['candidate_partitions']['development'][:COST.CORE.POLICY['max_children']]
    require(report['selected_children'] == selected and report['totals'] == COST.summarize(report['cases']), 'cost membership/counts differ')
    expected = [(child, profile['id']) for child in selected for profile in COST.CORE.PROFILES]
    require([(case['child'],case['profile']) for case in report['cases']] == expected
            and all(case['id'] == f'run-{case["child"]:06d}--{case["profile"]}' for case in report['cases']), 'cost grid differs')
    return report, before, source


def selected_feature(child, original, observations):
    analyzer = COST.CORE.SIGNAL.Analyzer(child)
    iterator = iter(observations)
    observation = next(iterator, None)
    for source in original:
        current = None
        if observation is not None and observation['sequence'] == source['sequence']:
            current, observation = observation, next(iterator, None)
            require(all(current[key] == source[key] for key in ('sequence','monotonic_ns','local_time_ns','connection_id')),
                    'normalized feature reference differs')
        for kind, value in analyzer.step(source,current):
            if kind == 'feature' and value['monotonic_ns'] >= analyzer.first+COST.CORE.POLICY['warmup_ns'] and value['prediction'] != 'abstain':
                return value
    return None


def fresh_market(binary, root, output, child, source_inventory, origin, deadline):
    replay = root/'control/replay'
    execution = obj(replay/'execution-replay.json')
    COST.match_source(execution, source_inventory, child)
    output.mkdir()
    native(binary, ['paper-market-replay','--input',str(replay/'market/source'),'--output-dir',str(output/'market'),
                   '--origin',origin.replace('_','-'),'--feed','bbo'],output/'market.stdout.json',output/'market.stderr',deadline)
    market = obj(output/'market/market-replay.json')
    require(market == execution['market'] == obj(output/'market.stdout.json'), 'fresh native market report differs')
    require(market['paper']['config']['coin'] == COST.CORE.SIGNAL.POLICY['coin']
            and market['paper']['config']['source']['network'] == COST.CORE.SIGNAL.POLICY['network'],
            'fresh source does not match the declared BTC mainnet policy')
    original = list(QUALITY.source_records(output/'market/source'))
    require(len(original) < 10000 and len(original) == market['source_report']['records'], 'source record count differs')
    frames, links = lines(output/'market/paper-updates.jsonl'),lines(output/'market/market-links.jsonl')
    events = CORE.market_events(original,frames,links)
    native(binary,['replay','--input',str(output/'market/source')],output/'normalized.jsonl',output/'normalized-report.json',deadline)
    require(obj(output/'normalized-report.json') == market['source_report'], 'fresh normalization report differs')
    feature = selected_feature(child,original,lines(output/'normalized.jsonl'))
    return dict(report=market, original=original, frames=frames, links=links, events=events,feature=feature,directory=output/'market')


def verify_saved(binary, root, scenario_path, market, output, origin, deadline):
    output.mkdir()
    replay = root/'replay'
    execution, paper = obj(replay/'execution-replay.json'),obj(replay/'paper-report.json')
    require(execution['market'] == market['report'] and execution['paper'] == paper
            and execution['execution_model_version'] == 1 and execution['mode'] == 'offline_controlled_ioc'
            and execution['scenario_orders_enabled'] is True and execution['strategy_enabled'] is False,
            'saved execution envelope differs')
    for name in ('source-manifest.json','paper-input.jsonl','paper-updates.jsonl','market-links.jsonl','paper-report.json','market-replay.json'):
        require(REVIEW.digest(replay/'market'/name) == REVIEW.digest(market['directory']/name), 'stored market export differs: '+name)
    for entry in execution['market']['source']['files']:
        require(re.fullmatch(r'index\.jsonl|segment-[0-9]{8}\.jsonl',entry['file']) is not None, 'unsafe source filename')
        file = replay/'market/source'/entry['file']
        require(file.stat().st_size == entry['bytes'] and REVIEW.digest(file) == entry['sha256'], 'stored raw source changed')
    raw = read(scenario_path,64*1024)
    require(read(replay/'scenario.json',64*1024) == raw and execution['scenario_sha256'] == hashlib.sha256(raw).hexdigest()
            and EXECUTION.semantic_scenario(execution['scenario']) == EXECUTION.semantic_scenario(parse(raw)), 'saved scenario differs')
    source = paper['config']['source']
    require(paper['paper_model_version'] == 3 and paper['fill_model'] == 'assumed_next_fresh_quote_ioc_v1'
            and source['kind'] == 'recorded_execution' and source['origin'] == origin and source['feed'] == 'bbo'
            and source['recording_sha256'] == market['report']['source']['recording_sha256']
            and source['scenario_sha256'] == execution['scenario_sha256']
            and source['assumptions'] == execution['scenario']['assumptions']
            and paper['config']['fee_rate'] == source['assumptions']['fee_rate'], 'saved source/model differs')
    scenario = execution['scenario']
    expected_config = dict(market['report']['paper']['config'])
    for key in ('starting_collateral','max_abs_position','max_order_notional','max_working_orders','max_loss'):
        expected_config[key] = scenario[key]
    expected_config['fee_rate'] = scenario['assumptions']['fee_rate']
    expected_config['source'] = dict(kind='recorded_execution',label=scenario['label'],origin=origin,
        recording_sha256=market['report']['source']['recording_sha256'],scenario_sha256=execution['scenario_sha256'],
        feed='bbo',network=market['report']['paper']['config']['source']['network'],assumptions=scenario['assumptions'])
    require(EXECUTION.semantic_scenario(paper['config']) == EXECUTION.semantic_scenario(expected_config), 'saved risk/account configuration differs')
    frames, links, trace = [lines(replay/name) for name in ('paper-updates.jsonl','market-links.jsonl','execution-trace.jsonl')]
    inputs = lines(replay/'paper-input.jsonl')
    base_inputs = lines(market['directory']/'paper-input.jsonl')
    require(len(frames) == len(links) == len(trace) == paper['records'] and paper['complete'] and frames[-1]['complete']
            and len(inputs) == len(frames) and all(not frame['complete'] for frame in frames[:-1]), 'saved execution frame count differs')
    for i,(frame,link,step,saved_input) in enumerate(zip(frames,links,trace,inputs),1):
        require(frame['sequence'] == link['paper_sequence'] == step['paper_sequence'] == i and frame['source'] == source
                and frame['paper_model_version'] == 3 and frame['mode'] == 'paper'
                and link['market_sequence'] == step['market_sequence']
                and saved_input['sequence'] == i and saved_input['paper_schema_version'] == 3
                and saved_input['monotonic_ns'] == link['monotonic_ns'] == frame['monotonic_ns'], 'saved execution reference differs')
        if step['phase'] == 'market':
            expected_event = (dict(type='session_started',config=paper['config']) if link['market_sequence']==1
                              else base_inputs[link['market_sequence']-1]['event'])
            require(saved_input['event'] == expected_event, 'derived market input differs from fresh native source')
        elif step['phase'] == 'replay_end':
            require(saved_input['event'] == base_inputs[-1]['event'], 'derived source end differs')
    require([link['market_sequence'] for link,step in zip(links,trace) if step['phase']=='market'] == list(range(1,len(market['original'])+1))
            and links[-1]['generated_end'] and all(not link['generated_end'] for link in links[:-1])
            and trace[-1]['phase'] == 'replay_end' and frames[-1]['account'] == paper['account'] and frames[-1]['risk'] == paper['risk'],
            'saved execution timeline/final state differs')
    require(sorted(execution['pending_order_ids']) == sorted(order['id'] for order in paper['orders'] if order['status']=='pending_new'),
            'saved pending orders differ')
    audit = EXECUTION.verify_costs(execution,frames,links,trace,market['original'])
    require(audit == obj(root/'cost-audit.json'), 'saved cost audit differs')
    REVIEW.save(output/'cost-audit.json',audit)
    native(binary,['paper-replay','--input',str(replay/'paper-input.jsonl')],output/'updates.jsonl',output/'report.json',deadline)
    require(REVIEW.digest(output/'updates.jsonl') == REVIEW.digest(replay/'paper-updates.jsonl') and obj(output/'report.json') == paper,
            'fresh exact native ledger differs')
    return execution,list(zip(frames,links,trace))


def case_review(binary, source, case, market, output, origin, policy_sha, deadline):
    output.mkdir()
    feature = obj(source.parent/f'run-{case["child"]:06d}/feature.json')
    require(feature == market['feature'], 'saved feature differs from fresh native source')
    profile = next(p for p in COST.CORE.PROFILES if p['id']==case['profile'])
    entry = obj(source/'entry-scenario.json')
    require(entry == COST.CORE.entry_scenario(feature,profile['assumptions']), 'entry differs from fixed policy')
    control, control_rows = verify_saved(binary,source/'control',source/'entry-scenario.json',market,output/'control',origin,deadline)
    decision = COST.CORE.close_decision(feature,zip(market['frames'],market['links']))
    plan,receipt = COST.CORE.compile_close(entry,decision,control_rows)
    receipt.update(control_scenario_sha256=REVIEW.digest(source/'entry-scenario.json'),
        control_updates_sha256=REVIEW.digest(source/'control/replay/paper-updates.jsonl'),policy_sha256=policy_sha)
    require(receipt == case['causal_prefix'] == obj(source/'causal-prefix.json')
            and plan == obj(source/'compiled-scenario.json') and case['policy_sha256'] == policy_sha
            and case['compiled_scenario_sha256'] == REVIEW.digest(source/'compiled-scenario.json'), 'causal compiler receipt differs')
    reused = plan == entry
    require(case['control_reused'] == reused and case['final_replay'] == ('control' if reused else 'compiled'), 'final replay selection differs')
    execution,rows = (control,control_rows) if reused else verify_saved(binary,source/'compiled',source/'compiled-scenario.json',market,output/'compiled',origin,deadline)
    require(COST.CORE.verify_prefix(control_rows,rows,decision) == receipt['prefix_sha256']
            and COST.CORE.metrics(execution,rows,receipt) == case['metrics'] and case['prefix_verified'] is True,
            'saved prefix or case metrics differ')
    final_root = source/('control' if reused else 'compiled')
    require(case['recording_sha256'] == execution['market']['source']['recording_sha256']
            and case['cost_audit'] == obj(final_root/'cost-audit.json')
            and obj(source/'case-result.json') == {k:v for k,v in case.items() if k not in ('id','child','profile','reason')},
            'case provenance/result differs')
    orders = CORE.diagnose(execution,rows,market['events'])
    result = dict(case_id=case['id'],child=case['child'],profile=case['profile'],status='verified',
        historical_outcome=case['metrics']['outcome'],orders=orders,
        recording_sha256=execution['market']['source']['recording_sha256'],reason=None,
        close_decision_status=receipt['status'],close_decision=CORE.stamps(decision),
        ending_position_quantity=execution['paper']['account']['position_quantity'],
        ending_pending_order_ids=execution['pending_order_ids'],profit_reestimated=False)
    REVIEW.save(output/'diagnostic.json',result)
    return result


def summary(cases):
    result = dict(cases=len(cases),verified=0,unavailable=0,not_run=0,orders=0,classifications={})
    for case in cases:
        result[case['status']] += 1
        for order in case['orders']:
            result['orders'] += 1
            key = order['classification']
            result['classifications'][key] = result['classifications'].get(key,0)+1
    return result


def milliseconds(ns):
    if ns is None:
        return None
    value = int(ns)
    whole,fraction = divmod(abs(value),1_000_000)
    decimal = str(fraction).zfill(6).rstrip('0')
    return ('-' if value < 0 else '')+str(whole)+('.'+decimal if decimal else '')


def readout(report):
    brief = {key:report[key] for key in ('status','input_unchanged','code_unchanged','totals','error')}
    brief['expired_orders'] = [dict(case=case['case_id'],order=order['order_id'],classification=order['classification'],
        request_sequence=order['request_sequence'],arrival_after_request_ms=milliseconds(order['arrival_offset_ns']),
        exclusive_expiry_after_request_ms=milliseconds(order['expiry_offset_ns']),
        first_native_quote_after_arrival_ms=milliseconds((order['first_native_quote_at_or_after_arrival'] or {}).get('offset_ns')),
        observed_expiry_after_request_ms=milliseconds((order['observed_resolution'] or {}).get('offset_ns')),
        usable_quotes_inside_window=order['native_opportunities_in_window'],
        bbo_messages_inside_window=order['selected_bbo_messages_in_window'],component_cause='unknown')
        for case in report['cases'] for order in case['orders'] if order['classification'].startswith('expired')]
    return brief


def generate(binary, source, output, quality_template, cost_template, template, theme):
    binary,source,output = binary.resolve(),source.absolute(),output.resolve()
    require(binary.is_file() and os.access(binary,os.X_OK) and binary.stat().st_size <= 128*MIB, 'bounded installed executable required')
    require(not output.is_relative_to(source.resolve()), 'diagnostic output must be outside original cost evidence')
    original,before,source_inventory = frozen(source,binary,quality_template,cost_template,theme)
    assets = dict(template=QUALITY.read_asset(template),theme=QUALITY.read_asset(theme))
    code = dict(**old_code(quality_template,cost_template,theme),expiry_core=Path(CORE.__file__),expiry_local=Path(__file__),template=template)
    code_hashes = {name:REVIEW.digest(path) for name,path in code.items()}
    binary_sha = REVIEW.digest(binary)
    output.parent.mkdir(parents=True,exist_ok=True)
    require(shutil.disk_usage(output.parent).free >= LIMITS['free_reserve_bytes']+LIMITS['source_allowance_bytes'], 'insufficient diagnostic free space')
    os.umask(0o077)
    output.mkdir(mode=0o700)
    deadline = time.monotonic()+LIMITS['suite_seconds']
    for name in ('cost-report.json','cost-policy.json','bundle-inventory.json'):
        shutil.copyfile(source/name,output/('input-'+name))
    REVIEW.save(output/'input-before.json',before)
    (output/'markets').mkdir()
    (output/'cases').mkdir()
    cases = [dict(case_id=c['id'],child=c['child'],profile=c['profile'],status='not_run',orders=[],
                  historical_outcome=(c.get('metrics') or {}).get('outcome'),reason='Not admitted.') for c in original['cases']]
    report = dict(expiry_report_version=1,created_at_utc=datetime.now(timezone.utc).isoformat(),
        status='incomplete',origin=original['origin'],policy_sha256=original['policy_sha256'],limits=LIMITS,
        historical_totals=original['totals'],selected_children=original['selected_children'],cases=cases,
        totals=None,input_unchanged=False,code_unchanged=False,orders_generated=False,profit_reestimated=False,
        full_window_verified=False,error=None)
    markets, market_errors = {}, {}
    for old,row in zip(original['cases'],cases):
        if old['status'] != 'verified':
            row.update(status='unavailable',reason='Original cost case was '+old['status']+'.')
            continue
        if old['child'] not in markets and old['child'] not in market_errors:
            try:
                admit(output,deadline,LIMITS['source_allowance_bytes'])
            except (ValueError,OSError) as error:
                row['reason'] = str(error)
                continue
            try:
                markets[old['child']] = fresh_market(binary,source/old['id'],output/'markets'/f'run-{old["child"]:06d}',
                    old['child'],source_inventory,original['origin'],deadline)
            except (ValueError,OSError,KeyError,TypeError,IndexError,subprocess.TimeoutExpired) as error:
                market_errors[old['child']] = str(error)
        if old['child'] in market_errors:
            row.update(status='unavailable',reason=market_errors[old['child']])
            continue
        try:
            admit(output,deadline,LIMITS['case_allowance_bytes'])
        except (ValueError,OSError,KeyError,TypeError,subprocess.TimeoutExpired) as error:
            row['reason'] = str(error)
            continue
        try:
            row.update(case_review(binary,source/old['id'],old,markets[old['child']],output/'cases'/old['id'],
                                   original['origin'],original['policy_sha256'],deadline))
        except (ValueError,OSError,KeyError,TypeError,IndexError,subprocess.TimeoutExpired) as error:
            row.update(status='unavailable',reason=str(error))
    try:
        after = inventory(source)
        REVIEW.save(output/'input-after.json',after)
        report['input_unchanged'] = before == after
        report['code_unchanged'] = code_hashes == {name:REVIEW.digest(path) for name,path in code.items()} and REVIEW.digest(binary) == binary_sha
    except (ValueError,OSError) as error:
        report['error'] = str(error)
    if not report['input_unchanged'] or not report['code_unchanged']:
        report.update(status='source_changed',error='cost evidence, executable or diagnostic helpers changed')
        for row in cases:
            row.update(status='unavailable',orders=[],reason='Evidence changed; diagnostics not admitted.')
    elif all(row['status']=='verified' for row in cases):
        report['status'] = 'completed'
    report['totals'] = summary(cases)
    report['provenance'] = dict(input_report_sha256=before['cost-report.json']['sha256'],
        input_bundle_sha256=before['bundle-inventory.json']['sha256'],input_inventory_sha256=REVIEW.digest(output/'input-before.json'),
        binary_sha256=binary_sha,code_hashes=code_hashes,
        audit_hashes={str(p.relative_to(output)):REVIEW.digest(p) for p in sorted(output.rglob('*')) if p.is_file()})
    require(COST.used_bytes(output) <= LIMITS['output_bytes']-LIMITS['report_reserve_bytes'], 'diagnostic output exceeded reserve')
    require(len(QUALITY.encoded(report)) <= 4*MIB, 'diagnostic report exceeds bound')
    REVIEW.save(output/'expiry-report.json',report)
    html = QUALITY.render(report,assets['template'].decode(),assets['theme'].decode())
    with (output/'expiry.html').open('x') as stream:
        stream.write(html)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary','input','output-dir','quality-template','cost-template','template','theme'):
        parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    try:
        result = generate(args.binary,args.input,args.output_dir,args.quality_template,args.cost_template,args.template,args.theme)
    except (ValueError,OSError,KeyError,TypeError) as error:
        parser.exit(2,'Expiry diagnostic preflight failed: '+str(error)+'\n')
    print(json.dumps(readout(result),indent=2))
    print('Expiry view: '+str(args.output_dir/'expiry.html'))
    return 0 if result['status']=='completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())

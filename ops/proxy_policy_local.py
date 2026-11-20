#!/usr/bin/env python3
"""Run one causal proxy entry/close cycle per preserved child/profile, offline."""
import argparse
import copy
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

if __package__:
    from . import proxy_policy_core as CORE,model_compare_local as MODEL
else:
    import proxy_policy_core as CORE
    import model_compare_local as MODEL

ORIGINAL=MODEL.ORIGINAL
REVIEW,QUALITY=ORIGINAL.REVIEW,ORIGINAL.QUALITY
require=REVIEW.require
MIB=1024*1024
LIMITS=dict(output_bytes=2048*MIB,free_reserve_bytes=1024*MIB,report_reserve_bytes=16*MIB,
    source_allowance_bytes=128*MIB,case_allowance_bytes=256*MIB,replay_allowance_bytes=128*MIB,
    suite_seconds=900,native_seconds=30,max_cases=24,max_requests_per_case=2)


def admit(output,deadline,allowance):
    require(time.monotonic()<deadline,'causal policy time budget exhausted')
    reserve=allowance+LIMITS['report_reserve_bytes']
    require(ORIGINAL.COST.used_bytes(output)+reserve<=LIMITS['output_bytes'],'policy output budget cannot admit operation')
    require(shutil.disk_usage(output).free>=LIMITS['free_reserve_bytes']+reserve,'policy free-space reserve insufficient')


def ledger_rows(folder):
    return tuple(ORIGINAL.lines(folder/name) for name in ('paper-input.jsonl','comparison-links.jsonl','paper-updates.jsonl'))


def run_case(binary,market,entry,feature,output,deadline,budget_root=None):
    output.mkdir()
    REVIEW.save(output/'entry-scenario.json',entry)
    if budget_root is not None:admit(budget_root,deadline,LIMITS['case_allowance_bytes'])
    control=MODEL.proxy(binary,market,entry,output/'control',deadline,budget_root)
    decision=CORE.FROZEN.close_decision(feature,zip(market['frames'],market['links']))
    control_rows=ledger_rows(output/'control')
    plan,receipt=CORE.compile_close(entry,decision,*control_rows)
    receipt.update(control_scenario_sha256=REVIEW.digest(output/'entry-scenario.json'),
        control_inputs_sha256=REVIEW.digest(output/'control/paper-input.jsonl'),
        control_updates_sha256=REVIEW.digest(output/'control/paper-updates.jsonl'))
    REVIEW.save(output/'compiled-scenario.json',plan)
    REVIEW.save(output/'close-compilation.json',receipt)
    reused=plan==entry
    if reused:
        final=control;final_rows=control_rows
    else:
        if budget_root is not None:admit(budget_root,deadline,LIMITS['replay_allowance_bytes'])
        final=MODEL.proxy(binary,market,plan,output/'final',deadline,budget_root)
        final_rows=ledger_rows(output/'final')
    prefix=CORE.verify_close(entry,plan,decision,receipt,control_rows,final_rows)
    REVIEW.save(output/'causal-prefix-audit.json',prefix)
    entry_result=next(d for d in final['orders'] if d['order']['id']=='entry')
    close_result=next((d for d in final['orders'] if d['order']['id']=='close'),None)
    metrics=copy.deepcopy(final['metrics'])
    metrics.update(entry_outcome=entry_result['outcome'],entry_quantity=entry_result['native_final_order']['filled_quantity'],
        close_decision_status=receipt['status'],known_position_at_decision=receipt['known_position'],
        close_requested_quantity=None if close_result is None else close_result['order']['quantity'],
        close_quantity=None if close_result is None else close_result['native_final_order']['filled_quantity'],
        close_outcome=None if close_result is None else close_result['outcome'])
    result=dict(causal_proxy_policy_version=1,policy_id=CORE.POLICY['policy_id'],status='verified',
        actual_execution='unknown',exploratory=True,control_reused=reused,final_replay='control' if reused else 'final',
        close_compilation=ORIGINAL.CORE.stamps(receipt),causal_prefix_audit=prefix,causal_prefix_verified=True,
        metrics=metrics,orders=final['orders'],control_metrics=control['metrics'],
        native_checkpoints=control['native_checkpoints']+(0 if reused else final['native_checkpoints']))
    REVIEW.save(output/'policy-case.json',result)
    return result


def code_files(quality_template,cost_template,template,theme):
    return dict(**ORIGINAL.old_code(quality_template,cost_template,theme),
        expiry_core=Path(ORIGINAL.CORE.__file__),expiry_local=Path(ORIGINAL.__file__),
        comparison_core=Path(MODEL.CORE.__file__),comparison_verifier=Path(MODEL.VERIFY.__file__),comparison_local=Path(MODEL.__file__),
        policy_core=Path(CORE.__file__),policy_local=Path(__file__),policy_template=template)


def totals(cases):
    result=dict(cases=len(cases),verified=0,unavailable=0,not_run=0,entry_requests=0,close_requests=0,
        actual_executions_known=0,outcomes={},close_decisions={})
    for row in cases:
        result[row['status']]+=1
        if row['status']!='verified':continue
        value=row['policy'];metrics=value['metrics']
        result['entry_requests']+=1;result['close_requests']+=metrics['close_requested_quantity'] is not None
        for key,label in (('outcomes',metrics['outcome']),('close_decisions',metrics['close_decision_status'])):
            result[key][label]=result[key].get(label,0)+1
    return result


def generate(binary,source,output,quality_template,cost_template,template,theme):
    binary,source,output=binary.resolve(),source.absolute(),output.resolve()
    require(not output.exists() and not output.is_relative_to(source.resolve()),'policy output must be new and outside original evidence')
    original,before,source_inventory=ORIGINAL.frozen(source,binary,quality_template,cost_template,theme)
    require(len(original['cases'])<=LIMITS['max_cases'],'frozen policy cohort exceeds bound')
    assets=dict(template=QUALITY.read_asset(template),theme=QUALITY.read_asset(theme))
    files=code_files(quality_template,cost_template,template,theme)
    hashes={name:REVIEW.digest(path) for name,path in files.items()};binary_sha=REVIEW.digest(binary)
    output.parent.mkdir(parents=True,exist_ok=True)
    require(shutil.disk_usage(output.parent).free>=LIMITS['free_reserve_bytes']+LIMITS['case_allowance_bytes'],'policy free-space reserve insufficient')
    os.umask(0o077);output.mkdir(mode=0o700)
    for name in ('markets','cases'):(output/name).mkdir()
    REVIEW.save(output/'input-before.json',before)
    shutil.copyfile(source/'cost-report.json',output/'input-cost-report.json')
    REVIEW.save(output/'policy-specification.json',dict(policy=CORE.POLICY,limits=LIMITS,
        original_policy=CORE.FROZEN.POLICY,profiles=CORE.FROZEN.PROFILES,proxy_policy=MODEL.CORE.POLICY))
    cases=[dict(case_id=c['id'],child=c['child'],profile=c['profile'],status='not_run',reason='Not admitted.',
        original_outcome=(c.get('metrics') or {}).get('outcome'),policy=None) for c in original['cases']]
    report=dict(policy_report_version=1,created_at_utc=datetime.now(timezone.utc).isoformat(),
        policy=CORE.POLICY,limits=LIMITS,status='incomplete',origin=original['origin'],selected_children=original['selected_children'],
        cases=cases,totals=None,input_unchanged=False,code_unchanged=False,actual_execution_known=False,
        live_orders_enabled=False,portfolio_profit_evaluated=False,historical_outcomes_changed=False,
        exploratory=True,full_window_verified=False,error=None)
    deadline=time.monotonic()+LIMITS['suite_seconds'];markets={};market_errors={}
    for old,row in zip(original['cases'],cases):
        if old['status']!='verified':
            row.update(status='unavailable',reason='Original case was '+old['status']);continue
        if old['child'] not in markets and old['child'] not in market_errors:
            try:admit(output,deadline,LIMITS['source_allowance_bytes'])
            except (ValueError,OSError) as error:
                row['reason']=str(error);continue
            try:
                markets[old['child']]=ORIGINAL.fresh_market(binary,source/old['id'],output/'markets'/f'run-{old["child"]:06d}',
                    old['child'],source_inventory,original['origin'],deadline)
            except (ValueError,OSError,KeyError,TypeError,IndexError,subprocess.TimeoutExpired) as error:
                market_errors[old['child']]=str(error)
        if old['child'] in market_errors:
            row.update(status='unavailable',reason=market_errors[old['child']]);continue
        try:admit(output,deadline,LIMITS['case_allowance_bytes'])
        except (ValueError,OSError) as error:
            row['reason']=str(error);continue
        folder=output/'cases'/old['id'];folder.mkdir()
        try:
            ORIGINAL.case_review(binary,source/old['id'],old,markets[old['child']],folder/'historical',
                original['origin'],original['policy_sha256'],deadline)
            entry=ORIGINAL.obj(source/old['id']/'entry-scenario.json')
            feature=markets[old['child']]['feature']
            profile=next(p for p in CORE.FROZEN.PROFILES if p['id']==old['profile'])
            require(entry==CORE.FROZEN.entry_scenario(feature,profile['assumptions']),'original entry differs from unchanged signal/policy')
            value=run_case(binary,markets[old['child']],entry,feature,folder/'policy',deadline,output)
            row.update(status='verified',reason=None,original_entry_sha256=REVIEW.digest(source/old['id']/'entry-scenario.json'),policy=value)
            REVIEW.save(folder/'case-result.json',row)
        except (ValueError,OSError,KeyError,TypeError,IndexError,subprocess.TimeoutExpired) as error:
            row.update(status='unavailable',reason=str(error),policy=None)
    try:
        after=ORIGINAL.inventory(source);REVIEW.save(output/'input-after.json',after)
        report['input_unchanged']=before==after
        report['code_unchanged']=hashes=={name:REVIEW.digest(path) for name,path in files.items()} and binary_sha==REVIEW.digest(binary)
    except (ValueError,OSError) as error:report['error']=str(error)
    if not report['input_unchanged'] or not report['code_unchanged']:
        report.update(status='source_changed',error='original evidence, native binary or policy producer changed')
        for row in cases:row.update(status='unavailable',reason='Changed evidence; policy metrics not admitted.',policy=None)
    elif all(row['status']=='verified' for row in cases):report['status']='completed'
    report['totals']=totals(cases)
    report['provenance']=dict(input_report_sha256=before['cost-report.json']['sha256'],binary_sha256=binary_sha,code_hashes=hashes,
        audit_hashes={p.relative_to(output).as_posix():REVIEW.digest(p) for p in sorted(output.rglob('*')) if p.is_file()})
    require(ORIGINAL.COST.used_bytes(output)<=LIMITS['output_bytes']-LIMITS['report_reserve_bytes'],'policy output exceeded report reserve')
    require(len(QUALITY.encoded(report))<=4*MIB,'policy report exceeds bound')
    REVIEW.save(output/'policy-report.json',report)
    with (output/'policy.html').open('x') as stream:
        stream.write(QUALITY.render(report,assets['template'].decode(),assets['theme'].decode()))
    return report


def readout(report):
    result={key:report[key] for key in ('status','input_unchanged','code_unchanged','totals','error')}
    result.update(policy_id=report['policy']['policy_id'],actual_execution='unknown',exploratory=True,cases=[])
    for row in report['cases']:
        value=dict(case=row['case_id'],status=row['status'],reason=row['reason'])
        if row['status']=='verified':
            policy=row['policy'];metrics=policy['metrics']
            value.update(outcome=metrics['outcome'],entry_quantity=metrics['entry_quantity'],
                close_decision=metrics['close_decision_status'],known_position=metrics['known_position_at_decision'],
                close_requested_quantity=metrics['close_requested_quantity'],close_quantity=metrics['close_quantity'],
                close_outcome=metrics['close_outcome'],conditional_closed_pnl=metrics['conditional_closed_pnl'],fees=metrics['fees'],
                ending_position=metrics['ending_position_quantity'],pending_orders=metrics['pending_order_ids'],
                causal_prefix_verified=policy['causal_prefix_verified'],orders=[dict(id=d['order']['id'],outcome=d['outcome'],
                    requested_quantity=d['order']['quantity'],filled_quantity=d['native_final_order']['filled_quantity'],
                    assumed_fill_price=d.get('assumed_fill_price'),assumed_fee=d.get('assumed_fee'),
                    reference_age_ms=ORIGINAL.milliseconds(d.get('reference_age_ns'))) for d in policy['orders']])
        result['cases'].append(value)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('binary','input','output-dir','quality-template','cost-template','template','theme'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    try:report=generate(args.binary,args.input,args.output_dir,args.quality_template,args.cost_template,args.template,args.theme)
    except (ValueError,OSError,KeyError,TypeError) as error:parser.exit(2,'Causal policy refused: '+str(error)+'\n')
    print(json.dumps(readout(report),indent=2))
    return 0 if report['status']=='completed' else 1


if __name__=='__main__':raise SystemExit(main())

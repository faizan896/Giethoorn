#!/usr/bin/env python3
"""Compare a preserved cost scenario with a separately labelled arrival-book proxy."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

if __package__:
    from . import model_compare_core as CORE,model_compare_verify as VERIFY,expiry_local as ORIGINAL
else:
    import model_compare_core as CORE
    import model_compare_verify as VERIFY
    import expiry_local as ORIGINAL

REVIEW,QUALITY=ORIGINAL.REVIEW,ORIGINAL.QUALITY
require=REVIEW.require
MIB=1024*1024
LIMITS=dict(output_bytes=2048*MIB,free_reserve_bytes=1024*MIB,report_reserve_bytes=16*MIB,
    source_allowance_bytes=128*MIB,case_allowance_bytes=256*MIB,checkpoint_allowance_bytes=64*MIB,
    suite_seconds=900,max_checkpoints=193,native_seconds=30)


def admit(output,deadline,allowance):
    require(time.monotonic()<deadline,'comparison time budget exhausted')
    reserve=allowance+LIMITS['report_reserve_bytes']
    require(ORIGINAL.COST.used_bytes(output)+reserve<=LIMITS['output_bytes'],'comparison output budget cannot admit operation')
    require(shutil.disk_usage(output).free>=LIMITS['free_reserve_bytes']+reserve,'comparison free-space reserve insufficient')


def stream_info(path):
    digest=hashlib.sha256();size=count=0;last=None
    with path.open('rb') as stream:
        for line in stream:
            require(len(line)<=65536 and line.endswith(b'\n'),'native comparison stream exceeds line bound')
            digest.update(line);size+=len(line);count+=1;last=ORIGINAL.parse(line)
            require(count<=10000 and size<=32*MIB,'native comparison stream exceeds bound')
    return dict(bytes=size,records=count,sha256=digest.hexdigest()),last


def verify_prefixes(path,receipts,key):
    digest=hashlib.sha256();size=index=0;by_count={r['records']:r[key] for r in receipts}
    with path.open('rb') as stream:
        for index,line in enumerate(stream,1):
            digest.update(line);size+=len(line)
            if index in by_count:
                expected=by_count[index]
                require(digest.hexdigest()==expected['sha256'] and size==expected['bytes'],'final native stream differs from a decision prefix')
    require(index==max(by_count),'final comparison prefix count differs')


def proxy(binary,market,scenario,output,deadline,budget_root=None):
    output.mkdir();(output/'checkpoints').mkdir()
    REVIEW.save(output/'scenario.json',scenario)
    REVIEW.save(output/'proxy-policy.json',CORE.POLICY)
    base=ORIGINAL.lines(market['directory']/'paper-input.jsonl')
    compiler=CORE.Compiler(market['events'],base,scenario)
    engine=compiler.run();feedback=None;receipts=[];input_hash=hashlib.sha256();input_bytes=0
    records=[];links=[]
    try:
        with (output/'paper-input.jsonl').open('xb') as inputs,(output/'comparison-links.jsonl').open('xb') as mapping:
            while True:
                try:batch=next(engine) if feedback is None else engine.send(feedback)
                except StopIteration as done:
                    decisions=done.value;break
                require(batch and len(receipts)<LIMITS['max_checkpoints'],'bounded nonempty native decision checkpoint required')
                for row in batch:
                    record,link=row['record'],row['link']
                    raw=QUALITY.encoded(record)+b'\n';input_bytes+=len(raw)
                    require(len(raw)<=65536 and input_bytes<=32*MIB,'manual paper input exceeds bound')
                    inputs.write(raw);input_hash.update(raw);mapping.write(QUALITY.encoded(link)+b'\n')
                    records.append(record);links.append(link)
                inputs.flush();os.fsync(inputs.fileno());mapping.flush();os.fsync(mapping.fileno())
                if budget_root is not None:admit(budget_root,deadline,LIMITS['checkpoint_allowance_bytes'])
                prefix=f'{len(receipts)+1:04d}'
                complete=records[-1]['event']['type']=='session_ended'
                stdout=output/('paper-updates.jsonl' if complete else f'checkpoints/{prefix}.updates.tmp')
                stderr=output/('paper-report.json' if complete else f'checkpoints/{prefix}.report.json')
                arguments=['paper-replay','--input',str(output/'paper-input.jsonl')]
                if not complete:arguments.append('--allow-incomplete')
                ORIGINAL.native(binary,arguments,stdout,stderr,deadline)
                feedback=ORIGINAL.obj(stderr)
                info,last=stream_info(stdout)
                require(info['records']==feedback['records']==len(records) and last is not None
                    and last['account']==feedback['account'] and last['risk']==feedback['risk']
                    and feedback['complete']==complete,'native comparison checkpoint differs')
                receipt=dict(records=len(records),input=dict(bytes=input_bytes,sha256=input_hash.hexdigest()),updates=info,
                    native_report=stderr.relative_to(output).as_posix(),native_report_sha256=REVIEW.digest(stderr))
                REVIEW.save(output/f'checkpoints/{prefix}.receipt.json',receipt);receipts.append(receipt)
                if not complete:stdout.unlink()  # Final exact stream must reproduce the retained prefix hash.
    finally:
        engine.close()
    verify_prefixes(output/'paper-input.jsonl',receipts,'input')
    verify_prefixes(output/'paper-updates.jsonl',receipts,'updates')
    frames=ORIGINAL.lines(output/'paper-updates.jsonl');report=ORIGINAL.obj(output/'paper-report.json')
    verified=VERIFY.verify(market['events'],base,scenario,records,links,frames,report,decisions)
    REVIEW.save(output/'decisions.json',dict(proxy_model_version=1,decisions=decisions))
    REVIEW.save(output/'cost-audit.json',verified)
    return dict(model=CORE.POLICY['proxy_model'],ledger_kind='manual_simulation',actual_execution='unknown',
        native_checkpoints=len(receipts),prefixes_verified=True,metrics=verified,orders=decisions)


def code_files(quality_template,cost_template,template,theme):
    return dict(**ORIGINAL.old_code(quality_template,cost_template,theme),
        expiry_core=Path(ORIGINAL.CORE.__file__),expiry_local=Path(ORIGINAL.__file__),
        comparison_core=Path(CORE.__file__),comparison_verifier=Path(VERIFY.__file__),
        comparison_local=Path(__file__),comparison_template=template)


def totals(cases):
    result=dict(cases=len(cases),verified=0,unavailable=0,not_run=0,orders=0,reference_eligible=0,
                actual_executions_known=0,proxy_outcomes={},historical_outcomes={})
    for row in cases:
        result[row['status']]+=1
        if row['status']!='verified':continue
        result['orders']+=len(row['proxy']['orders'])
        result['reference_eligible']+=sum(o['reference_eligible'] is True for o in row['proxy']['orders'])
        for key,value in (('proxy_outcomes',row['proxy']['metrics']['outcome']),('historical_outcomes',row['historical']['metrics']['outcome'])):
            result[key][value]=result[key].get(value,0)+1
    return result


def generate(binary,source,output,quality_template,cost_template,template,theme):
    binary,source,output=binary.resolve(),source.absolute(),output.resolve()
    require(not output.exists() and not output.is_relative_to(source.resolve()),'comparison output must be new and outside original cost evidence')
    original,before,source_inventory=ORIGINAL.frozen(source,binary,quality_template,cost_template,theme)
    assets=dict(template=QUALITY.read_asset(template),theme=QUALITY.read_asset(theme))
    files=code_files(quality_template,cost_template,template,theme)
    hashes={name:REVIEW.digest(path) for name,path in files.items()};binary_sha=REVIEW.digest(binary)
    output.parent.mkdir(parents=True,exist_ok=True)
    require(shutil.disk_usage(output.parent).free>=LIMITS['free_reserve_bytes']+LIMITS['case_allowance_bytes'],'comparison free-space reserve insufficient')
    os.umask(0o077);output.mkdir(mode=0o700)
    for name in ('markets','cases'):(output/name).mkdir()
    REVIEW.save(output/'input-before.json',before)
    shutil.copyfile(source/'cost-report.json',output/'input-cost-report.json')
    REVIEW.save(output/'comparison-policy.json',dict(policy=CORE.POLICY,limits=LIMITS))
    cases=[dict(case_id=c['id'],child=c['child'],profile=c['profile'],status='not_run',reason='Not admitted.',
        historical=None,proxy=None) for c in original['cases']]
    report=dict(comparison_report_version=1,created_at_utc=datetime.now(timezone.utc).isoformat(),
        status='incomplete',origin=original['origin'],selected_children=original['selected_children'],
        policy=CORE.POLICY,limits=LIMITS,cases=cases,totals=None,input_unchanged=False,code_unchanged=False,
        actual_execution_known=False,alternative_strategy_evaluated=False,historical_outcomes_changed=False,
        full_window_verified=False,error=None)
    deadline=time.monotonic()+LIMITS['suite_seconds'];markets={};market_errors={}
    for old,row in zip(original['cases'],cases):
        if old['status']!='verified':
            row.update(status='unavailable',reason='Original case was '+old['status']);continue
        if old['child'] not in markets and old['child'] not in market_errors:
            try:
                admit(output,deadline,LIMITS['source_allowance_bytes'])
            except (ValueError,OSError) as error:
                row['reason']=str(error);continue
            try:
                markets[old['child']]=ORIGINAL.fresh_market(binary,source/old['id'],output/'markets'/f'run-{old["child"]:06d}',
                    old['child'],source_inventory,original['origin'],deadline)
            except (ValueError,OSError,KeyError,TypeError,IndexError,subprocess.TimeoutExpired) as error:
                market_errors[old['child']]=str(error)
        if old['child'] in market_errors:
            row.update(status='unavailable',reason=market_errors[old['child']]);continue
        try:
            admit(output,deadline,LIMITS['case_allowance_bytes'])
        except (ValueError,OSError) as error:
            row['reason']=str(error);continue
        folder=output/'cases'/old['id'];folder.mkdir()
        try:
            historical=ORIGINAL.case_review(binary,source/old['id'],old,markets[old['child']],folder/'historical',
                original['origin'],original['policy_sha256'],deadline)
            scenario=ORIGINAL.obj(source/old['id']/'compiled-scenario.json')
            alternative=proxy(binary,markets[old['child']],scenario,folder/'proxy',deadline,output)
            row.update(status='verified',reason=None,scenario_sha256=REVIEW.digest(source/old['id']/'compiled-scenario.json'),
                historical=dict(metrics=old['metrics'],diagnostic=historical),proxy=alternative)
            REVIEW.save(folder/'comparison.json',row)
        except (ValueError,OSError,KeyError,TypeError,IndexError,subprocess.TimeoutExpired) as error:
            row.update(status='unavailable',reason=str(error),historical=None,proxy=None)
    try:
        after=ORIGINAL.inventory(source);REVIEW.save(output/'input-after.json',after)
        report['input_unchanged']=before==after
        report['code_unchanged']=hashes=={name:REVIEW.digest(path) for name,path in files.items()} and binary_sha==REVIEW.digest(binary)
    except (ValueError,OSError) as error:report['error']=str(error)
    if not report['input_unchanged'] or not report['code_unchanged']:
        report.update(status='source_changed',error='original cost evidence, binary or comparison assets changed')
        for row in cases:row.update(status='unavailable',historical=None,proxy=None,reason='Changed evidence; comparison not admitted.')
    elif all(row['status']=='verified' for row in cases):report['status']='completed'
    report['totals']=totals(cases)
    report['provenance']=dict(input_report_sha256=before['cost-report.json']['sha256'],binary_sha256=binary_sha,code_hashes=hashes,
        audit_hashes={p.relative_to(output).as_posix():REVIEW.digest(p) for p in sorted(output.rglob('*')) if p.is_file()})
    require(ORIGINAL.COST.used_bytes(output)<=LIMITS['output_bytes']-LIMITS['report_reserve_bytes'],'comparison output exceeded report reservation')
    require(len(QUALITY.encoded(report))<=4*MIB,'comparison report exceeds bound')
    REVIEW.save(output/'comparison-report.json',report)
    with (output/'comparison.html').open('x') as stream:
        stream.write(QUALITY.render(report,assets['template'].decode(),assets['theme'].decode()))
    return report


def readout(report):
    result={key:report[key] for key in ('status','input_unchanged','code_unchanged','totals','error')}
    result.update(actual_execution='unknown',fixed_original_requests=True,alternative_strategy_evaluated=False,cases=[])
    for row in report['cases']:
        value=dict(case=row['case_id'],status=row['status'],reason=row['reason'])
        if row['status']=='verified':
            old=row['historical']['metrics'];new=row['proxy']['metrics']
            value.update(historical_outcome=old['outcome'],historical_closed_pnl=old['closed_case_net_pnl'],
                proxy_outcome=new['outcome'],proxy_conditional_closed_pnl=new['conditional_closed_pnl'],
                proxy_fees=new['fees'],proxy_position=new['ending_position_quantity'],proxy_pending=new['pending_order_ids'],
                orders=[dict(id=d['order']['id'],outcome=d['outcome'],reference_eligible=d['reference_eligible'],
                    reference_age_ms=ORIGINAL.milliseconds(d.get('reference_age_ns')),limit_price=d['order']['limit_price'],
                    assumed_fill_price=d.get('assumed_fill_price'),assumed_fill_quantity=d.get('assumed_fill_quantity'),assumed_fee=d.get('assumed_fee'))
                    for d in row['proxy']['orders']])
        result['cases'].append(value)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('binary','input','output-dir','quality-template','cost-template','template','theme'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    try:report=generate(args.binary,args.input,args.output_dir,args.quality_template,args.cost_template,args.template,args.theme)
    except (ValueError,OSError,KeyError,TypeError) as error:parser.exit(2,'Model comparison refused: '+str(error)+'\n')
    print(json.dumps(readout(report),indent=2))
    return 0 if report['status']=='completed' else 1


if __name__=='__main__':raise SystemExit(main())

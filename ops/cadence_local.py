#!/usr/bin/env python3
"""Measure unique recorded feeds behind a preserved quote-window diagnostic."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import shutil
import subprocess
import time

if __package__:
    from . import cadence_core as CORE,expiry_local as EXPLAIN
else:
    import cadence_core as CORE
    import expiry_local as EXPLAIN

REVIEW,QUALITY=EXPLAIN.REVIEW,EXPLAIN.QUALITY
require=REVIEW.require
MIB=1024*1024
LIMITS=dict(output_bytes=1024*MIB,free_reserve_bytes=1024*MIB,report_reserve_bytes=16*MIB,
    source_allowance_bytes=128*MIB,suite_seconds=300,interval_file_bytes=64*MIB)


def producer_code(quality_template,cost_template,expiry_template,theme):
    return dict(**EXPLAIN.old_code(quality_template,cost_template,theme),
        expiry_core=Path(EXPLAIN.CORE.__file__),expiry_local=Path(EXPLAIN.__file__),template=expiry_template)


def frozen(source,binary,quality_template,cost_template,expiry_template,theme):
    before=EXPLAIN.inventory(source)
    report=EXPLAIN.obj(source/'expiry-report.json')
    require(type(report.get('expiry_report_version')) is int and report['expiry_report_version']==1
            and report.get('status') in ('completed','incomplete') and report.get('input_unchanged') is True
            and report.get('code_unchanged') is True and report.get('orders_generated') is False
            and report.get('profit_reestimated') is False and report.get('full_window_verified') is False,
            'preserved version-1 quote-window report required')
    provenance=report['provenance']
    hashes=provenance['audit_hashes']
    require(set(before)==set(hashes)|{'expiry-report.json','expiry.html'},'unexpected or missing diagnostic artifact')
    for name,digest in hashes.items():
        path=PurePosixPath(name)
        require(name==path.as_posix() and not path.is_absolute() and '..' not in path.parts,'unsafe diagnostic artifact path')
        require(before[name]['sha256']==digest,'diagnostic artifact changed: '+name)
    require(provenance['code_hashes']=={name:REVIEW.digest(path) for name,path in producer_code(quality_template,cost_template,expiry_template,theme).items()},
            'unsupported diagnostic producer/assets version')
    require(REVIEW.digest(binary)==provenance['binary_sha256'],'installed source verifier differs')
    cost=EXPLAIN.obj(source/'input-cost-report.json',2*MIB)
    policy=EXPLAIN.obj(source/'input-cost-policy.json')
    expected_policy=dict(policy=EXPLAIN.COST.CORE.POLICY,profiles=EXPLAIN.COST.CORE.PROFILES,limits=EXPLAIN.COST.LIMITS)
    require(policy==cost['policy']==expected_policy and report['policy_sha256']==cost['policy_sha256']==EXPLAIN.COST.CORE.fingerprint(policy),
            'original cost policy differs')
    require(REVIEW.digest(source/'input-cost-report.json')==provenance['input_report_sha256']
            and REVIEW.digest(source/'input-bundle-inventory.json')==provenance['input_bundle_sha256']
            and REVIEW.digest(source/'input-cost-policy.json')==cost['provenance']['cost_policy_file_sha256'],
            'copied cost receipts differ')
    require(report['origin']==cost['origin'] and report['origin'] in ('synthetic_fixture','captured_public_data'), 'original origin differs')
    selected=report['selected_children']
    require(selected==cost['selected_children'] and 1<=len(selected)<=4 and len(set(selected))==len(selected)
            and all(type(n) is int and 1<=n<=999999 for n in selected), 'original selected cohort differs')
    expected=[(child,p['id']) for child in selected for p in EXPLAIN.COST.CORE.PROFILES]
    require([(c['child'],c['profile']) for c in cost['cases']]==expected
            and [(c['child'],c['profile']) for c in report['cases']]==expected
            and report['totals']==EXPLAIN.summary(report['cases']) and cost['totals']==EXPLAIN.COST.summarize(cost['cases']),
            'original case grid/counts differ')
    require(report['historical_totals']==cost['totals'],'historical lifecycle receipt differs')
    return report,cost,before


def source_groups(source,report,cost,before):
    groups=[]
    by_digest={}
    for child in report['selected_children']:
        base=f'markets/run-{child:06d}/market'
        try:
            market=EXPLAIN.obj(source/base/'market-replay.json')
            manifest=market['source']
            require(type(manifest.get('manifest_version')) is int and manifest['manifest_version']==1
                    and manifest['origin']==report['origin'], 'source manifest version/origin differs')
            files=manifest['files']
            require(files and [entry['file'] for entry in files]==sorted({entry['file'] for entry in files}), 'source manifest order differs')
            canonical=[]
            for entry in files:
                require(re.fullmatch(r'index\.jsonl|segment-[0-9]{8}\.jsonl',entry['file']) is not None, 'unsafe raw source filename')
                name=base+'/source/'+entry['file']
                require(name in before and before[name]['sha256']==entry['sha256'] and before[name]['bytes']==entry['bytes'],
                        'source copy differs from its manifest')
                canonical.append(dict(file=entry['file'],bytes=entry['bytes'],sha256=entry['sha256']))
            digest=hashlib.sha256(b'giethoorn-recorded-market-v1\0'+json.dumps(canonical,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
            require(digest==manifest['recording_sha256'],'source identity differs')
            for row in cost['cases']:
                if row['child']==child and row['status']=='verified':
                    require(row['recording_sha256']==digest,'cost case source identity differs')
            for row in report['cases']:
                if row['child']==child and row['status']=='verified':
                    require(row['recording_sha256']==digest,'diagnostic case source identity differs')
            if digest in by_digest:
                group=by_digest[digest]
                require(group['_market']==market,'duplicate identity has inconsistent source reports')
                group['children'].append(child)
            else:
                group=dict(child=child,children=[child],recording_sha256=digest,status='not_run',metrics=None,
                    request_neighborhoods=[],reason='Not admitted.',_market=market,_base=base)
                by_digest[digest]=group
                groups.append(group)
        except (ValueError,OSError,KeyError,TypeError) as error:
            groups.append(dict(child=child,children=[child],recording_sha256=None,status='unavailable',metrics=None,
                               request_neighborhoods=[],reason=str(error)))
    return groups


def admit(output,deadline):
    require(time.monotonic()<deadline,'cadence time budget exhausted')
    reserve=LIMITS['source_allowance_bytes']+LIMITS['report_reserve_bytes']
    require(EXPLAIN.COST.used_bytes(output)+reserve<=LIMITS['output_bytes'],'cadence output budget cannot admit source')
    require(shutil.disk_usage(output).free>=LIMITS['free_reserve_bytes']+reserve,'cadence free-space reserve insufficient')


def fresh_source(binary,source,group,output,origin,deadline):
    output.mkdir()
    raw=source/group['_base']/'source'
    EXPLAIN.native(binary,['paper-market-replay','--input',str(raw),'--output-dir',str(output/'market'),
        '--origin',origin.replace('_','-'),'--feed','bbo'],output/'native.stdout.json',output/'native.stderr',deadline)
    market=EXPLAIN.obj(output/'market/market-replay.json')
    require(market==group['_market']==EXPLAIN.obj(output/'native.stdout.json'),'fresh native source report differs')
    config=market['paper']['config']
    require(config['coin']=='BTC' and config['source']['network']=='mainnet','cadence source must match the declared BTC mainnet scope')
    for name in ('paper-input.jsonl','paper-updates.jsonl','market-links.jsonl','paper-report.json','source-manifest.json','market-replay.json'):
        require(REVIEW.digest(source/group['_base']/name)==REVIEW.digest(output/'market'/name),'saved native market stream differs: '+name)
    original=list(QUALITY.source_records(output/'market/source'))
    frames=EXPLAIN.lines(output/'market/paper-updates.jsonl')
    links=EXPLAIN.lines(output/'market/market-links.jsonl')
    events=EXPLAIN.CORE.market_events(original,frames,links)
    require(len(events)==market['source_report']['records'],'fresh source event count differs')
    return events


def neighborhoods(group,report):
    points={}
    for case in report['cases']:
        if case['child'] not in group['children'] or case['status']!='verified':
            continue
        for order in case['orders']:
            # Preserve already diagnosed source references; do not create or
            # re-evaluate an order, outcome or execution window.
            key=(case['child'],order['order_id'],order['request_sequence'],order['arrival_offset_ns'],order['expiry_offset_ns'])
            value=points.setdefault(key,dict(child=case['child'],order=order['order_id'],request_sequence=order['request_sequence'],
                arrival_offset_ns=order['arrival_offset_ns'],expiry_offset_ns=order['expiry_offset_ns'],
                profiles=[],case_ids=[],historical_diagnoses=[],timeline=order['timeline']))
            value['profiles'].append(case['profile'])
            value['case_ids'].append(case['case_id'])
            value['historical_diagnoses'].append(order['classification'])
    return list(points.values())


def totals(groups,selected):
    result=dict(selected_children=len(selected),recording_groups=len(groups),known_unique_recordings=sum(g['recording_sha256'] is not None for g in groups),
        duplicate_child_copies=len(selected)-len(groups),verified=0,unavailable=0,not_run=0,source_records=0,
        connections=0,bbo_messages=0,native_opportunities=0,source_clock_discontinuities=0)
    for group in groups:
        result[group['status']]+=1
        if group['status']=='verified':
            metric=group['metrics']
            result['source_records']+=metric['source_records']
            result['connections']+=len(metric['connections'])
            for kind in CORE.POLICY['series']:
                result[kind]+=metric['series'][kind]['observations']
            result['source_clock_discontinuities']+=len(metric['source_clock_discontinuities'])
    return result


def generate(binary,source,output,quality_template,cost_template,expiry_template,template,theme):
    binary,source,output=binary.resolve(),source.absolute(),output.resolve()
    require(binary.is_file() and os.access(binary,os.X_OK) and binary.stat().st_size<=128*MIB,'bounded installed source verifier required')
    require(not output.is_relative_to(source.resolve()),'cadence output must be outside original evidence')
    original,cost,before=frozen(source,binary,quality_template,cost_template,expiry_template,theme)
    assets=dict(template=QUALITY.read_asset(template),theme=QUALITY.read_asset(theme))
    code={**producer_code(quality_template,cost_template,expiry_template,theme),
          'cadence_core':Path(CORE.__file__),'cadence_local':Path(__file__),'cadence_template':template}
    code_hashes={name:REVIEW.digest(path) for name,path in code.items()}
    binary_sha=REVIEW.digest(binary)
    output.parent.mkdir(parents=True,exist_ok=True)
    require(shutil.disk_usage(output.parent).free>=LIMITS['free_reserve_bytes']+LIMITS['source_allowance_bytes'],'insufficient cadence free space')
    os.umask(0o077)
    output.mkdir(mode=0o700)
    deadline=time.monotonic()+LIMITS['suite_seconds']
    REVIEW.save(output/'input-before.json',before)
    shutil.copyfile(source/'expiry-report.json',output/'input-expiry-report.json')
    REVIEW.save(output/'cadence-policy.json',CORE.POLICY)
    (output/'recordings').mkdir()
    groups=source_groups(source,original,cost,before)
    report=dict(cadence_report_version=1,created_at_utc=datetime.now(timezone.utc).isoformat(),status='incomplete',
        origin=original['origin'],policy=CORE.POLICY,limits=LIMITS,selected_children=original['selected_children'],
        recordings=groups,totals=None,input_unchanged=False,code_unchanged=False,orders_generated=False,
        profit_evaluated=False,measured_order_latency=False,fill_probability_estimated=False,full_window_verified=False,error=None)
    for group in groups:
        if group['status']=='unavailable':
            continue
        try:
            admit(output,deadline)
        except (ValueError,OSError) as error:
            group['reason']=str(error)
            continue
        try:
            folder=output/'recordings'/f'run-{group["child"]:06d}'
            events=fresh_source(binary,source,group,folder,original['origin'],deadline)
            metric,intervals=CORE.analyze(group['child'],events)
            byte_count=0
            with (folder/'intervals.jsonl').open('xb') as stream:
                for row in intervals:
                    raw=QUALITY.encoded(row)+b'\n'
                    byte_count+=len(raw)
                    require(byte_count<=LIMITS['interval_file_bytes'],'cadence interval export exceeds bound')
                    stream.write(raw)
            metric['intervals_sha256']=REVIEW.digest(folder/'intervals.jsonl')
            REVIEW.save(folder/'cadence-recording.json',metric)
            group.update(status='verified',metrics=metric,request_neighborhoods=neighborhoods(group,original),reason=None)
        except (ValueError,OSError,KeyError,TypeError,IndexError,subprocess.TimeoutExpired) as error:
            group.update(status='unavailable',metrics=None,reason=str(error))
    for group in groups:
        group.pop('_market',None);group.pop('_base',None)
    try:
        after=EXPLAIN.inventory(source)
        REVIEW.save(output/'input-after.json',after)
        report['input_unchanged']=before==after
        report['code_unchanged']=code_hashes=={name:REVIEW.digest(path) for name,path in code.items()} and REVIEW.digest(binary)==binary_sha
    except (ValueError,OSError) as error:
        report['error']=str(error)
    if not report['input_unchanged'] or not report['code_unchanged']:
        report.update(status='source_changed',error='diagnostic input, verifier or cadence assets changed')
        for group in groups:
            group.update(status='unavailable',metrics=None,request_neighborhoods=[],reason='Evidence changed; cadence measurements not admitted.')
    elif all(group['status']=='verified' for group in groups):
        report['status']='completed'
    report['totals']=totals(groups,original['selected_children'])
    report['provenance']=dict(input_report_sha256=before['expiry-report.json']['sha256'],
        input_inventory_sha256=REVIEW.digest(output/'input-before.json'),binary_sha256=binary_sha,code_hashes=code_hashes,
        cadence_policy_sha256=REVIEW.digest(output/'cadence-policy.json'),
        audit_hashes={str(path.relative_to(output)):REVIEW.digest(path) for path in sorted(output.rglob('*')) if path.is_file()})
    require(EXPLAIN.COST.used_bytes(output)<=LIMITS['output_bytes']-LIMITS['report_reserve_bytes'],'cadence output exceeded report reserve')
    require(len(QUALITY.encoded(report))<=4*MIB,'cadence report exceeds bound')
    REVIEW.save(output/'cadence-report.json',report)
    html=QUALITY.render(report,assets['template'].decode(),assets['theme'].decode())
    with (output/'cadence.html').open('x') as stream:stream.write(html)
    return report


def readout(report):
    result={key:report[key] for key in ('status','input_unchanged','code_unchanged','totals','error')}
    result['recordings']=[]
    for group in report['recordings']:
        row=dict(child=group['child'],source_children=group['children'],status=group['status'],reason=group['reason'],series=None)
        if group['metrics'] is not None:
            metric=group['metrics']
            row.update(source_span_ms=EXPLAIN.milliseconds(metric['source_span_ns']),source_policy=metric['source_policy'],
                source_clock_discontinuities=len(metric['source_clock_discontinuities']),
                raw_messages_without_native_opportunity=sum(c['raw_bbo_without_native_opportunity'] for c in metric['connections']),series={})
            for kind in CORE.POLICY['series']:
                data=metric['series'][kind]
                row['series'][kind]=dict(observations=data['observations'],intervals=data['intervals'],zero_intervals=data['zero_intervals'],
                    p50_ms=EXPLAIN.milliseconds(data['percentiles_ns']['50']),p95_ms=EXPLAIN.milliseconds(data['percentiles_ns']['95']),
                    p99_ms=EXPLAIN.milliseconds(data['percentiles_ns']['99']),maximum_ms=EXPLAIN.milliseconds(data['maximum_ns']),
                    gap_bins=[b['count'] for b in data['bins']])
        result['recordings'].append(row)
    result['gap_bin_upper_ms']=['50','100','250','350','500','1000',None]
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('binary','input','output-dir','quality-template','cost-template','expiry-template','template','theme'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    try:
        report=generate(args.binary,args.input,args.output_dir,args.quality_template,args.cost_template,args.expiry_template,args.template,args.theme)
    except (ValueError,OSError,KeyError,TypeError) as error:
        parser.exit(2,'Cadence preflight failed: '+str(error)+'\n')
    print(json.dumps(readout(report),indent=2))
    print('Cadence view: '+str(args.output_dir/'cadence.html'))
    return 0 if report['status']=='completed' else 1


if __name__=='__main__':
    raise SystemExit(main())

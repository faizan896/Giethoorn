#!/usr/bin/env python3
"""One frozen public-data capture, followed by a separate offline replay check."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import stat
import subprocess
import time

if __package__:
    from . import cadence_core as CADENCE, expiry_core as EVENTS, quality_local as QUALITY, review_local as REVIEW
else:
    import cadence_core as CADENCE
    import expiry_core as EVENTS
    import quality_local as QUALITY
    import review_local as REVIEW

MIB = 1024 * 1024
BINARY_SHA256 = 'ed10624d0bc6a660e1aa6f8689ef0f42529b3e3d9dff76c5edcf9be93694ba1e'
POLICY = dict(feed_check_policy_version=1, check_id='btc-feed-check-001', coin='BTC', network='mainnet',
    duration_secs=120, profile='combined', depth_stale_after_ms=15000, bbo_stale_after_ms=2000,
    timer_interval_ms=250, max_reconnects=3, route='direct', max_segment_bytes=MIB,
    max_session_bytes=16*MIB, min_free_disk_bytes=1024*MIB, injected_faults=False,
    automatic_reruns=False, orders_generated=False)
LIMITS = dict(output_bytes=256*MIB, report_reserve_bytes=16*MIB, source_allowance_bytes=128*MIB,
    capture_bytes=64*MIB, native_file_bytes=16*MIB, interval_bytes=32*MIB,
    free_reserve_bytes=1024*MIB, capture_seconds=180, offline_seconds=120, native_seconds=30,
    max_files=512, max_source_events=10000)
require = REVIEW.require
PROXY_KEYS = ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy')


def obj(path):
    return REVIEW.read_json(path)


def inventory(root, bound):
    require(root.is_dir() and not root.is_symlink(), 'regular evidence directory required')
    result, total = {}, 0
    for path in sorted(root.rglob('*')):
        info = path.lstat()
        require(not path.is_symlink(), 'evidence symlink refused')
        if stat.S_ISDIR(info.st_mode):
            continue
        require(stat.S_ISREG(info.st_mode), 'evidence must contain regular files')
        total += info.st_size
        require(total <= bound and len(result) < LIMITS['max_files'], 'evidence inventory exceeds bound')
        result[path.relative_to(root).as_posix()] = dict(bytes=info.st_size, sha256=REVIEW.digest(path), mtime_ns=info.st_mtime_ns)
    return result


def used(root):
    return sum(p.stat().st_size for p in root.rglob('*') if p.is_file())


def assets(template, theme):
    return dict(feed_check=Path(__file__), cadence_core=Path(CADENCE.__file__), expiry_core=Path(EVENTS.__file__),
                quality_local=Path(QUALITY.__file__), review_local=Path(REVIEW.__file__), template=template, theme=theme)


def fingerprints(binary, template, theme):
    require(binary.is_file() and not binary.is_symlink() and os.access(binary, os.X_OK)
            and binary.stat().st_size <= 128*MIB, 'bounded installed native executable required')
    digest = REVIEW.digest(binary)
    require(digest == BINARY_SHA256, 'installed native executable differs from the frozen Mac runtime')
    return dict(binary_sha256=digest, code_hashes={name:REVIEW.digest(path) for name,path in assets(template,theme).items()})


def child_environment():
    # Docker Desktop may supply host proxy defaults. This check requests direct
    # verified TLS using the image trust store, without retaining secret values.
    env = dict(os.environ)
    for name in (*PROXY_KEYS, 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'OPENSSL_CONF'):
        env.pop(name, None)
    env.update(NO_PROXY='*', no_proxy='*')
    return env


def child_limits():
    resource.setrlimit(resource.RLIMIT_FSIZE, (LIMITS['native_file_bytes'], LIMITS['native_file_bytes']))


def stop_child(child):
    if child.poll() is not None:
        return
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=5)


def run_native(binary, arguments, stdout, stderr, deadline, budget_root, byte_cap, extra_bytes=0):
    require(time.monotonic() < deadline, 'process deadline exhausted')
    require(used(budget_root)+extra_bytes < byte_cap-LIMITS['report_reserve_bytes'], 'output budget exhausted before native call')
    require(shutil.disk_usage(budget_root).free >= LIMITS['free_reserve_bytes'], 'free-space reserve insufficient')
    result = dict(exit_code=None, timed_out=False, interrupted=False, budget_exceeded=False, error=None)
    child = None
    try:
        with stdout.open('xb') as out, stderr.open('xb') as err:
            child = subprocess.Popen([str(binary), *arguments], stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                env=child_environment(), start_new_session=True, preexec_fn=child_limits)
            while child.poll() is None:
                if time.monotonic() >= deadline:
                    result.update(timed_out=True, error='native process exceeded its deadline')
                    break
                if used(budget_root)+extra_bytes >= byte_cap-LIMITS['report_reserve_bytes'] or shutil.disk_usage(budget_root).free < LIMITS['free_reserve_bytes']:
                    result.update(budget_exceeded=True, error='output/free-space budget reached')
                    break
                try:
                    child.wait(timeout=.1)
                except subprocess.TimeoutExpired:
                    pass
    except KeyboardInterrupt:
        result.update(interrupted=True, error='native process interrupted')
    except OSError as error:
        result['error'] = str(error)
    finally:
        if child is not None:
            stop_child(child)
            result['exit_code'] = child.returncode
    result['status'] = 'completed' if result['exit_code'] == 0 and not any(result[k] for k in ('timed_out','interrupted','budget_exceeded','error')) else 'failed'
    if stderr.is_file():
        with stderr.open('rb') as stream:
            result['diagnostic'] = stream.read(2048).decode('utf-8', errors='replace').strip() or None
    return result


def capture_arguments(output):
    return ['collect','--coin',POLICY['coin'],'--network',POLICY['network'],
        '--duration-secs',str(POLICY['duration_secs']),'--feed-profile',POLICY['profile'],
        '--depth-stale-after-ms',str(POLICY['depth_stale_after_ms']),
        '--bbo-stale-after-ms',str(POLICY['bbo_stale_after_ms']),'--feed-timer-ms',str(POLICY['timer_interval_ms']),
        '--max-reconnects',str(POLICY['max_reconnects']),'--max-segment-bytes',str(POLICY['max_segment_bytes']),
        '--max-session-bytes',str(POLICY['max_session_bytes']),'--min-free-disk-bytes',str(POLICY['min_free_disk_bytes']),
        '--output-dir',str(output/'session')]


def capture(binary, output, template, theme, image_id, origin='captured_public_data'):
    binary,output = binary.absolute(),output.absolute()
    require(origin in ('captured_public_data','synthetic_fixture'), 'explicit recording origin required')
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', image_id) is not None, 'Docker image identity required')
    before = fingerprints(binary,template,theme)
    require(not output.exists() and not output.is_symlink(), 'capture output must be a new path')
    require(shutil.disk_usage(output.parent).free >= LIMITS['free_reserve_bytes']+LIMITS['capture_bytes'], 'capture free-space reserve insufficient')
    os.umask(0o077)
    output.mkdir(mode=0o700)
    request = dict(feed_check_request_version=1, created_at_utc=datetime.now(timezone.utc).isoformat(),
        origin=origin, policy=POLICY, limits=LIMITS, image_id=image_id, **before)
    REVIEW.save(output/'request.json',request)
    result = run_native(binary,capture_arguments(output),output/'live.jsonl',output/'capture.stderr',
        time.monotonic()+LIMITS['capture_seconds'],output,LIMITS['capture_bytes'])
    result.update(feed_check_capture_version=1, requested_duration_secs=POLICY['duration_secs'],
                  code_unchanged=before == fingerprints(binary,template,theme))
    if not result['code_unchanged']:
        result.update(status='failed',error='capture code/assets or native executable changed')
    result['artifacts'] = inventory(output,LIMITS['capture_bytes'])
    REVIEW.save(output/'capture-result.json',result)
    return result


def admit_source(source, binary, template, theme, image_id):
    before = inventory(source,LIMITS['capture_bytes'])
    request,result = obj(source/'request.json'),obj(source/'capture-result.json')
    require(type(request.get('feed_check_request_version')) is int and request['feed_check_request_version']==1
        and type(result.get('feed_check_capture_version')) is int and result['feed_check_capture_version']==1,
        'unsupported capture receipt version')
    require(request['origin'] in ('captured_public_data','synthetic_fixture') and request['policy']==POLICY
        and request['limits']==LIMITS and request['image_id']==image_id, 'frozen request or Docker image differs')
    require(result['requested_duration_secs']==POLICY['duration_secs'] and result['code_unchanged'] is True,
        'capture code changed or request duration differs')
    require(request['binary_sha256']==BINARY_SHA256 and
        {key:request[key] for key in ('binary_sha256','code_hashes')}==fingerprints(binary,template,theme),
        'capture producer or installed native executable differs')
    saved=result['artifacts']
    require(set(before)==set(saved)|{'capture-result.json'} and all(before[name]==saved[name] for name in saved),
        'captured source or original live output changed')
    require(result['status'] in ('completed','failed') and (result['status']!='completed' or
        result['exit_code']==0 and not any(result[key] for key in ('timed_out','interrupted','budget_exceeded','error'))),
        'capture lifecycle receipt is inconsistent')
    return request,result,before


def verify_session(source, inspection):
    session=inspection['session']
    require(inspection['status'] in ('completed','completed_with_connection_errors') and session['complete'] is True
        and session['end_reason']=='duration_elapsed' and inspection['storage']['finalized'] is True
        and inspection['recorded_duration_ns'] >= POLICY['duration_secs']*1000000000
        and session['feeds']['normalization_version']==2 and session['feeds']['all_required_fresh_observed'] is True,
        'capture did not complete with usable combined data')
    first=next(QUALITY.source_records(source/'session'))
    expected=dict(profile=POLICY['profile'],depth_stale_after_ms=POLICY['depth_stale_after_ms'],
                  bbo_stale_after_ms=POLICY['bbo_stale_after_ms'],timer_interval_ms=POLICY['timer_interval_ms'])
    require(first['schema_version']==2 and first['event']['type']=='feed_session_started'
        and first['event']['coin']==POLICY['coin'] and first['event']['network']==POLICY['network']
        and first['event']['policy']==expected and session['feeds']['policy']==expected, 'recorded policy differs')
    index=list(QUALITY.objects(source/'session/index.jsonl'))
    require(index[0]['event_schema_version']==2 and index[0]['max_segment_bytes']==POLICY['max_segment_bytes']
        and index[0]['max_session_bytes']==POLICY['max_session_bytes'] and index[-1]['kind']=='end',
        'collection is not finalized under the requested storage limits')


def audit(binary, source, output, template, theme, image_id):
    binary,source,output=binary.absolute(),source.absolute(),output.absolute()
    require(not output.exists() and not output.is_symlink() and not output.resolve().is_relative_to(source.resolve()),
        'audit output must be new and outside capture evidence')
    request,recorded,before=admit_source(source,binary,template,theme,image_id)
    fixed=fingerprints(binary,template,theme)
    template_bytes,theme_bytes=QUALITY.read_asset(template),QUALITY.read_asset(theme)
    require(shutil.disk_usage(output.parent).free >= LIMITS['free_reserve_bytes']+LIMITS['source_allowance_bytes'], 'audit free-space reserve insufficient')
    os.umask(0o077)
    output.mkdir(mode=0o700)
    REVIEW.save(output/'input-before.json',before)
    shutil.copyfile(source/'request.json',output/'input-request.json')
    shutil.copyfile(source/'capture-result.json',output/'input-capture-result.json')
    report=dict(feed_check_report_version=1, created_at_utc=datetime.now(timezone.utc).isoformat(), origin=request['origin'],
        status='incomplete', request=request, capture=recorded,
        integrity=dict(status='not_run',reason=None), replay=dict(status='not_run',comparison=None,reason=None),
        cadence=dict(status='not_run',metrics=None,reason=None), input_unchanged=False, code_unchanged=False,
        orders_generated=False, measured_order_latency=False, fill_probability_estimated=False,
        profit_evaluated=False, full_window_verified=False, error=None)
    deadline=time.monotonic()+LIMITS['offline_seconds']
    source_bytes=sum(row['bytes'] for row in before.values())
    attempted=set()
    active='integrity'
    def native(args,name):
        result=run_native(binary,args,output/(name+'.stdout.json'),output/(name+'.stderr'),
            min(deadline,time.monotonic()+LIMITS['native_seconds']),output,LIMITS['output_bytes'],source_bytes)
        attempted.add(active)
        REVIEW.save(output/(name+'-result.json'),result)
        require(result['status']=='completed', result['error'] or result.get('diagnostic') or 'native '+name+' failed')
        return output/(name+'.stdout.json')
    try:
        inspection=obj(native(['inspect','--input',str(source/'session'),'--allow-incomplete'],'inspection'))
        report['integrity']=dict(status='verified',inspection=inspection,reason=None)
        require(recorded['status']=='completed','capture did not complete: '+str(recorded['error'] or recorded.get('diagnostic') or recorded['exit_code']))
        verify_session(source,inspection)
        active='replay'
        replay=native(['replay','--input',str(source/'session')],'replay')
        require(REVIEW.digest(replay)==REVIEW.digest(source/'live.jsonl'), 'live/replay normalized streams differ')
        report['replay']=dict(status='verified',comparison='exact',sha256=REVIEW.digest(replay),reason=None)
        active='cadence'
        require(used(output)+source_bytes+LIMITS['source_allowance_bytes'] < LIMITS['output_bytes']-LIMITS['report_reserve_bytes'],
                'output budget cannot admit mark-only source replay')
        market=output/'market'
        native(['paper-market-replay','--input',str(source/'session'),'--output-dir',str(market),
            '--origin',request['origin'].replace('_','-'),'--feed','bbo'],'market')
        market_report=obj(market/'market-replay.json')
        require(market_report==obj(output/'market.stdout.json') and market_report['source']['origin']==request['origin'],
                'native source identity or origin differs')
        raw=list(QUALITY.source_records(market/'source'))
        require(0<len(raw)<LIMITS['max_source_events'], 'native source event bound exceeded')
        events=EVENTS.market_events(raw,list(QUALITY.objects(market/'paper-updates.jsonl')),list(QUALITY.objects(market/'market-links.jsonl')))
        metric,intervals=CADENCE.analyze(1,events)
        metric['recording_sha256']=market_report['source']['recording_sha256']
        size=0
        with (output/'intervals.jsonl').open('xb') as stream:
            for row in intervals:
                encoded=QUALITY.encoded(row)+b'\n';size+=len(encoded)
                require(size<=LIMITS['interval_bytes'], 'interval export exceeds bound')
                stream.write(encoded)
        metric['intervals_sha256']=REVIEW.digest(output/'intervals.jsonl')
        REVIEW.save(output/'cadence-recording.json',metric)
        require(time.monotonic()<deadline,'offline measurement deadline exhausted')
        report['cadence']=dict(status='verified',metrics=metric,reason=None)
    except (ValueError,OSError,KeyError,TypeError,IndexError,StopIteration) as error:
        report['error']=str(error) or type(error).__name__
        if active in attempted and report[active]['status']!='verified':
            report[active]['status']='failed'
        for key in ('integrity','replay','cadence'):
            if report[key]['status'] in ('not_run','failed'):
                report[key]['reason']=report['error']
    try:
        after=inventory(source,LIMITS['capture_bytes'])
        REVIEW.save(output/'input-after.json',after)
        report['input_unchanged']=before==after
        report['code_unchanged']=fixed==fingerprints(binary,template,theme)
    except (ValueError,OSError) as error:
        report['error']=str(error)
    if not report['input_unchanged'] or not report['code_unchanged']:
        report.update(status='source_changed',error='capture evidence, binary or report assets changed')
        report['cadence']=dict(status='unavailable',metrics=None,reason=report['error'])
        for key in ('integrity','replay'):
            report[key]=dict(status='unavailable',reason=report['error'])
    elif all(report[key]['status']=='verified' for key in ('integrity','replay','cadence')):
        report['status']='completed'
    require(used(output)+source_bytes <= LIMITS['output_bytes']-LIMITS['report_reserve_bytes'], 'output exceeded report reservation')
    report['provenance']=dict(**fixed, input_inventory_sha256=REVIEW.digest(output/'input-before.json'),
        audit_hashes={str(p.relative_to(output)):REVIEW.digest(p) for p in sorted(output.rglob('*')) if p.is_file()})
    require(len(QUALITY.encoded(report))<=4*MIB, 'feed-check report exceeds bound')
    REVIEW.save(output/'feed-check-report.json',report)
    with (output/'feed-check.html').open('x') as stream:
        stream.write(QUALITY.render(report,template_bytes.decode(),theme_bytes.decode()))
    return report


def milliseconds(ns):
    if ns is None:return None
    value=int(ns);whole,part=divmod(value,1000000)
    tail=str(part).zfill(6).rstrip('0')
    return str(whole)+('.'+tail if tail else '')


def readout(report):
    result={key:report[key] for key in ('status','origin','input_unchanged','code_unchanged','error')}
    result['stages']={key:report[key]['status'] for key in ('capture','integrity','replay','cadence')}
    result['requested_duration_secs']=report['request']['policy']['duration_secs']
    result['capture_exit_code']=report['capture']['exit_code']
    result['capture_timed_out']=report['capture']['timed_out']
    result['series']=None
    metric=report['cadence']['metrics']
    if metric is not None:
        result.update(source_records=metric['source_records'],source_span_ms=milliseconds(metric['source_span_ns']),
            connections=len(metric['connections']),source_clock_discontinuities=len(metric['source_clock_discontinuities']),series={})
        for kind,data in metric['series'].items():
            result['series'][kind]=dict(observations=data['observations'],intervals=data['intervals'],
                p50_ms=milliseconds(data['percentiles_ns']['50']),p95_ms=milliseconds(data['percentiles_ns']['95']),
                p99_ms=milliseconds(data['percentiles_ns']['99']),maximum_ms=milliseconds(data['maximum_ns']),gap_bins=[b['count'] for b in data['bins']])
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['capture','audit'])
    for name in ('binary','output-dir','template','theme'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--input',type=Path)
    parser.add_argument('--image-id',required=True)
    args=parser.parse_args()
    def interrupted(*_):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,interrupted)
    try:
        if args.mode=='capture':
            require(args.input is None,'capture has no input recording')
            result=capture(args.binary,args.output_dir,args.template,args.theme,args.image_id)
            print(json.dumps({key:result[key] for key in ('status','requested_duration_secs','exit_code','timed_out','interrupted','error')},indent=2))
        else:
            require(args.input is not None,'audit requires capture input')
            result=audit(args.binary,args.input,args.output_dir,args.template,args.theme,args.image_id)
            print(json.dumps(readout(result),indent=2))
    except (ValueError,OSError,KeyError,TypeError) as error:
        parser.exit(2,'Feed check refused: '+str(error)+'\n')
    return 0 if result['status']=='completed' else 1


if __name__=='__main__':
    raise SystemExit(main())

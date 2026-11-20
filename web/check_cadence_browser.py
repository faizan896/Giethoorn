#!/usr/bin/env python3
"""Check saved cadence views offline, including distinct and sparse series."""
import argparse
import copy
import json
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

PROJECT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(PROJECT))
from ops import cadence_core as CORE,cadence_local as RUN,expiry_core as EVENTS


def ms(ns):
    return 'Unavailable' if ns is None else RUN.EXPLAIN.milliseconds(ns)+' ms'


def run(html,output):
    output.mkdir(parents=True,exist_ok=True)
    source=html.read_text();report=json.loads((html.parent/'cadence-report.json').read_text())
    errors,requests,checks=[],[],[]
    with sync_playwright() as driver:
        browser=driver.chromium.launch(executable_path='/usr/bin/chromium',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1100},accept_downloads=True)
        context.set_offline(True)
        def page_for(contents):
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('request',lambda r:requests.append(r.url));page.set_content(contents,wait_until='load');return page
        page=page_for(source)
        assert page.locator('#status').inner_text()=='Recorded cadence audit complete'
        assert page.locator('#verified').inner_text()==str(report['totals']['verified'])
        assert page.locator('#messages').inner_text().replace(',','')==str(report['totals']['bbo_messages'])
        assert page.locator('#recordings tr').count()==len(report['recordings'])
        for i,group in enumerate(report['recordings']):
            page.locator('#recording').select_option(str(i))
            for kind in CORE.POLICY['series']:
                page.locator('#series').select_option(kind)
                data=group['metrics']['series'][kind]
                assert page.locator('#p50').inner_text()==ms(data['percentiles_ns']['50'])
                assert page.locator('#p95').inner_text()==ms(data['percentiles_ns']['95'])
                assert page.locator('#histogram .bin strong').all_inner_texts()==[format(b['count'],',') for b in data['bins']]
            connection=group['metrics']['connections'][0]
            page.locator('#connection').select_option(str(connection['connection_id']))
            assert page.locator('#edges tr').count()==1
        checks.append('Unique-recording counts, raw/native series, percentiles, histograms and connection filters match backend')
        page.locator('#recording').select_option('0');page.locator('#series').select_option('bbo_messages')
        with page.expect_download() as pending:page.locator('#download').click()
        pending.value.save_as(output/'downloaded-cadence.json')
        assert json.loads((output/'downloaded-cadence.json').read_text())==report
        page.screenshot(path=str(output/'cadence-desktop.png'),full_page=True)
        for width in (390,320):
            page.set_viewport_size({'width':width,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'),width
            page.screenshot(path=str(output/f'cadence-mobile-{width}.png'),full_page=True)
        checks.append('Exact raw JSON export and desktop/390/320-pixel layouts work')
        boot=source.split('<script type="application/json" id="cadence-data">',1)[1].split('</script>',1)[0]
        def with_report(value):
            encoded=json.dumps(value).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
            return source.replace(boot,encoded,1)
        load=lambda name:[json.loads(line) for line in (PROJECT/'fixtures'/name).read_text().splitlines()]
        events=EVENTS.market_events(load('hyperliquid-combined-v2.jsonl'),load('paper-recorded-v2.updates.jsonl'),load('paper-recorded-v2.links.jsonl'))
        metric,_=CORE.analyze(1,events)
        synthetic=copy.deepcopy(report)
        synthetic.update(origin='synthetic_fixture',selected_children=[1,2],provenance=dict(kind='synthetic_browser_test_only'))
        synthetic['recordings']=[dict(child=1,children=[1,2],recording_sha256='synthetic-source',status='verified',metrics=metric,reason=None,request_neighborhoods=[])]
        synthetic['totals']=RUN.totals(synthetic['recordings'],[1,2])
        sparse=page_for(with_report(synthetic))
        assert sparse.locator('#origin').inner_text()=='Synthetic fixture'
        assert sparse.locator('#messages').inner_text()=='7'
        assert sparse.locator('#p50').inner_text()=='20 ms'
        sparse.locator('#series').select_option('native_opportunities')
        assert sparse.locator('#p50').inner_text()=='60 ms'
        sparse.locator('#connection').select_option('2')
        assert sparse.locator('#p95').inner_text()=='Unavailable'
        assert sparse.locator('#empty').is_visible()
        assert '1 duplicate child copies' in sparse.locator('#scope').inner_text()
        sparse.screenshot(path=str(output/'synthetic-sparse.png'),full_page=True)
        checks.append('Synthetic duplicate aliases contribute once; distinct series and one-observation censoring stay correct')
        bad=copy.deepcopy(synthetic)
        bad.update(status='source_changed',input_unchanged=False,precision_probe=2**63+123,
            error='</script><img src="https://synthetic.invalid/" onerror="globalThis.cadenceInjection=true">')
        for group in bad['recordings']:group.update(status='unavailable',metrics=None,reason='Synthetic evidence change')
        bad['totals']=RUN.totals(bad['recordings'],[1,2])
        failed=page_for(with_report(bad))
        assert failed.locator('#status').inner_text()=='Recorded cadence audit incomplete'
        assert failed.locator('#p50').inner_text()=='Unavailable'
        assert failed.locator('#error').inner_text()==bad['error']
        assert failed.evaluate('globalThis.cadenceInjection === undefined')
        with failed.expect_download() as pending:failed.locator('#download').click()
        pending.value.save_as(output/'synthetic-failure.json')
        assert json.loads((output/'synthetic-failure.json').read_text())==bad
        checks.append('Unavailable inputs show no fabricated measurements; hostile text and large-integer JSON export are safe')
        assert not errors,errors
        assert not requests,requests
        browser.close()
    result=dict(checks=checks,errors=errors,network_requests=requests)
    (output/'browser-checks.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html',type=Path,required=True);parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();run(args.html,args.output_dir)

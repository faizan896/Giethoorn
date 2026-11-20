#!/usr/bin/env python3
"""Validate native and deliberately sparse/unavailable fresh-check views offline."""
import argparse
import copy
import json
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

PROJECT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(PROJECT))
from ops import feed_check as RUN


def run(html,output):
    output.mkdir(parents=True,exist_ok=True)
    source=html.read_text();report=json.loads((html.parent/'feed-check-report.json').read_text())
    errors,requests,checks=[],[],[]
    with sync_playwright() as driver:
        browser=driver.chromium.launch(executable_path='/usr/bin/chromium',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1100},accept_downloads=True)
        context.set_offline(True)
        def page_for(contents):
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('request',lambda r:requests.append(r.url));page.set_content(contents,wait_until='load');return page
        page=page_for(source)
        assert page.locator('#status').inner_text()=='Fresh recording check complete'
        assert page.locator('#comparison').inner_text()=='Exact match'
        assert page.locator('#stages tr').count()==4
        metric=report['cadence']['metrics']
        for kind in RUN.CADENCE.POLICY['series']:
            page.locator('#series').select_option(kind)
            data=metric['series'][kind]
            assert page.locator('#p50').inner_text()==RUN.milliseconds(data['percentiles_ns']['50'])+' ms'
            assert page.locator('#histogram .bin strong').all_inner_texts()==[format(b['count'],',') for b in data['bins']]
        assert page.locator('#messages').inner_text().replace(',','')==str(metric['series']['bbo_messages']['observations'])
        page.locator('#series').select_option('bbo_messages')
        page.locator('#connection').select_option(str(metric['connections'][0]['connection_id']))
        assert page.locator('#edges tr').count()==1
        page.locator('#connection').select_option('all')
        with page.expect_download() as pending:page.locator('#download').click()
        pending.value.save_as(output/'downloaded-feed-check.json')
        assert json.loads((output/'downloaded-feed-check.json').read_text())==report
        page.screenshot(path=str(output/'feed-check-desktop.png'),full_page=True)
        for width in (390,320):
            page.set_viewport_size({'width':width,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'),width
            page.screenshot(path=str(output/f'feed-check-mobile-{width}.png'),full_page=True)
        checks.append('Native stage outcomes, series/bins/quantiles, connection filter and exact JSON export agree with backend')
        checks.append('Desktop and 390/320-pixel layouts remain inside the viewport')
        boot=source.split('<script type="application/json" id="feed-check-data">',1)[1].split('</script>',1)[0]
        def with_report(value):
            encoded=json.dumps(value).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
            return source.replace(boot,encoded,1)
        load=lambda name:[json.loads(line) for line in (PROJECT/'fixtures'/name).read_text().splitlines()]
        events=RUN.EVENTS.market_events(load('hyperliquid-combined-v2.jsonl'),load('paper-recorded-v2.updates.jsonl'),load('paper-recorded-v2.links.jsonl'))
        sparse=copy.deepcopy(report);sparse['cadence']['metrics'],_=RUN.CADENCE.analyze(1,events)
        golden=page_for(with_report(sparse))
        assert golden.locator('#p50').inner_text()=='20 ms'
        golden.locator('#series').select_option('native_opportunities')
        assert golden.locator('#p50').inner_text()=='60 ms'
        golden.locator('#connection').select_option('2')
        assert golden.locator('#p95').inner_text()=='Unavailable'
        assert golden.locator('#empty').is_visible()
        checks.append('Distinct raw/native golden series and a single censored observation stay explicit')
        failed=copy.deepcopy(report)
        failed.update(status='incomplete',precision_probe=2**63+123,
            error='</script><img src="https://synthetic.invalid/" onerror="globalThis.feedInjection=true">')
        failed['capture'].update(status='failed',timed_out=True,exit_code=-15)
        failed['replay']=dict(status='not_run',comparison=None,reason='Synthetic timeout')
        failed['cadence']=dict(status='not_run',metrics=None,reason='Synthetic timeout')
        error=page_for(with_report(failed))
        assert error.locator('#status').inner_text()=='Fresh recording check incomplete'
        assert error.locator('#messages').inner_text()=='Unavailable'
        assert error.locator('#p50').inner_text()=='Unavailable'
        assert error.locator('#comparison').inner_text()!='Exact match'
        assert error.locator('#error').inner_text()==failed['error']
        assert error.evaluate('globalThis.feedInjection === undefined')
        with error.expect_download() as pending:error.locator('#download').click()
        pending.value.save_as(output/'failed-feed-check.json')
        assert json.loads((output/'failed-feed-check.json').read_text())==failed
        error.screenshot(path=str(output/'feed-check-timeout.png'),full_page=True)
        changed=copy.deepcopy(report);changed.update(status='source_changed',input_unchanged=False)
        changed_page=page_for(with_report(changed))
        assert changed_page.locator('#opportunities').inner_text()=='Unavailable'
        assert changed_page.locator('#p95').inner_text()=='Unavailable'
        checks.append('Timeout/changed evidence cannot display admitted measurements; hostile text and large-integer export are safe')
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

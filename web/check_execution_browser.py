#!/usr/bin/env python3
"""Controlled execution UI acceptance; no orders are submitted by this test."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def money_decimal(text):
    return Decimal(text.replace('$','').replace(',','').replace('−','-'))


def run(html, fixture_html, output, url=None):
    output.mkdir(parents=True, exist_ok=True)
    frames=[json.loads(line) for line in (html.parent/'replay/paper-updates.jsonl').read_text().splitlines()]
    trace=[json.loads(line) for line in (html.parent/'replay/execution-trace.jsonl').read_text().splitlines()]
    fixture_frames=[json.loads(line) for line in (fixture_html.parent/'replay/paper-updates.jsonl').read_text().splitlines()]
    fixture_trace=[json.loads(line) for line in (fixture_html.parent/'replay/execution-trace.jsonl').read_text().splitlines()]
    checks,errors=[],[]
    def seek(page,index):
        page.locator('#scrubber').evaluate('(e,n)=>{e.value=String(n);e.dispatchEvent(new Event("input",{bubbles:true}));}',index)
    with sync_playwright() as driver:
        browser=driver.chromium.launch(executable_path='/usr/bin/chromium',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1080})
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        if url:page.goto(url,wait_until='networkidle')
        else:context.set_offline(True);page.set_content(html.read_text(),wait_until='load')
        assert page.locator('#lab-kind').inner_text()=='Controlled simulation'
        assert page.locator('#lab-title').inner_text()=='Execution scenarios'
        assert 'Recorded prices, simulated execution.' in page.locator('.banner').inner_text()
        assert page.locator('#source-gate').inner_text()=='Not verified'
        assert page.locator('#execution-assumptions').is_visible()
        assert page.locator('#execution-costs').is_visible()
        assert page.locator('#assumed-fee').inner_text().endswith('× notional')
        checks.append('Real-price origin, simulated execution, explicit assumptions and outstanding collector gate remain clear')
        first=next(i for i,f in enumerate(frames) if f['assumed_fill'])
        seek(page,first)
        assert page.locator('#event-title').inner_text()=='Assumed IOC fill'
        assert money_decimal(page.locator('#fees').inner_text())==Decimal(frames[first]['account']['fees'])
        assert money_decimal(page.locator('#execution-spread').inner_text())==Decimal(trace[first]['cumulative_costs']['spread_cost'])
        assert money_decimal(page.locator('#execution-slippage').inner_text())==Decimal(trace[first]['cumulative_costs']['slippage_cost'])
        assert page.locator('#source-sequence').inner_text()==str(trace[first]['market_sequence'])
        checks.append('Rendered fill, source event, account fee and cumulative costs match persisted Rust states')
        page.locator('[data-execution-chart="pnl"]').click()
        assert page.locator('#chart-title').inner_text()=='Net paper P&L'
        assert page.locator('[data-execution-chart="pnl"]').get_attribute('aria-pressed')=='true'
        page.locator('[data-execution-chart="price"]').click()
        assert page.locator('#chart-title').inner_text().startswith('Recorded ')
        checks.append('Price and net-PnL chart controls switch actual derived series')
        page.locator('#reset').click()
        assert page.locator('#frame-label').inner_text().startswith('1 / ')
        assert page.locator('#fees').inner_text()=='$0.00'
        page.locator('#play').click();page.wait_for_timeout(750);page.locator('#play').click()
        assert page.locator('#play').inner_text()=='Play replay'
        assert int(page.locator('#frame-label').inner_text().split(' / ')[0])>1
        seek(page,first)
        assert page.locator('[data-event]').count()<=40
        checks.append('Reset/play/pause/scrubbing work with a bounded event trace')
        seek(page,len(frames)-1)
        page.locator('[data-execution-chart="pnl"]').click()
        page.screenshot(path=str(output/'execution-desktop.png'),full_page=True)
        page.screenshot(path=str(output/'execution-preview.png'))
        for width in (320,390,768,1440):
            page.set_viewport_size({'width':width,'height':844})
            assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),width
            if width==390:page.screenshot(path=str(output/'execution-mobile.png'),full_page=True)
        checks.append('320–1440 pixel layouts have no horizontal overflow')
        offline=browser.new_context(viewport={'width':1440,'height':1080});offline.set_offline(True)
        saved=offline.new_page();requests=[];saved.on('request',lambda r:requests.append(r.url));saved.on('pageerror',lambda e:errors.append(str(e)))
        saved.set_content(html.read_text(),wait_until='load');seek(saved,first)
        saved.locator('[data-execution-chart="pnl"]').click()
        assert saved.locator('#chart-title').inner_text()=='Net paper P&L'
        assert requests==[],requests
        checks.append('Exact portable captured-data view works offline with zero requests')
        saved.set_content(fixture_html.read_text(),wait_until='load')
        assert 'Synthetic fixture and simulated execution.' in saved.locator('.banner').inner_text()
        partial=next(i for i,f in enumerate(fixture_frames) if f['assumed_fill'])
        seek(saved,partial)
        assert 'Partially Filled' in saved.locator('#order-rows').inner_text()
        cancel=next(i for i,t in enumerate(fixture_trace) if t['phase']=='assumed_cancel_ack' and t['order_id']=='buy-partial')
        seek(saved,cancel)
        assert 'Cancelled' in saved.locator('#order-rows tr').filter(has_text='buy-partial').inner_text()
        stale=next(i for i,f in enumerate(fixture_frames) if f['order'] and f['order']['id']=='stale-send')
        seek(saved,stale)
        assert saved.locator('#event-title').inner_text()=='Scenario order blocked by risk'
        assert 'Stale Market' in saved.locator('#order-rows').inner_text()
        seek(saved,len(fixture_frames)-1)
        assert saved.locator('#scenario-state').inner_text()=='Ended · unresolved'
        assert saved.locator('#working').inner_text()=='1'
        assert money_decimal(saved.locator('#fees').inner_text())==Decimal('0.02511250125')
        assert money_decimal(saved.locator('#execution-spread').inner_text())==Decimal('0.05')
        assert money_decimal(saved.locator('#execution-slippage').inner_text())==Decimal('0.0050225')
        assert saved.locator('#source-gate').inner_text()=='Not verified'
        checks.append('Synthetic fixture exposes partial/cancel/stale states, exact costs and unresolved ending exposure')
        assert errors==[],errors;assert requests==[],requests
        checks.append('No JavaScript errors or hidden network activity')
        browser.close()
    (output/'execution-browser-checks.json').write_text(json.dumps(dict(status='passed',checks=checks,javascript_errors=errors),indent=2)+'\n')
    print(json.dumps(dict(status='passed',checks=len(checks),artifacts=str(output.resolve())),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html',type=Path,required=True)
    parser.add_argument('--fixture-html',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--url')
    args=parser.parse_args();run(args.html,args.fixture_html,args.output_dir,args.url)

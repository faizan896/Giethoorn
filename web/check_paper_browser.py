#!/usr/bin/env python3
"""Browser acceptance for the explicitly synthetic Paper Lab."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def run(url,output,html):
    output.mkdir(parents=True,exist_ok=True)
    checks=[];errors=[]
    with sync_playwright() as driver:
        browser=driver.chromium.launch(executable_path='/usr/bin/chromium',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1080},device_scale_factor=1)
        page=context.new_page()
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(url,wait_until='networkidle')
        assert 'Synthetic scenario.' in page.locator('.banner').inner_text()
        assert page.locator('#position').inner_text()=='0'
        assert page.locator('#fees').inner_text()=='$0.0592'
        assert page.locator('#realized').inner_text()=='$1.60'
        assert page.locator('#balance').inner_text()=='$10,001.5408'
        assert page.locator('#order-rows tr').count()==6
        checks.append('Initial final state matches Rust golden accounting and is explicitly synthetic')
        page.locator('#reset').click()
        assert page.locator('#frame-label').inner_text()=='1 / 29'
        assert 'No orders' in page.locator('#order-rows').inner_text()
        page.locator('#next').click()
        assert page.locator('#frame-label').inner_text()=='2 / 29'
        page.locator('#previous').click()
        assert page.locator('#frame-label').inner_text()=='1 / 29'
        checks.append('Reset, next and previous traverse the real replay trace')
        page.locator('[data-event="6"]').click()
        before=page.locator('#balance').inner_text()
        assert page.locator('#position').inner_text()=='0.5'
        assert 'Pending Cancel' in page.locator('#order-rows').inner_text()
        page.locator('[data-event="7"]').click()
        assert page.locator('#event-title').inner_text()=='Duplicate event ignored'
        assert page.locator('#balance').inner_text()==before
        checks.append('Partial fills during cancellation and duplicate-fill accounting remain visible')
        page.locator('[data-event="16"]').click()
        assert 'Stale Market' in page.locator('#order-rows').inner_text()
        assert page.locator('#mark-state').inner_text()=='Stale'
        page.locator('[data-event="27"]').click()
        assert 'Halted' in page.locator('#order-rows').inner_text()
        assert page.locator('#risk-status').inner_text()=='Halted'
        checks.append('Stale-data and halt rejections are shown without synthetic cancellations')
        page.locator('#play').click()
        page.wait_for_function("document.querySelector('#frame-label').textContent !== '28 / 29'")
        page.locator('#play').click()
        assert 'Play scenario' in page.locator('#play').inner_text()
        page.locator('#scrubber').evaluate("node=>{node.value=21;node.dispatchEvent(new Event('input',{bubbles:true}));}")
        assert page.locator('#position').inner_text()=='-0.1'
        checks.append('Playback and scrubber navigate state without recomputing finances in JavaScript')
        page.evaluate("document.documentElement.style.scrollBehavior='auto';window.scrollTo(0,0)")
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
        page.screenshot(path=str(output/'paper-lab-desktop.png'),full_page=True)
        page.screenshot(path=str(output/'paper-lab-preview.png'),full_page=False)
        page.set_viewport_size({'width':390,'height':844})
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
        page.screenshot(path=str(output/'paper-lab-mobile.png'),full_page=True)
        checks.append('Desktop and mobile layouts have no horizontal page overflow')
        context.set_offline(True)
        offline=context.new_page();requests=[]
        offline.on('request',lambda request:requests.append(request.url))
        offline.on('pageerror',lambda error:errors.append(str(error)))
        offline.set_content(html.read_text(),wait_until='load')
        offline.locator('#reset').click();offline.locator('#next').click()
        assert offline.locator('#frame-label').inner_text()=='2 / 29'
        assert not requests,requests
        checks.append('Portable Paper Lab stays interactive offline with zero network requests')
        assert not errors,errors
        checks.append('No browser JavaScript errors')
        browser.close()
    result=dict(status='passed',checks=checks,browser_errors=errors)
    (output/'paper-browser-checks.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status='passed',checks=len(checks),artifacts=str(output)),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:3000/paper')
    parser.add_argument('--html',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    run(args.url,args.output_dir.resolve(),args.html)

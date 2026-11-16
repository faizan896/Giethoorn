#!/usr/bin/env python3
"""Optional browser acceptance; uses installed Playwright and Chromium."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def run(url, output):
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    checks = []
    with sync_playwright() as driver:
        browser = driver.chromium.launch(executable_path='/usr/bin/chromium', headless=True)
        context = browser.new_context(viewport={'width':1440,'height':1080},device_scale_factor=1)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(url, wait_until='networkidle')
        page.wait_for_function("document.querySelector('#market-price').textContent !== '—'")
        assert page.locator('#mode-text').inner_text() == 'Collector running'
        assert page.locator('#gate-badge').inner_text() == 'In progress'
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
        assert 'Clock uncertain' not in page.locator('#bbo-status').inner_text()
        checks.append('Live data renders, current gate is pending, desktop has no horizontal overflow')
        # Range/series controls must change the actual graph.
        page.locator('[data-range="300000"]').click()
        assert page.locator('[data-range="300000"]').get_attribute('aria-pressed') == 'true'
        for source in ('bbo','depth'):
            page.locator('[data-series="'+source+'"]').click()
        assert page.locator('#chart-empty').is_visible()
        for source in ('bbo','depth'):
            page.locator('[data-series="'+source+'"]').click()
        assert not page.locator('#chart-empty').is_visible()
        checks.append('Chart ranges and source toggles work without invented series')
        page.locator('[data-nav="recordings"]').click()
        page.locator('[data-filter="recording"]').click()
        assert page.locator('#session-rows tr').count() <= 1
        assert 'Collecting' in page.locator('#session-rows').inner_text()
        page.locator('[data-filter="verified"]').click()
        assert 'Collecting' not in page.locator('#session-rows').inner_text()
        page.locator('[data-filter="all"]').click()
        checks.append('Navigation and active/verified recording filters work')
        page.locator('[data-nav="overview"]').click()
        page.locator('#pause-view').click()
        elapsed=page.locator('#elapsed').inner_text()
        page.wait_for_timeout(2300)
        assert page.locator('#elapsed').inner_text() == elapsed
        assert page.locator('#mode-text').inner_text() == 'Display paused'
        page.locator('#pause-view').click()
        page.wait_for_function("document.querySelector('#mode-text').textContent === 'Collector running'")
        checks.append('Pause freezes only the view; resuming reconnects to the monitor')
        page.locator('[data-range="60000"]').click()
        page.evaluate("document.documentElement.style.scrollBehavior='auto';window.scrollTo(0,0)")
        page.screenshot(path=str(output/'dashboard-desktop.png'), full_page=True)
        page.screenshot(path=str(output/'dashboard-preview.png'), full_page=False)
        page.set_viewport_size({'width':390,'height':844})
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
        page.wait_for_function("document.querySelector('#price-chart').viewBox.baseVal.width < 450")
        page.screenshot(path=str(output/'dashboard-mobile.png'), full_page=True)
        checks.append('Mobile 390px layout has no horizontal page overflow')
        page.set_viewport_size({'width':1440,'height':1080})
        with page.expect_download() as download:
            page.locator('#export').click()
        snapshot=output/'giethoorn-dashboard.html'
        download.value.save_as(snapshot)
        # The Cloud browser blocks file:// navigation by policy. Render the exact
        # downloaded bytes offline, with networking disabled; do not change policy.
        await_requests=[]
        context.set_offline(True)
        offline=context.new_page()
        offline.on('request', lambda request:await_requests.append(request.url))
        offline.on('pageerror',lambda error:errors.append(str(error)))
        offline.set_content(snapshot.read_text(),wait_until='load')
        assert offline.locator('#mode-text').inner_text() == 'Saved snapshot'
        assert offline.locator('#market-price').inner_text() != '—'
        assert offline.locator('#notice').is_visible()
        assert offline.locator('#pause-view').is_hidden()
        offline.locator('[data-range="300000"]').click()
        offline.locator('[data-filter="verified"]').click()
        offline.locator('[data-filter="all"]').click()
        offline.evaluate("document.documentElement.style.scrollBehavior='auto';window.scrollTo(0,0)")
        offline.screenshot(path=str(output/'snapshot-desktop.png'),full_page=False)
        assert not await_requests,await_requests
        checks.append('Downloaded HTML renders and stays interactive offline, with zero network requests')
        context.set_offline(False)
        page.route('**/api/state',lambda route:route.abort())
        page.wait_for_function("document.querySelector('#mode-text').textContent === 'Monitor offline'",timeout=8000)
        assert page.locator('#bbo-status').inner_text() == 'Historical'
        assert page.locator('#depth-status').inner_text() == 'Historical'
        checks.append('Lost API connection marks displayed prices historical')
        assert not errors,errors
        checks.append('No browser JavaScript errors')
        browser.close()
    (output/'browser-checks.json').write_text(json.dumps(dict(status='passed',checks=checks,browser_errors=errors),indent=2)+'\n')
    print(json.dumps(dict(status='passed',checks=len(checks),artifacts=str(output)),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:3000')
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    run(args.url,args.output_dir.resolve())

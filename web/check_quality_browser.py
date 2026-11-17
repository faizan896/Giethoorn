#!/usr/bin/env python3
"""Check the saved quality view offline, including unavailable results."""
import argparse
import copy
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def run(html, failure, output):
    output.mkdir(parents=True, exist_ok=True)
    report = json.loads((html.parent/'quality-report.json').read_text())
    checks, errors, requests = [], [], []
    with sync_playwright() as driver:
        browser = driver.chromium.launch(executable_path='/usr/bin/chromium', headless=True)
        context = browser.new_context(viewport={'width':1440, 'height':1080}, accept_downloads=True)
        context.set_offline(True)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append(request.url))
        page.set_content(html.read_text(), wait_until='load')
        assert page.locator('#report-status').inner_text() == 'Archive verified · quality review complete'
        assert page.locator('#snapshots').inner_text() == format(report['totals']['retained_snapshots'], ',')
        assert page.locator('#rows tr').count() == len(report['runs'])
        checks.append('Verified source counts and all recording rows are displayed')
        page.locator('#filter').select_option('prefix')
        prefixes = sum(not row['finalized'] for row in report['runs'])
        assert page.locator('#rows tr').count() == prefixes
        if prefixes:
            assert page.locator('#child-tag').inner_text() == 'Recovered prefix'
            assert 'Unavailable' in page.locator('#facts').inner_text()
        page.locator('#filter').select_option('candidate')
        assert page.locator('#rows tr').count() == report['totals']['candidate_recordings']
        page.locator('#filter').select_option('all')
        child = report['runs'][-1]['run']
        page.locator('#search').fill(str(child).zfill(6))
        assert page.locator('#rows tr').count() == 1
        page.locator('#rows button').focus()
        page.keyboard.press('Enter')
        assert page.locator('#child-name').inner_text() == 'Run '+str(child).zfill(6)
        page.locator('#search').fill('no-such-recording')
        assert page.locator('#empty').is_visible() and not page.locator('#detail').is_visible()
        page.locator('#search').fill('')
        checks.append('Candidate/recovery filters, search, empty state and keyboard selection work')
        with page.expect_download() as pending:
            page.locator('#download').click()
        pending.value.save_as(output/'downloaded-report.json')
        assert json.loads((output/'downloaded-report.json').read_text()) == report
        assert (output/'downloaded-report.json').read_bytes() == (html.parent/'quality-report.json').read_bytes()
        checks.append('Offline JSON download preserves exact backend values')
        page.screenshot(path=str(output/'quality-desktop.png'), full_page=True)
        for width in (390, 320):
            page.set_viewport_size({'width':width, 'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), width
            page.screenshot(path=str(output/('quality-mobile-'+str(width)+'.png')), full_page=True)
        checks.append('Desktop and 390/320-pixel layouts avoid page overflow')
        page.close()
        bad = context.new_page()
        bad.on('pageerror', lambda error: errors.append(str(error)))
        bad.on('request', lambda request: requests.append(request.url))
        bad.set_content(failure.read_text(), wait_until='load')
        assert bad.locator('#report-status').inner_text() == 'Quality review unavailable'
        for element in ('snapshots', 'finalized', 'candidates', 'fast-time'):
            assert bad.locator('#'+element).inner_text() == 'Unavailable'
        assert bad.locator('#rows tr').count() == 0
        assert bad.locator('#diagnostic').is_visible()
        assert 'unavailable' in bad.locator('#partition-note').inner_text().lower()
        bad.screenshot(path=str(output/'quality-unverified.png'), full_page=True)
        checks.append('Refused native audit shows unavailable metrics rather than zero results')
        synthetic=copy.deepcopy(report)
        synthetic.update(origin='synthetic_fixture',precision_probe=2**63+123,
                         error='</script><img src="https://synthetic.invalid/" onerror="globalThis.qualityInjection=true">')
        source=html.read_text()
        boot=source.split('<script type="application/json" id="quality-data">',1)[1].split('</script>',1)[0]
        replacement=json.dumps(synthetic).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
        probe=context.new_page()
        probe.on('pageerror',lambda error:errors.append(str(error)))
        probe.on('request',lambda request:requests.append(request.url))
        probe.set_content(source.replace(boot,replacement,1),wait_until='load')
        assert probe.locator('#origin').inner_text()=='Synthetic fixture'
        assert probe.evaluate('globalThis.qualityInjection === undefined')
        assert probe.locator('#diagnostic').inner_text()==synthetic['error']
        with probe.expect_download() as pending:probe.locator('#download').click()
        pending.value.save_as(output/'synthetic-precision-report.json')
        assert json.loads((output/'synthetic-precision-report.json').read_text())==synthetic
        checks.append('Synthetic hostile text stays inert and JSON export preserves integers beyond JavaScript precision')
        assert not errors, errors
        assert not requests, requests
        browser.close()
    result = dict(checks=checks, errors=errors, network_requests=requests)
    (output/'browser-checks.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', type=Path, required=True)
    parser.add_argument('--failure-html', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    run(args.html, args.failure_html, args.output_dir)

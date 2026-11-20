#!/usr/bin/env python3
"""Check the portable cost report offline, including unresolved and failed cases."""
import argparse
import copy
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def run(html, output):
    output.mkdir(parents=True, exist_ok=True)
    report = json.loads((html.parent/'cost-report.json').read_text())
    source = html.read_text()
    errors, requests, checks = [], [], []
    with sync_playwright() as driver:
        browser = driver.chromium.launch(executable_path='/usr/bin/chromium', headless=True)
        context = browser.new_context(viewport={'width':1440,'height':1100}, accept_downloads=True)
        context.set_offline(True)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append(request.url))
        page.set_content(source, wait_until='load')
        assert page.locator('#status').inner_text() == 'Paper probe complete'
        assert page.locator('#verified').inner_text() == str(report['totals']['verified'])
        assert page.locator('#closed').inner_text() == str(report['totals']['closed'])
        assert page.locator('#unresolved').inner_text() == str(report['totals']['unresolved'])
        assert page.locator('#cases tr').count() == len(report['cases'])
        assert page.locator('#profiles tr').count() == len(report['policy']['profiles'])
        for outcome in ('closed', 'unresolved'):
            expected = [row for row in report['cases'] if row['status']=='verified' and row['metrics']['outcome']==outcome]
            page.locator('#filter').select_option(outcome)
            assert page.locator('#cases tr').count() == len(expected)
            if expected:
                page.locator('#cases button').first.click()
                assert expected[0]['metrics']['entry_quantity'] in page.locator('#facts').inner_text()
                if outcome == 'unresolved':
                    assert page.locator('#cases tr').first.locator('td').nth(6).inner_text() == 'Unavailable'
                    assert 'Unavailable' in page.locator('#facts').inner_text()
                    if expected[0]['metrics']['close_rejection_detail']:
                        assert expected[0]['metrics']['close_rejection_detail'] in page.locator('#facts').inner_text()
        checks.append('Counts match backend; unresolved cases retain exposure and no closed P&L')
        page.locator('#filter').select_option('all')
        page.locator('#child').select_option(str(report['selected_children'][0]))
        assert page.locator('#cases tr').count() == len(report['policy']['profiles'])
        page.locator('#child').select_option('all')
        page.locator('#filter').select_option('no_signal')
        assert page.locator('#empty').is_visible()
        page.locator('#filter').select_option('all')
        with page.expect_download() as pending:
            page.locator('#download').click()
        pending.value.save_as(output/'downloaded-cost.json')
        assert json.loads((output/'downloaded-cost.json').read_text()) == report
        checks.append('Recording/outcome filters, empty states, case inspection and exact raw JSON export work')
        page.screenshot(path=str(output/'cost-desktop.png'), full_page=True)
        for width in (390, 320):
            page.set_viewport_size({'width':width,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), width
            page.screenshot(path=str(output/f'cost-mobile-{width}.png'), full_page=True)
        checks.append('Desktop and 390/320-pixel layouts avoid page overflow')
        boot = source.split('<script type="application/json" id="cost-data">',1)[1].split('</script>',1)[0]
        bad = copy.deepcopy(report)
        bad.update(origin='synthetic_fixture', status='source_changed', quality_unchanged=False,
            error='</script><img src="https://synthetic.invalid/" onerror="globalThis.costInjection=true">',
            precision_probe=2**63+123)
        for row in bad['cases']:
            row.update(status='failed',metrics=None,reason='Synthetic source-change test')
        bad['totals'].update(verified=0,closed=0,unresolved=0,no_entry_fill=0,entry_rejected=0,failed=len(bad['cases']))
        encoded = json.dumps(bad).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
        failure = context.new_page()
        failure.on('pageerror', lambda error: errors.append(str(error)))
        failure.on('request', lambda request: requests.append(request.url))
        failure.set_content(source.replace(boot,encoded,1),wait_until='load')
        assert failure.locator('#origin').inner_text() == 'Synthetic fixture'
        assert failure.locator('#status').inner_text() == 'Paper probe incomplete'
        assert failure.locator('#error').inner_text() == bad['error']
        assert failure.locator('#verified').inner_text() == '0'
        assert failure.locator('#cases tr').first.locator('td').nth(6).inner_text() == 'Unavailable'
        failure.locator('#cases button').first.click()
        assert 'Synthetic source-change test' in failure.locator('#detail-reason').inner_text()
        assert failure.evaluate('globalThis.costInjection === undefined')
        with failure.expect_download() as pending:
            failure.locator('#download').click()
        pending.value.save_as(output/'synthetic-failure.json')
        assert json.loads((output/'synthetic-failure.json').read_text()) == bad
        failure.screenshot(path=str(output/'synthetic-unavailable.png'),full_page=True)
        checks.append('Failed cases show unavailable P&L; synthetic origin, hostile text and large-integer export stay correct')
        assert not errors, errors
        assert not requests, requests
        browser.close()
    result = dict(checks=checks, errors=errors, network_requests=requests)
    (output/'browser-checks.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args = parser.parse_args()
    run(args.html, args.output_dir)

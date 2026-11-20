#!/usr/bin/env python3
"""Check the offline policy view against native results and explicit UI fixtures."""
import argparse
import copy
import json
from pathlib import Path
import sys

from playwright.sync_api import sync_playwright

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
from ops import proxy_policy_local as RUN


def run(html, output):
    output.mkdir(parents=True, exist_ok=True)
    source = html.read_text()
    report = json.loads((html.parent / 'policy-report.json').read_text())
    errors, requests, checks = [], [], []

    def expected(value):
        return 'Unavailable' if value is None else str(value)

    def fact(page, identity, label):
        return page.locator('#' + identity + ' div').filter(
            has=page.locator('dt', has_text=label)).locator('dd').inner_text()

    boot = source.split('<script type="application/json" id="policy-data">', 1)[1].split('</script>', 1)[0]

    def with_report(value):
        encoded = json.dumps(value).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
        return source.replace(boot, encoded, 1)

    with sync_playwright() as driver:
        browser = driver.chromium.launch(executable_path='/usr/bin/chromium', headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1100}, accept_downloads=True)
        context.set_offline(True)

        def page_for(contents):
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda request: requests.append(request.url))
            page.set_content(contents, wait_until='load')
            return page

        page = page_for(source)
        assert page.locator('#status').inner_text() == 'Causal paper policy verified'
        assert page.locator('#verified').inner_text() == str(report['totals']['verified'])
        assert page.locator('#entries').inner_text() == str(report['totals']['entry_requests'])
        assert page.locator('#closes').inner_text() == str(report['totals']['close_requests'])
        assert page.locator('#cases tr').count() == len(report['cases'])
        for i, row in enumerate(report['cases']):
            page.locator('#case').select_option(str(i))
            policy = row['policy']
            metrics, receipt = policy['metrics'], policy['close_compilation']
            assert fact(page, 'decision', 'Own position at decision') == expected(receipt['known_position'])
            assert fact(page, 'decision', 'Requested close quantity') == expected(metrics['close_requested_quantity'])
            assert fact(page, 'decision', 'Working orders at decision') == expected(receipt['working_orders'])
            assert fact(page, 'ending', 'Entry filled') == expected(metrics['entry_quantity'])
            assert fact(page, 'ending', 'Close filled') == expected(metrics['close_quantity'])
            assert fact(page, 'ending', 'Ending assumed position') == metrics['ending_position_quantity']
            assert fact(page, 'ending', 'Assumed fees') == metrics['fees']
            assert fact(page, 'ending', 'Conditional closed P&L') == expected(metrics['conditional_closed_pnl'])
            assert fact(page, 'ending', 'Actual execution') == 'Unknown'
            assert page.locator('#orders tr').count() == len(policy['orders'])
            if policy['causal_prefix_audit']['decision_available']:
                assert fact(page, 'decision', 'Native control prefix') == (
                    'Exact match · ' + str(policy['causal_prefix_audit']['prefix_records']) + ' records')
        checks.append('Every native case displays its own decision position, close size, exact costs, prefix and ending state')
        page.locator('#case').select_option('0')
        with page.expect_download() as pending:
            page.locator('#download').click()
        pending.value.save_as(output / 'downloaded-policy.json')
        assert json.loads((output / 'downloaded-policy.json').read_text()) == report
        page.screenshot(path=str(output / 'policy-desktop.png'), full_page=True)
        for width in (390, 320):
            page.set_viewport_size({'width': width, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), width
            page.screenshot(path=str(output / f'policy-mobile-{width}.png'), full_page=True)
        checks.append('Exact JSON export, case selection and desktop/390/320-pixel layouts work offline')

        # These are explicitly synthetic rendering fixtures; native mechanics are
        # exercised separately by test_proxy_policy_native.py.
        synthetic = copy.deepcopy(report)
        synthetic.update(origin='synthetic_fixture', cases=[])
        for name in ('partial', 'pending-entry', 'no-fill', 'missing-decision', 'pending-exit'):
            row = copy.deepcopy(report['cases'][0])
            row['case_id'] = 'synthetic-' + name
            policy = row['policy']
            metrics, receipt = policy['metrics'], policy['close_compilation']
            policy['orders'][0]['assumed_fill_price'] = '100.020001000000000001'
            if name == 'partial':
                receipt['known_position'] = '0.0005'
                metrics.update(entry_quantity='0.0005', close_requested_quantity='0.0005', close_quantity='0.00025',
                    ending_position_quantity='0.00025', conditional_closed_pnl=None, outcome='open_exposure')
                policy['orders'][1]['order']['quantity'] = '0.0005'
                policy['orders'][1]['native_final_order']['filled_quantity'] = '0.00025'
            else:
                metrics.update(conditional_closed_pnl=None, close_requested_quantity=None,
                    close_quantity=None, close_outcome=None, pending_order_ids=[])
                policy['orders'] = policy['orders'][:1]
                policy['control_reused'] = True
                if name == 'pending-entry':
                    receipt.update(known_position='0', working_orders=1, status='unresolved_entry')
                    metrics.update(close_decision_status='unresolved_entry', ending_position_quantity='0.001', outcome='open_exposure')
                elif name == 'no-fill':
                    receipt.update(known_position='0', working_orders=0, status='flat_no_close')
                    metrics.update(entry_quantity='0', close_decision_status='flat_no_close',
                        ending_position_quantity='0', fees='0', outcome='no_entry_fill')
                elif name == 'missing-decision':
                    receipt.update(known_position=None, working_orders=None, risk_at_decision=None,
                        decision=None, status='missing_decision')
                    policy['causal_prefix_audit'].update(decision_available=False, prefix_records=None, prefix_sha256=None)
                    metrics.update(close_decision_status='missing_decision', ending_position_quantity='0.001', outcome='open_exposure')
                else:
                    policy['orders'] = copy.deepcopy(report['cases'][0]['policy']['orders'])
                    policy['orders'][1]['native_final_order']['filled_quantity'] = '0'
                    policy['orders'][1]['outcome'] = 'pending_at_source_end'
                    policy['control_reused'] = False
                    metrics.update(close_requested_quantity='0.001', close_quantity='0',
                        ending_position_quantity='0.001', pending_order_ids=['close'], outcome='open_exposure')
            synthetic['cases'].append(row)
        synthetic['totals'] = RUN.totals(synthetic['cases'])
        golden = page_for(with_report(synthetic))
        assert golden.locator('#origin').inner_text() == 'Synthetic source'
        assert fact(golden, 'decision', 'Own position at decision') == '0.0005'
        assert fact(golden, 'decision', 'Requested close quantity') == '0.0005'
        assert fact(golden, 'ending', 'Close filled') == '0.00025'
        assert fact(golden, 'ending', 'Ending assumed position') == '0.00025'
        assert '100.020001000000000001' in golden.locator('#orders').inner_text()
        for i, row in enumerate(synthetic['cases']):
            golden.locator('#case').select_option(str(i))
            assert fact(golden, 'ending', 'Conditional closed P&L') == 'Unavailable'
            if i == 1:
                assert fact(golden, 'decision', 'Own position at decision') == '0'
                assert fact(golden, 'ending', 'Ending assumed position') == '0.001'
                assert fact(golden, 'decision', 'Requested close quantity') == 'Unavailable'
            elif i == 2:
                assert fact(golden, 'ending', 'Entry filled') == '0'
                assert fact(golden, 'ending', 'Assumed fees') == '0'
            elif i == 3:
                assert fact(golden, 'decision', 'Own position at decision') == 'Unavailable'
                assert fact(golden, 'decision', 'Native control prefix') == 'No decision · entry-only control retained'
            elif i == 4:
                assert fact(golden, 'ending', 'Pending assumed orders') == 'close'
                assert fact(golden, 'ending', 'Close filled') == '0'
        checks.append('Synthetic partial, pending, no-fill and missing-decision states retain distinct decision/ending positions and unavailable P&L')

        changed = copy.deepcopy(synthetic)
        changed.update(status='source_changed', input_unchanged=False, precision_probe=2**63 + 123,
            error='</script><img src="https://synthetic.invalid/" onerror="globalThis.policyInjection=true">')
        for row in changed['cases']:
            row.update(status='unavailable', policy=None, reason='Synthetic changed evidence')
        changed['totals'] = RUN.totals(changed['cases'])
        failure = page_for(with_report(changed))
        assert failure.locator('#status').inner_text() == 'Causal paper policy incomplete'
        assert fact(failure, 'decision', 'Own position at decision') == 'Unavailable'
        assert fact(failure, 'ending', 'Conditional closed P&L') == 'Unavailable'
        assert fact(failure, 'ending', 'Ending assumed position') == 'Unavailable'
        assert failure.locator('#orders tr').count() == 0
        assert failure.locator('#error').inner_text() == changed['error']
        assert failure.evaluate('globalThis.policyInjection === undefined')
        with failure.expect_download() as pending:
            failure.locator('#download').click()
        pending.value.save_as(output / 'failed-policy.json')
        assert json.loads((output / 'failed-policy.json').read_text()) == changed
        checks.append('Changed evidence hides policy metrics; hostile text stays inert and large integers export exactly')
        assert not errors, errors
        assert not requests, requests
        browser.close()
    result = dict(checks=checks, errors=errors, network_requests=requests)
    (output / 'browser-checks.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    run(args.html, args.output_dir)

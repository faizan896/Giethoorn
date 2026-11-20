#!/usr/bin/env python3
"""Check the saved quote-opportunity report offline, without new policy execution."""
import argparse
import copy
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def run(html,output):
    output.mkdir(parents=True,exist_ok=True)
    source=html.read_text()
    report=json.loads((html.parent/'expiry-report.json').read_text())
    errors,requests,checks=[],[],[]
    with sync_playwright() as driver:
        browser=driver.chromium.launch(executable_path='/usr/bin/chromium',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1100},accept_downloads=True)
        context.set_offline(True)
        page=context.new_page()
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:requests.append(r.url))
        page.set_content(source,wait_until='load')
        assert page.locator('#status').inner_text()=='Quote-opportunity review complete'
        assert page.locator('#verified').inner_text()==str(report['totals']['verified'])
        assert page.locator('#orders-count').inner_text()==str(report['totals']['orders'])
        assert page.locator('#orders tr').count()==report['totals']['orders']
        expired=[o for c in report['cases'] for o in c['orders'] if o['classification'].startswith('expired')]
        page.locator('#filter').select_option('expired')
        assert page.locator('#orders tr').count()==len(expired)
        if expired:
            page.locator('#orders button').first.click()
            assert page.locator('#window').is_visible()
            assert page.locator('#timeline tr').count()==len(expired[0]['timeline'])
            assert page.locator('#facts').inner_text().endswith('ms') or 'Unavailable' in page.locator('#facts').inner_text()
            assert 'unknown' in page.locator('#exposure').inner_text()
        checks.append('Backend order counts, expiry filter, boundary window and source timeline render correctly')
        page.locator('#filter').select_option('all')
        child=report['selected_children'][0]
        page.locator('#child').select_option(str(child))
        assert page.locator('#orders tr').count()==sum(len(c['orders']) for c in report['cases'] if c['child']==child)
        page.locator('#child').select_option('all')
        page.locator('#filter').select_option('unavailable')
        assert page.locator('#empty').is_visible()
        page.locator('#filter').select_option('all')
        with page.expect_download() as pending:page.locator('#download').click()
        pending.value.save_as(output/'downloaded-expiry.json')
        assert json.loads((output/'downloaded-expiry.json').read_text())==report
        page.screenshot(path=str(output/'expiry-desktop.png'),full_page=True)
        for width in (390,320):
            page.set_viewport_size({'width':width,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'),width
            page.screenshot(path=str(output/f'expiry-mobile-{width}.png'),full_page=True)
        checks.append('Recording filter, empty states, exact JSON export and 390/320-pixel layouts work')
        boot=source.split('<script type="application/json" id="expiry-data">',1)[1].split('</script>',1)[0]
        bad=copy.deepcopy(report)
        bad.update(origin='synthetic_fixture',status='source_changed',input_unchanged=False,
            error='</script><img src="https://synthetic.invalid/" onerror="globalThis.expiryInjection=true">',precision_probe=2**63+123)
        for case in bad['cases']:case.update(status='unavailable',orders=[],reason='Synthetic evidence mutation')
        bad['totals'].update(verified=0,unavailable=len(bad['cases']),orders=0,classifications={})
        encoded=json.dumps(bad).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
        failure=context.new_page()
        failure.on('pageerror',lambda e:errors.append(str(e)))
        failure.on('request',lambda r:requests.append(r.url))
        failure.set_content(source.replace(boot,encoded,1),wait_until='load')
        assert failure.locator('#origin').inner_text()=='Synthetic fixture'
        assert failure.locator('#status').inner_text()=='Quote-opportunity review incomplete'
        assert failure.locator('#error').inner_text()==bad['error']
        assert failure.locator('#orders tr').first.locator('td').nth(3).inner_text()=='Unavailable'
        failure.locator('#orders button').first.click()
        assert failure.locator('#detail-reason').inner_text()=='Synthetic evidence mutation'
        assert failure.evaluate('globalThis.expiryInjection === undefined')
        with failure.expect_download() as pending:failure.locator('#download').click()
        pending.value.save_as(output/'synthetic-unavailable.json')
        assert json.loads((output/'synthetic-unavailable.json').read_text())==bad
        checks.append('Failed evidence has no invented timestamps; hostile text is inert and large JSON integers survive export')
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

#!/usr/bin/env python3
"""Check the saved study without network access or computing new partitions."""
import argparse
import copy
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def run(html, output):
    output.mkdir(parents=True,exist_ok=True)
    report=json.loads((html.parent/'study-report.json').read_text())
    errors,requests,checks=[],[],[]
    with sync_playwright() as driver:
        browser=driver.chromium.launch(executable_path='/usr/bin/chromium',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1100},accept_downloads=True)
        context.set_offline(True)
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:requests.append(r.url))
        page.set_content(html.read_text(),wait_until='load')
        metrics=report['metrics']
        assert page.locator('#status').inner_text()=='development study complete'
        assert page.locator('#signals').inner_text()==format(metrics['signals'],',')
        assert page.locator('#labels').inner_text()==format(metrics['labelled_signals'],',')
        assert page.locator('#baselines tr').count()==3
        baseline=page.locator('#baselines tr').first.inner_text()
        assert str(metrics['signal_hits'])+' / '+str(metrics['labelled_signals']) in baseline
        assert page.locator('#partitions tr').count()==3
        for group in ('validation','retrospective_test'):
            page.locator('#filter').select_option(group)
            assert page.locator('#rows tr').count()==len(report['partitions'][group]['children'])
            assert 'not run' in page.locator('#rows').inner_text()
            assert 'Unavailable' in page.locator('#rows').inner_text()
        checks.append('Scores use the backend denominator and unrun partitions stay unavailable')
        page.locator('#filter').select_option('all')
        assert page.locator('#rows tr').count()==len(report['rows'])
        page.locator('#search').fill('no-such-child');assert page.locator('#empty').is_visible()
        page.locator('#search').fill('');page.locator('#filter').select_option('development')
        with page.expect_download() as pending:page.locator('#download').click()
        pending.value.save_as(output/'downloaded-study.json')
        assert json.loads((output/'downloaded-study.json').read_text())==report
        checks.append('Filters, empty states and offline JSON export work')
        page.screenshot(path=str(output/'study-desktop.png'),full_page=True)
        for width in (390,320):
            page.set_viewport_size({'width':width,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'),width
            page.screenshot(path=str(output/f'study-mobile-{width}.png'),full_page=True)
        checks.append('Desktop and 390/320-pixel layouts avoid page overflow')
        source=html.read_text()
        boot=source.split('<script type="application/json" id="study-data">',1)[1].split('</script>',1)[0]
        bad=copy.deepcopy(report);bad.update(origin='synthetic_fixture',status='analysis_failed',metrics=None,
            quality_unchanged=False,error='</script><img src="https://synthetic.invalid/" onerror="globalThis.studyInjection=true">',
            precision_probe=2**63+123)
        for row in bad['rows']:row.update(status='not_run',metrics=None)
        for part in bad['partitions'].values():part.update(status='not_run',metrics=None)
        encoded=json.dumps(bad).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
        failure=context.new_page();failure.on('pageerror',lambda e:errors.append(str(e)))
        failure.on('request',lambda r:requests.append(r.url))
        failure.set_content(source.replace(boot,encoded,1),wait_until='load')
        assert failure.locator('#origin').inner_text()=='Synthetic fixture'
        assert failure.locator('#status').inner_text()=='Study results unavailable'
        for element in ('signals','labels','hit-rate','mid-move'):
            assert failure.locator('#'+element).inner_text()=='Unavailable'
        assert failure.locator('#error').inner_text()==bad['error']
        assert failure.evaluate('globalThis.studyInjection === undefined')
        with failure.expect_download() as pending:failure.locator('#download').click()
        pending.value.save_as(output/'synthetic-failure.json')
        assert json.loads((output/'synthetic-failure.json').read_text())==bad
        failure.screenshot(path=str(output/'synthetic-unavailable.png'),full_page=True)
        checks.append('Synthetic failures show no zero scores; hostile text is inert and large JSON integers survive export')
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

#!/usr/bin/env python3
"""Exercise the saved sensitivity report offline and optional loopback routing."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

PROJECT=Path(__file__).resolve().parent.parent
SPEC=importlib.util.spec_from_file_location('batch_view',PROJECT/'ops/paper_batch.py')
MODULE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def run(html, output, url=None):
    output.mkdir(parents=True,exist_ok=True)
    report=json.loads((html.parent/'batch-report.json').read_text())
    checks,errors,requests=[],[],[]
    with sync_playwright() as driver:
        browser=driver.chromium.launch(executable_path='/usr/bin/chromium',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1080})
        context.set_offline(True)
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda request:requests.append(request.url))
        page.set_content(html.read_text(),wait_until='load')
        assert 'uncalibrated' in page.locator('.notice').inner_text()
        assert '24-hour collection gate remains unverified' in page.locator('.notice').inner_text()
        assert page.locator('#verified-count').inner_text()==f"{report['counts']['verified']} / {len(report['cases'])}"
        assert page.locator('#case-rows tr').count()==len(report['cases'])
        assert page.locator('#source-pairs').inner_text().endswith('Not verified')
        checks.append('Explicit simulated execution, uncalibrated assumptions, source origin and pending collection gate')
        dataset=report['datasets'][0]['id']
        profile=report['profiles'][1]['id']
        page.locator('#dataset-filter').select_option(dataset)
        assert page.locator('#case-rows tr').count()==len(report['profiles'])
        page.locator('#profile-filter').select_option(profile)
        assert page.locator('#case-rows tr').count()==1
        chosen=next(c for c in report['cases'] if c['dataset_id']==dataset and c['profile_id']==profile)
        assert page.locator('#detail-title').inner_text()==report['profiles'][1]['label']
        assert page.locator('#source-hash').inner_text()==chosen['recording_sha256']
        assert page.locator('#plan-hash').inner_text()==chosen['fixed_plan_sha256']
        checks.append('Recording/profile filters select the correct paired case and exact source/plan fingerprints')
        text=page.locator('#detail-pnl').inner_text().replace('−','-').replace('$','').replace(',','')
        assert text==chosen['metrics']['net_pnl']
        delta=next(p for p in report['comparisons'] if p['case_id']==chosen['id'])['deltas']['net_pnl']
        shown=page.locator('#delta-pairs .pair').first.locator('dd').inner_text().replace('−','-').replace('$','').replace(',','').lstrip('+')
        assert shown==delta
        checks.append('Displayed paper P&L and paired deltas preserve backend decimal strings')
        page.locator('#dataset-filter').select_option('all');page.locator('#profile-filter').select_option('all')
        page.locator('#case-rows button').last.click()
        assert page.locator('#case-rows button[aria-pressed="true"]').count()==1
        page.locator('#case-rows button').first.focus();page.keyboard.press('Enter')
        assert page.locator('#case-rows button').first.get_attribute('aria-pressed')=='true'
        page.locator('#status-filter').select_option('failed')
        assert page.locator('#empty').is_visible()
        assert not page.locator('#case-detail').is_visible()
        page.locator('#status-filter').select_option('all')
        with page.expect_download() as pending:
            page.locator('#download').click()
        download=pending.value;download.save_as(output/'downloaded-report.json')
        assert json.loads((output/'downloaded-report.json').read_text())==report
        checks.append('Mouse/keyboard selection, empty filter states and JSON download work offline')
        page.screenshot(path=str(output/'batch-desktop.png'),full_page=True)
        page.screenshot(path=str(output/'batch-preview.png'))
        for width in [320,390,768,1024,1440]:
            page.set_viewport_size({'width':width,'height':844})
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),width
            if width==390:page.screenshot(path=str(output/'batch-mobile.png'),full_page=True)
        checks.append('320–1440 pixel desktop/mobile layouts fit without page overflow')
        fixture=copy.deepcopy(report)
        fixture['label']='Synthetic UI failure fixture'
        for d in fixture['datasets']:d['origin']='synthetic_fixture';d['label']='Synthetic '+d['id']
        fixture['cases'][0].update(status='failed',metrics=None,reason='Synthetic timeout fixture: no result available.')
        fixture['counts']['verified']-=1;fixture['counts']['failed']+=1
        fixture['comparisons']=MODULE.comparisons(fixture['cases'],fixture['baseline_profile'])
        fixture['status']='completed_with_failures'
        page=context.new_page()
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda request:requests.append(request.url))
        page.set_content(MODULE.render_report(fixture),wait_until='load')
        assert page.locator('#detail-pnl').inner_text()=='—'
        assert 'Synthetic timeout fixture' in page.locator('#detail-reason').inner_text()
        assert 'Synthetic fixture' in page.locator('#source-pairs').inner_text()
        assert 'Both case and baseline must verify' in page.locator('#delta-pairs').inner_text()
        page.locator('#status-filter').select_option('failed')
        assert page.locator('#case-rows tr').count()==1
        assert 'Failed' in page.locator('#case-rows').inner_text()
        checks.append('Synthetic failure fixture stays visible with blank metrics and unavailable baseline comparisons')
        assert requests==[],requests
        assert errors==[],errors
        checks.append('Portable report makes zero network requests and has no browser errors')
        if url:
            online=browser.new_context(viewport={'width':1440,'height':1080});live=online.new_page()
            live.on('pageerror',lambda e:errors.append(str(e)))
            response=live.goto(url,wait_until='networkidle');assert response.status==200
            assert live.locator('#case-rows tr').count()==len(report['cases'])
            assert live.locator('.server-link').first.is_visible()
            live.goto(url.rsplit('/',1)[0]+'/',wait_until='networkidle')
            assert live.locator('#batch-nav').is_visible()
            assert live.locator('#paper-nav').is_visible()
            assert live.locator('#gate-badge').inner_text()=='Incomplete'
            for width in [320,390,768,1440]:
                live.set_viewport_size({'width':width,'height':844})
                assert not live.evaluate('document.documentElement.scrollWidth>innerWidth'),width
                if width<=390:
                    assert live.locator('#batch-mobile').is_visible()
                    assert live.locator('#paper-mobile').is_visible()
            response=live.request.get(url.rsplit('/',1)[0]+'/snapshot.html')
            assert response.status==200
            saved=context.new_page()
            saved.on('pageerror',lambda e:errors.append(str(e)))
            saved.on('request',lambda request:requests.append(request.url))
            saved.set_content(response.text(),wait_until='load')
            assert saved.locator('#mode-text').inner_text()=='Saved snapshot'
            for id in ['batch-nav','batch-mobile','paper-nav','paper-mobile']:
                assert not saved.locator('#'+id).is_visible()
            assert not requests,requests
            assert errors==[],errors
            checks.append('Loopback report, stopped monitor/mobile navigation and offline snapshots with hidden server links')
            online.close()
        context.close();browser.close()
    result=dict(status='passed',checks=checks,errors=errors,offline_requests=requests)
    (output/'browser-results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--url')
    args=parser.parse_args()
    run(args.html,args.output_dir,args.url)

#!/usr/bin/env python3
"""Optional offline Playwright acceptance for retained R002 diagnostic reports."""
import argparse
import copy
import json
from pathlib import Path

try:
    from . import quality_local as QUALITY
except ImportError:
    import quality_local as QUALITY


def main():
    from playwright.sync_api import sync_playwright
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture-json',type=Path,required=True)
    parser.add_argument('--no-signal-json',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parent.parent
    args.output_dir.mkdir(mode=0o700)
    template=(root/'web/momentum-explain.html').read_text();theme=(root/'web/theme.css').read_text()
    fixture=json.loads(args.fixture_json.read_text());idle=json.loads(args.no_signal_json.read_text())
    assert fixture['origin']=='synthetic_fixture' and fixture.get('synthetic_component_fixture') is True
    errors=[];network=[];checks=[]

    def save(name,value):
        html=QUALITY.render(value,template,theme)
        (args.output_dir/(name+'.html')).write_text(html)
        return html

    def checked(name):checks.append(name)

    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        context=browser.new_context(viewport=dict(width=1440,height=1000),accept_downloads=True)
        page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('request',lambda request:network.append(request.url) if request.url.startswith(('http:','https:')) else None)
        def load(html):
            # Managed cloud Chrome disallows file: navigation. Check the same
            # self-contained document in memory without changing that policy.
            page.goto('about:blank');page.set_content(html)
        load(save('native-fixture',fixture));page.wait_for_selector('#orders tr')
        assert page.locator('#slots').inner_text()==str(len(fixture['cases']))
        net=fixture['cases'][0]['explanation']['closed_decomposition']['closed_net_usdc']
        assert net in page.locator('#identity').inner_text()
        assert 'Exact identity verified' in page.locator('#identity').inner_text()
        assert page.locator('#orders tr').count()==3
        checked('exact_native_partial_close_identity')
        page.screenshot(path=str(args.output_dir/'desktop.png'),full_page=True)
        for child,word in [(2,'source ended before close window'),(3,'remaining assumed capacity limited'),(4,'not marketable'),(5,'No original signal')]:
            page.select_option('#case',label=f'run-{child:06d}--baseline')
            assert word in page.locator('#window' if child in (2,5) else '#orders').inner_text()
            assert 'Unavailable' in page.locator('#ending').inner_text()
            if child in (2,3):assert 'Closed decomposition unavailable' in page.locator('#identity').inner_text()
        checked('open_no_fill_no_signal_and_capacity_states')
        page.select_option('#case',label='run-000003--baseline');page.select_option('#profile','liquidity-stress')
        assert page.locator('#case option:checked').inner_text()=='run-000003--liquidity-stress'
        checked('profile_selection_preserves_recording')
        for width in (390,320):
            page.set_viewport_size(dict(width=width,height=900))
            assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        page.screenshot(path=str(args.output_dir/'mobile.png'),full_page=True)
        checked('desktop_and_390_320_pixel_layout')

        hostile=copy.deepcopy(fixture);evil='</script><img src="https://invalid.example/x" onerror="window.__pwned=1">'
        hostile['error']=evil;hostile['browser_fixture_ns']='900719925474099312345678901'
        hostile['cases'][0]['explanation']['orders'][0]['native_rejection_detail']=evil
        load(save('hostile',hostile))
        assert page.locator('#error').inner_text()==evil
        assert page.locator('img').count()==0 and page.evaluate('window.__pwned') is None
        with page.expect_download() as download_info:page.click('#download')
        download=download_info.value;download.save_as(str(args.output_dir/'export.json'))
        assert json.loads((args.output_dir/'export.json').read_text())==hostile
        checked('inert_hostile_text_and_exact_raw_json_export')

        invalid=copy.deepcopy(fixture);invalid['input_unchanged']=False;invalid['status']='invalid'
        load(save('changed-input',invalid))
        assert page.locator('#status').inner_text()=='Diagnostic evidence not admitted'
        assert page.locator('#identities').inner_text()=='Unavailable'
        assert page.locator('#orders tr').count()==page.locator('#fills tr').count()==0
        assert net not in page.locator('body').inner_text()
        checked('failed_verification_hides_financial_analysis')

        load(save('no-signal',idle))
        assert page.locator('#status').inner_text()=='Original evidence independently revalidated'
        assert page.locator('#baseline tr').count()==0
        assert 'No original signal' in page.locator('#window').inner_text()
        checked('full_bundle_no_signal_report')

        stress=copy.deepcopy(fixture);stress['selected_children']=list(range(1,80));stress['cases']=[]
        stress['verification_scope']='Synthetic 474-slot layout fixture only; repeated component data, no research result.'
        for child in stress['selected_children']:
            for profile in fixture['original_totals']['profiles']:
                old=next(c for c in fixture['cases'] if c['child']==1+(child-1)%5 and c['profile']==profile['profile'])
                case=copy.deepcopy(old);case.update(child=child,case_id=f'run-{child:06d}--{profile["profile"]}')
                stress['cases'].append(case)
        for profile in stress['original_totals']['profiles']:
            rows=[c for c in stress['cases'] if c['profile']==profile['profile']]
            profile.update(cases=len(rows),no_signal=sum(c['original_status']=='no_signal' for c in rows),closed_cycle_net=None)
            for key,outcome in [('closed','closed_under_assumptions'),('unresolved','open_exposure'),('no_fills','no_fills')]:
                profile[key]=sum(c['explanation'] is not None and c['explanation']['outcome']==outcome for c in rows)
        for key in ('cases','no_signal','closed','unresolved','no_fills'):
            stress['original_totals'][key]=sum(p[key] for p in stress['original_totals']['profiles'])
        page.set_viewport_size(dict(width=1440,height=1000));load(save('474-slots',stress))
        assert page.locator('#slots').inner_text()=='474' and page.locator('#cases tr').count()==79
        page.select_option('#case',label='run-000079--baseline');page.select_option('#profile','slippage-stress')
        assert page.locator('#case option:checked').inner_text()=='run-000079--slippage-stress'
        for width in (390,320):
            page.set_viewport_size(dict(width=width,height=900))
            assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        checked('474_slot_complete_cohort_layout')
        browser.close()
    assert not errors and not network,(errors,network)
    receipt=dict(status='passed',checks=checks,browser_errors=errors,network_requests=network,
        input_method='Self-contained HTML loaded in memory; managed cloud file navigation is blocked.')
    (args.output_dir/'browser-check.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()

#!/usr/bin/env python3
"""Offline checks of residual sizing, unresolved coverage and honest comparisons."""
import argparse
import copy
import json
from pathlib import Path
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from ops import bounded_exit_core as CORE


def run(html, native_fixture, output):
    output.mkdir(parents=True,exist_ok=True)
    source=html.read_text(); report=json.loads((html.parent/'bounded-exit-report.json').read_text())
    fixture=json.loads(native_fixture.read_text())
    assert fixture['origin']=='synthetic_fixture'
    errors,requests,checks=[],[],[]
    expected=lambda value:'Unavailable' if value is None else str(value)
    def fact(page,identity,label):
        return page.locator('#'+identity+' div').filter(has=page.locator('dt',has_text=label)).locator('dd').inner_text()
    boot=source.split('<script type="application/json" id="bounded-exit-data">',1)[1].split('</script>',1)[0]
    def with_report(value):
        encoded=json.dumps(value).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
        return source.replace(boot,encoded,1)
    def summarize(value):
        value['totals'],value['control_totals'],value['comparisons']=CORE.summarize(value['cases'])
    with sync_playwright() as driver:
        browser=driver.chromium.launch(executable_path='/usr/bin/chromium',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1100},accept_downloads=True)
        context.set_offline(True)
        def page_for(contents):
            page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('request',lambda request:requests.append(request.url));page.set_content(contents,wait_until='load');return page
        page=page_for(source)
        assert page.locator('#status').inner_text()=='Bounded exit experiment complete'
        assert page.locator('#planned').inner_text()==str(report['totals']['cases'])
        assert page.locator('#verified').inner_text()==str(report['totals']['verified'])
        for i,p in enumerate(report['totals']['profiles']):
            old=report['control_totals']['profiles'][i];cells=page.locator('#profiles tr').nth(i).locator('td')
            assert cells.nth(6).inner_text()==expected(old['closed_cycle_net'])
            assert cells.nth(7).inner_text()==expected(p['closed_cycle_net'])
        for i,row in enumerate(report['cases']):
            page.locator('#profile').select_option(row['profile']);page.locator('#case').select_option(str(i))
            p=row['policy'];m=p['metrics'];old=row['control']['metrics']
            assert fact(page,'control','Conditional closed P&L')==expected(old['conditional_closed_pnl'])
            assert fact(page,'ending','Conditional closed P&L')==expected(m['conditional_closed_pnl'])
            assert fact(page,'ending','Assumed fees')==m['fees']
            assert fact(page,'ending','Ending position')==m['ending_position_quantity']
            assert fact(page,'decision','Known residual position')==expected(p['retry_compilation']['known_position'])
            assert fact(page,'decision','Requested extra close')==expected(m['retry_requested_quantity'])
            assert fact(page,'ending','Actual execution')=='Unknown'
            assert page.locator('#orders tr').count()==len(p['orders'])
        checks.append('All real software-sample controls, new cases and separate profile totals retain exact backend strings')
        page.locator('#profile').select_option('baseline');page.locator('#case').select_option('0')
        with page.expect_download() as pending:page.locator('#download').click()
        pending.value.save_as(output/'downloaded-bounded-exit.json')
        assert json.loads((output/'downloaded-bounded-exit.json').read_text())==report
        page.screenshot(path=str(output/'bounded-exit-desktop.png'),full_page=True)
        for width in (390,320):
            page.set_viewport_size({'width':width,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'),width
            page.screenshot(path=str(output/f'bounded-exit-mobile-{width}.png'),full_page=True)
        checks.append('Exact export and desktop/390/320-pixel selection/layout checks pass offline')

        golden=copy.deepcopy(report);golden.update(origin='synthetic_fixture',selected_children=[1],
            previously_cost_probed_children=[],cases=[fixture['case']]);summarize(golden)
        native=page_for(with_report(golden))
        assert native.locator('#origin').inner_text()=='Synthetic source'
        assert fact(native,'decision','Known residual position')=='0.00075'
        assert fact(native,'decision','Requested extra close')=='0.00075'
        assert fact(native,'decision','First-close native status')=='cancelled'
        assert fact(native,'decision','Cancellation pending')=='false'
        assert fact(native,'decision','Working orders')=='0'
        assert fact(native,'ending','Extra close filled')=='0.00075'
        assert fact(native,'ending','Total closes filled')=='0.00100'
        assert fact(native,'ending','Ending position')=='0'
        assert fact(native,'ending','Conditional closed P&L')=='-0.000140000001'
        assert fact(native,'control','Conditional closed P&L')=='Unavailable'
        assert fact(native,'comparison','Conditional closed-net delta')=='Unavailable'
        assert native.locator('#orders tr').count()==3
        native.screenshot(path=str(output/'bounded-exit-native-partial-fixture.png'),full_page=True)
        checks.append('Same-image native partial-close fixture shows exact residual retry and no fabricated return improvement')

        large=copy.deepcopy(golden);large.update(selected_children=list(range(1,80)),cases=[],status='incomplete')
        for child in large['selected_children']:
            for profile in CORE.ECONOMICS.PROFILES:
                row=copy.deepcopy(fixture['case']);row.update(child=child,profile=profile['id'],
                    case_id=f'run-{child:06d}--{profile["id"]}',previously_cost_probed=child<5)
                large['cases'].append(row)
        row=large['cases'][0];m=row['policy']['metrics']
        m.update(conditional_closed_pnl=None,ending_position_quantity='0.0005',retry_quantity='0.00025',
            total_close_quantity='0.00050',retry_outcome='partial_fill_cancelled',outcome='open_exposure')
        row['policy']['orders'][-1].update(filled_quantity='0.00025',outcome='partial_fill_cancelled')
        large['cases'][6].update(status='no_signal',policy=None,control=None,reason='Synthetic no signal')
        large['cases'][12].update(status='unavailable',policy=None,control=None,reason='Synthetic admission failure')
        row=large['cases'][18];p=row['policy'];m=p['metrics']
        m.update(conditional_closed_pnl=None,ending_position_quantity='0.00075',pending_order_ids=['close-retry'],
            retry_quantity='0',retry_outcome='pending_at_source_end',outcome='pending_at_source_end',assumed_fills=2)
        p['orders'][-1].update(filled_quantity='0',outcome='pending_at_source_end')
        row=large['cases'][24];p=row['policy'];m=p['metrics']
        p['retry_compilation'].update(status='risk_halted',risk_at_decision=dict(halted=True))
        m.update(conditional_closed_pnl=None,ending_position_quantity='0.00075',retry_requested_quantity=None,
            retry_quantity=None,retry_outcome=None,retry_decision_status='risk_halted',outcome='open_exposure',assumed_fills=2)
        p['orders']=p['orders'][:2]
        summarize(large)
        scaled=page_for(with_report(large))
        assert scaled.locator('#planned').inner_text()=='474'
        assert scaled.locator('#cases tr').count()==79
        assert scaled.locator('#profiles tr').nth(0).locator('td').nth(7).inner_text()=='Unavailable'
        for i in (0,6,12,18,24):
            scaled.locator('#case').select_option(str(i))
            assert fact(scaled,'ending','Conditional closed P&L')=='Unavailable'
            if i in (6,12):assert scaled.locator('#orders tr').count()==0
            elif i==18:assert fact(scaled,'ending','Pending orders')=='close-retry'
            elif i==24:assert fact(scaled,'decision','Risk halted')=='true'
        scaled.locator('#case').select_option('24');scaled.locator('#profile').select_option('zero-fee')
        assert scaled.locator('#case').input_value()=='26'
        checks.append('Synthetic 474-case view keeps partial/pending/risk/no-signal/failed states and incomplete financial totals visible')

        changed=copy.deepcopy(large);changed.update(status='source_changed',source_unchanged=False,precision_probe=2**63+123,
            error='</script><img src="https://synthetic.invalid/" onerror="globalThis.boundedInjection=true">')
        for row in changed['cases']:row.update(status='unavailable',policy=None,control=None,reason='Synthetic changed evidence')
        summarize(changed)
        failure=page_for(with_report(changed))
        assert failure.locator('#status').inner_text()=='Bounded exit experiment incomplete'
        assert fact(failure,'ending','Conditional closed P&L')=='Unavailable'
        assert fact(failure,'control','Ending position')=='Unavailable'
        assert failure.locator('#orders tr').count()==0
        assert failure.locator('#error').inner_text()==changed['error']
        assert failure.evaluate('globalThis.boundedInjection === undefined')
        with failure.expect_download() as pending:failure.locator('#download').click()
        pending.value.save_as(output/'failed-bounded-exit.json')
        assert json.loads((output/'failed-bounded-exit.json').read_text())==changed
        checks.append('Changed evidence hides both sides; hostile text is inert and large integer export stays exact')
        assert not errors,errors
        assert not requests,requests
        browser.close()
    result=dict(checks=checks,errors=errors,network_requests=requests)
    (output/'browser-checks.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html',type=Path,required=True);parser.add_argument('--native-fixture',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();run(args.html,args.native_fixture,args.output_dir)

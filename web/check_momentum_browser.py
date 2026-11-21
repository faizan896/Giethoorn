#!/usr/bin/env python3
"""Offline R002 controls, exact financial strings and unavailable-result views."""
import argparse
import copy
import json
from pathlib import Path
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from ops import momentum_core as CORE


def run(html,fixture_path,output):
    output.mkdir(parents=True,exist_ok=True)
    source=html.read_text();report=json.loads((html.parent/'momentum-report.json').read_text())
    fixture=json.loads(fixture_path.read_text());assert fixture['origin']=='synthetic_fixture'
    boot=source.split('<script type="application/json" id="momentum-data">',1)[1].split('</script>',1)[0]
    errors,requests,checks=[],[],[]
    expected=lambda value:'Unavailable' if value is None else str(value)
    def fact(page,identity,label):
        return page.locator('#'+identity+' div').filter(has=page.locator('dt',has_text=label)).locator('dd').inner_text()
    def with_report(value):
        encoded=json.dumps(value).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
        return source.replace(boot,encoded,1)
    def summarize(value):value['totals'],value['screen']=CORE.summarize(value['cases'],value['selected_children'])
    with sync_playwright() as driver:
        browser=driver.chromium.launch(executable_path='/usr/bin/chromium',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1100},accept_downloads=True)
        context.set_offline(True)
        def page_for(contents):
            page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('request',lambda request:requests.append(request.url))
            page.set_content(contents,wait_until='load');return page
        page=page_for(source)
        assert page.locator('#status').inner_text()=='R002 research processing complete'
        assert page.locator('#planned').inner_text()==str(report['totals']['cases'])
        assert page.locator('#classification').inner_text()==report['screen']['classification'].replace('_',' ')
        for i,p in enumerate(report['totals']['profiles']):
            assert page.locator('#profiles tr').nth(i).locator('td').nth(7).inner_text()==expected(p['closed_cycle_net'])
        for i,c in enumerate(report['cases']):
            page.locator('#profile').select_option(c['profile']);page.locator('#case').select_option(str(i))
            m=None if c['policy'] is None else c['policy']['metrics']
            assert fact(page,'ending','Conditional closed P&L')==expected(None if m is None else m['conditional_closed_pnl'])
            assert fact(page,'ending','Assumed fees')==expected(None if m is None else m['fees'])
        with page.expect_download() as pending:page.locator('#download').click()
        pending.value.save_as(output/'downloaded-momentum.json')
        assert json.loads((output/'downloaded-momentum.json').read_text())==report
        page.locator('#profile').select_option('baseline')
        page.screenshot(path=str(output/'momentum-desktop.png'),full_page=True)
        for width in (390,320):
            page.set_viewport_size({'width':width,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'),width
            page.screenshot(path=str(output/f'momentum-mobile-{width}.png'),full_page=True)
        checks.append('Saved software sample keeps complete denominators, exact totals and raw JSON export offline at desktop/390/320 widths')

        golden=copy.deepcopy(report);golden.update(origin='synthetic_fixture',selected_children=[1],
            cases=fixture['cases'],rows=[fixture['row']]);summarize(golden)
        native=page_for(with_report(golden))
        assert native.locator('#origin').inner_text()=='Synthetic source'
        assert native.locator('#classification').inner_text()=='insufficient data'
        assert fact(native,'feature','Signal')=='up'
        assert fact(native,'ending','First close filled')=='0.00025'
        assert fact(native,'ending','Extra close filled')=='0.00075'
        assert fact(native,'ending','Ending position')=='0'
        assert fact(native,'ending','Conditional closed P&L')=='-0.000140240001'
        assert fact(native,'decisions','Requested extra close')=='0.00075'
        assert native.locator('#orders tr').count()==3
        for i,c in enumerate(golden['cases']):
            native.locator('#profile').select_option(c['profile']);native.locator('#case').select_option(str(i))
            m=c['policy']['metrics']
            assert fact(native,'ending','Assumed fees')==m['fees']
            assert fact(native,'ending','Conditional closed P&L')==m['conditional_closed_pnl']
        native.locator('#profile').select_option('baseline')
        native.screenshot(path=str(output/'momentum-native-fixture.png'),full_page=True)
        checks.append('Six same-image native fixture cases display exact causal feature, residual sizing, fees and conditional net without passing the research gate')

        stress=copy.deepcopy(golden);stress['selected_children']=list(range(1,80));stress['cases']=[];stress['rows']=[]
        for child in stress['selected_children']:
            row=copy.deepcopy(fixture['row']);row['child']=child;row['feature']['child']=child
            row['reason']='Labelled synthetic UI stress; not a 79-recording market evaluation'
            if child==4:row.update(feature=None,status='no_signal')
            stress['rows'].append(row)
            for c in fixture['cases']:
                value=copy.deepcopy(c);value.update(child=child,case_id=f'run-{child:06d}--{c["profile"]}',reason=row['reason'])
                m=value['policy']['metrics']
                if child in (1,2,5) and c['profile']=='baseline':
                    m.update(conditional_closed_pnl=None,ending_position_quantity='0.0005',outcome='open_exposure')
                    if child==2:m['pending_order_ids']=['close-retry']
                    if child==5:m['close_decision_status']='risk_halted'
                if child==3 and c['profile']=='baseline':value.update(status='unavailable',policy=None,reason='Labelled synthetic unavailable case')
                if child==4:value.update(status='no_signal',policy=None)
                if child==6 and c['profile']=='slippage-stress':
                    m.update(conditional_closed_pnl=None,ending_position_quantity='0',pending_order_ids=[],
                        assumed_fills=0,entry_quantity='0',entry_outcome='request_rejected',close_requested_quantity=None,
                        close_quantity=None,retry_requested_quantity=None,retry_quantity=None,fees='0',outcome='no_fills')
                    value['policy']['orders']=[]
                stress['cases'].append(value)
        summarize(stress)
        large=page_for(with_report(stress))
        assert large.locator('#planned').inner_text()=='474'
        assert large.locator('#cases tr').count()==79
        assert large.locator('#profiles tr').first.locator('td').nth(7).inner_text()=='Unavailable'
        assert fact(large,'ending','Conditional closed P&L')=='Unavailable'
        assert large.locator('#classification').inner_text()=='incomplete'
        large.locator('#case').select_option('6');assert fact(large,'ending','Pending orders')=='close-retry'
        large.locator('#case').select_option('12');assert fact(large,'ending','Assumed fees')=='Unavailable'
        large.locator('#case').select_option('24');assert fact(large,'decisions','First close decision')=='risk halted'
        large.locator('#profile').select_option('slippage-stress');large.locator('#case').select_option('35')
        assert fact(large,'ending','Outcome')=='no fills';assert fact(large,'ending','Assumed fees')=='0'
        assert fact(large,'ending','Conditional closed P&L')=='Unavailable'
        checks.append('Labelled synthetic 474-case view retains no-signal/no-fill, unavailable, partial, pending and risk states with incomplete financial totals')

        invalid=copy.deepcopy(golden);invalid['source_unchanged']=False
        invalid['cases'][0]['reason']='</script><img src=x onerror="window.attacked=true">'
        invalid['precision_probe']=2**63+123
        hidden=page_for(with_report(invalid))
        assert fact(hidden,'ending','Assumed fees')=='Unavailable'
        assert fact(hidden,'ending','Conditional closed P&L')=='Unavailable'
        assert fact(hidden,'feature','Past move')=='Unavailable'
        assert hidden.locator('#classification').inner_text()=='Invalid evidence'
        assert hidden.evaluate('window.attacked===undefined')
        assert hidden.locator('#selection').inner_text().endswith(invalid['cases'][0]['reason'])
        with hidden.expect_download() as pending:hidden.locator('#download').click()
        pending.value.save_as(output/'invalid-momentum.json')
        assert json.loads((output/'invalid-momentum.json').read_text())==invalid
        checks.append('Changed evidence hides feature/economic values; hostile text is inert and raw export preserves large integers exactly')
        browser.close()
    assert not errors,errors
    assert not requests,requests
    result=dict(checks=checks,errors=errors,network_requests=requests)
    (output/'browser-checks.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--html',type=Path,required=True);p.add_argument('--native-fixture',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    print(json.dumps(run(a.html,a.native_fixture,a.output_dir),indent=2))

#!/usr/bin/env python3
"""Check offline evaluation economics, complete denominators and portable export."""
import argparse
import copy
import json
from pathlib import Path
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from ops import evaluation_core as CORE


def run(html, output):
    output.mkdir(parents=True,exist_ok=True)
    source=html.read_text(); report=json.loads((html.parent/'evaluation-report.json').read_text())
    errors,requests,checks=[],[],[]
    expected=lambda value:'Unavailable' if value is None else str(value)
    def fact(page,identity,label):
        return page.locator('#'+identity+' div').filter(has=page.locator('dt',has_text=label)).locator('dd').inner_text()
    boot=source.split('<script type="application/json" id="evaluation-data">',1)[1].split('</script>',1)[0]
    def with_report(value):
        encoded=json.dumps(value).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
        return source.replace(boot,encoded,1)
    with sync_playwright() as driver:
        browser=driver.chromium.launch(executable_path='/usr/bin/chromium',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1100},accept_downloads=True)
        context.set_offline(True)
        def page_for(contents):
            page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('request',lambda request:requests.append(request.url))
            page.set_content(contents,wait_until='load');return page
        page=page_for(source)
        assert page.locator('#status').inner_text()=='Development evaluation complete'
        assert page.locator('#children').inner_text()==str(len(report['selected_children']))
        assert page.locator('#cases-count').inner_text()==str(report['totals']['cases'])
        for i,p in enumerate(report['totals']['profiles']):
            assert page.locator('#profiles tr').nth(i).locator('td').nth(7).inner_text()==expected(p['closed_cycle_net'])
        for i,row in enumerate(report['cases']):
            page.locator('#profile').select_option(row['profile']);page.locator('#case').select_option(str(i))
            m=row['policy']['metrics'];c=row['policy']['close_compilation']
            assert fact(page,'decision','Own position at decision')==expected(c['known_position'])
            assert fact(page,'decision','Requested close quantity')==expected(m['close_requested_quantity'])
            assert fact(page,'ending','Conditional closed P&L')==expected(m['conditional_closed_pnl'])
            assert fact(page,'ending','Assumed fees')==m['fees']
            assert fact(page,'ending','Ending assumed position')==m['ending_position_quantity']
            assert fact(page,'ending','Actual execution')=='Unknown'
            assert page.locator('#orders tr').count()==len(row['policy']['orders'])
        checks.append('All native cases and six separate profile totals display exact backend financial strings')
        page.locator('#profile').select_option('baseline');page.locator('#case').select_option('0')
        with page.expect_download() as pending:page.locator('#download').click()
        pending.value.save_as(output/'downloaded-evaluation.json')
        assert json.loads((output/'downloaded-evaluation.json').read_text())==report
        page.screenshot(path=str(output/'evaluation-desktop.png'),full_page=True)
        for width in (390,320):
            page.set_viewport_size({'width':width,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'),width
            page.screenshot(path=str(output/f'evaluation-mobile-{width}.png'),full_page=True)
        checks.append('Case/profile selection, exact JSON export and desktop/390/320-pixel layouts work offline')

        synthetic=copy.deepcopy(report);synthetic.update(origin='synthetic_fixture',selected_children=list(range(2,81)),cases=[])
        for child in synthetic['selected_children']:
            for profile in CORE.PROFILES:
                row=copy.deepcopy(report['cases'][0]);row.update(child=child,profile=profile['id'],
                    case_id=f'run-{child:06d}--{profile["id"]}',previously_cost_probed=child<6)
                synthetic['cases'].append(row)
        row=synthetic['cases'][0];p=row['policy'];m=p['metrics']
        p['close_compilation'].update(status='unresolved_entry',known_position='0',working_orders=1)
        m.update(conditional_closed_pnl=None,ending_position_quantity='0.001',pending_order_ids=[],
            close_requested_quantity=None,close_quantity=None,assumed_fills=1,outcome='open_exposure')
        p['orders']=p['orders'][:1]
        row=synthetic['cases'][6];p=row['policy'];m=p['metrics']
        p['close_compilation'].update(status='flat_no_close',known_position='0',working_orders=0)
        m.update(conditional_closed_pnl=None,ending_position_quantity='0',pending_order_ids=[],entry_quantity='0',
            close_requested_quantity=None,close_quantity=None,assumed_fills=0,fees='0',outcome='no_fills')
        p['orders']=p['orders'][:1];p['orders'][0].update(filled_quantity='0',assumed_fee='0',outcome='not_marketable')
        synthetic['cases'][12].update(status='no_signal',policy=None,reason='Synthetic no signal')
        synthetic['cases'][18].update(status='unavailable',policy=None,reason='Synthetic source failure')
        row=synthetic['cases'][24];p=row['policy'];m=p['metrics']
        m.update(conditional_closed_pnl=None,ending_position_quantity='0.001',pending_order_ids=['close'],
            close_quantity='0',assumed_fills=1,outcome='pending_at_source_end')
        p['orders'][1].update(filled_quantity='0',outcome='pending_at_source_end')
        row=synthetic['cases'][30];p=row['policy'];m=p['metrics']
        p['close_compilation'].update(status='missing_decision',known_position=None,working_orders=None)
        p['causal_prefix_audit'].update(decision_available=False,prefix_records=None,prefix_sha256=None)
        m.update(conditional_closed_pnl=None,ending_position_quantity='0.001',pending_order_ids=[],
            close_requested_quantity=None,close_quantity=None,assumed_fills=1,outcome='open_exposure')
        p['orders']=p['orders'][:1]
        synthetic['totals']=CORE.summarize(synthetic['cases']);synthetic['status']='incomplete'
        golden=page_for(with_report(synthetic))
        assert golden.locator('#origin').inner_text()=='Synthetic source'
        assert golden.locator('#children').inner_text()=='79';assert golden.locator('#cases-count').inner_text()=='474'
        assert golden.locator('#cases tr').count()==79
        assert golden.locator('#profiles tr').nth(0).locator('td').nth(7).inner_text()=='Unavailable'
        for i in (0,6,12,18,24,30):
            golden.locator('#case').select_option(str(i))
            assert fact(golden,'ending','Conditional closed P&L')=='Unavailable'
            if i==0:
                assert fact(golden,'decision','Own position at decision')=='0'
                assert fact(golden,'ending','Ending assumed position')=='0.001'
            elif i==6:
                assert fact(golden,'ending','Entry filled')=='0'
                assert fact(golden,'ending','Assumed fees')=='0'
            elif i in (12,18):assert golden.locator('#orders tr').count()==0
            elif i==24:assert fact(golden,'ending','Pending assumed orders')=='close'
            else:assert fact(golden,'decision','Native control prefix')=='No decision · entry-only control retained'
        golden.locator('#case').select_option('24');golden.locator('#profile').select_option('zero-fee')
        assert golden.locator('#case').input_value()=='26'
        checks.append('Synthetic 79-child/474-case view retains failures, no-signal/no-fill and unresolved states without completing a partial profile total')

        changed=copy.deepcopy(synthetic);changed.update(status='source_changed',source_unchanged=False,precision_probe=2**63+123,
            error='</script><img src="https://synthetic.invalid/" onerror="globalThis.evaluationInjection=true">')
        for row in changed['cases']:row.update(status='unavailable',policy=None,reason='Synthetic changed evidence')
        changed['totals']=CORE.summarize(changed['cases'])
        failure=page_for(with_report(changed))
        assert failure.locator('#status').inner_text()=='Development evaluation incomplete'
        assert fact(failure,'ending','Conditional closed P&L')=='Unavailable'
        assert fact(failure,'ending','Ending assumed position')=='Unavailable'
        assert failure.locator('#orders tr').count()==0
        assert all(cell.inner_text()=='Unavailable' for cell in failure.locator('#profiles tr td:last-child').all())
        assert failure.locator('#error').inner_text()==changed['error']
        assert failure.evaluate('globalThis.evaluationInjection === undefined')
        with failure.expect_download() as pending:failure.locator('#download').click()
        pending.value.save_as(output/'failed-evaluation.json')
        assert json.loads((output/'failed-evaluation.json').read_text())==changed
        checks.append('Changed evidence hides economics; hostile text stays inert and large integers export exactly')
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

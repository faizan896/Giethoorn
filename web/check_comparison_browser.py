#!/usr/bin/env python3
"""Offline browser checks for exact financial strings, unknown execution and failures."""
import argparse
import copy
import json
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

PROJECT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(PROJECT))
from ops import model_compare_local as RUN


def run(html,output):
    output.mkdir(parents=True,exist_ok=True)
    source=html.read_text();report=json.loads((html.parent/'comparison-report.json').read_text())
    errors,requests,checks=[],[],[]
    def expected(value):return 'Unavailable' if value is None else str(value)
    def fact(page,identity,label):
        return page.locator('#'+identity+' div').filter(has=page.locator('dt',has_text=label)).locator('dd').inner_text()
    with sync_playwright() as driver:
        browser=driver.chromium.launch(executable_path='/usr/bin/chromium',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1100},accept_downloads=True)
        context.set_offline(True)
        def page_for(contents):
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('request',lambda req:requests.append(req.url));page.set_content(contents,wait_until='load');return page
        page=page_for(source)
        assert page.locator('#status').inner_text()=='Model comparison verified'
        assert page.locator('#verified').inner_text()==str(report['totals']['verified'])
        assert page.locator('#cases tr').count()==len(report['cases'])
        for i,row in enumerate(report['cases']):
            page.locator('#case').select_option(str(i))
            old=row['historical']['metrics'];new=row['proxy']['metrics']
            assert fact(page,'historical','Closed-case P&L')==expected(old['closed_case_net_pnl'])
            assert fact(page,'proxy','Conditional closed P&L')==expected(new['conditional_closed_pnl'])
            assert fact(page,'proxy','Assumed fees')==new['fees']
            assert fact(page,'proxy','Ending assumed position')==new['ending_position_quantity']
            assert fact(page,'proxy','Actual execution')=='Unknown'
            assert page.locator('#orders tr').count()==len(row['proxy']['orders'])
        checks.append('Every case displays backend financial strings, unavailable P&L, positions and unknown actual execution')
        page.locator('#case').select_option('0')
        with page.expect_download() as pending:page.locator('#download').click()
        pending.value.save_as(output/'downloaded-comparison.json')
        assert json.loads((output/'downloaded-comparison.json').read_text())==report
        page.screenshot(path=str(output/'comparison-desktop.png'),full_page=True)
        for width in (390,320):
            page.set_viewport_size({'width':width,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'),width
            page.screenshot(path=str(output/f'comparison-mobile-{width}.png'),full_page=True)
        checks.append('Exact JSON export, case selection and desktop/390/320-pixel layouts work offline')
        boot=source.split('<script type="application/json" id="comparison-data">',1)[1].split('</script>',1)[0]
        def with_report(value):
            encoded=json.dumps(value).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
            return source.replace(boot,encoded,1)
        synthetic=copy.deepcopy(report);synthetic.update(origin='synthetic_fixture',cases=[copy.deepcopy(report['cases'][0])])
        row=synthetic['cases'][0]
        row['historical']['metrics'].update(outcome='entry_rejected',closed_case_net_pnl=None,fees='0',position_quantity='0')
        row['historical']['diagnostic']['orders']=[dict(order_id='entry',classification='expired_no_opportunity')]
        row['proxy']['metrics'].update(outcome='open_exposure',conditional_closed_pnl=None,fees='0.0000500100005',ending_position_quantity='0.001')
        row['proxy']['orders']=[dict(order=dict(id='entry',side='buy',quantity='0.001',limit_price='101'),
            outcome='filled',reference_eligible=True,reference_quote=dict(sequence=8),reference_age_ns='100000000',
            assumed_fill_price='100.020001000000000001',assumed_fill_quantity='0.001',assumed_fee='0.0000500100005')]
        synthetic['totals']=RUN.totals(synthetic['cases'])
        golden=page_for(with_report(synthetic))
        assert golden.locator('#origin').inner_text()=='Synthetic source'
        assert 'expired no opportunity' in golden.locator('#orders').inner_text()
        assert '100 ms' in golden.locator('#orders').inner_text()
        assert '100.020001000000000001' in golden.locator('#orders').inner_text()
        assert fact(golden,'proxy','Conditional closed P&L')=='Unavailable'
        assert fact(golden,'proxy','Ending assumed position')=='0.001'
        checks.append('Synthetic quiet-window contrast preserves exact assumed price, unknown execution and open exposure')
        changed=copy.deepcopy(synthetic)
        changed.update(status='source_changed',input_unchanged=False,precision_probe=2**63+123,
            error='</script><img src="https://synthetic.invalid/" onerror="globalThis.comparisonInjection=true">')
        for row in changed['cases']:row.update(status='unavailable',historical=None,proxy=None,reason='Synthetic changed evidence')
        changed['totals']=RUN.totals(changed['cases'])
        failure=page_for(with_report(changed))
        assert failure.locator('#status').inner_text()=='Model comparison incomplete'
        assert fact(failure,'proxy','Conditional closed P&L')=='Unavailable'
        assert fact(failure,'proxy','Ending assumed position')=='Unavailable'
        assert failure.locator('#orders tr').count()==0
        assert failure.locator('#error').inner_text()==changed['error']
        assert failure.evaluate('globalThis.comparisonInjection === undefined')
        with failure.expect_download() as pending:failure.locator('#download').click()
        pending.value.save_as(output/'failed-comparison.json')
        assert json.loads((output/'failed-comparison.json').read_text())==changed
        checks.append('Changed evidence hides all comparisons; hostile text and large-integer export remain safe')
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

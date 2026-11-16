#!/usr/bin/env python3
"""Acceptance for recorded Paper Lab, using real data plus an explicit fixture."""
import argparse
from decimal import Decimal
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def run(html, fixture_html, output, url=None):
    output.mkdir(parents=True, exist_ok=True)
    frames = [json.loads(line) for line in (html.parent/'replay/paper-updates.jsonl').read_text().splitlines()]
    links = [json.loads(line) for line in (html.parent/'replay/market-links.jsonl').read_text().splitlines()]
    checks, errors = [], []

    def seek(page, index):
        page.locator('#scrubber').evaluate('(node,index)=>{node.value=String(index);node.dispatchEvent(new Event("input",{bubbles:true}));}', index)

    with sync_playwright() as driver:
        browser = driver.chromium.launch(executable_path='/usr/bin/chromium', headless=True)
        context = browser.new_context(viewport={'width':1440, 'height':1080})
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        if url:
            page.goto(url, wait_until='networkidle')
        else:
            context.set_offline(True)
            page.set_content(html.read_text(), wait_until='load')
        assert page.locator('#lab-kind').inner_text() == 'Recorded replay'
        assert 'Recorded public-market data.' in page.locator('.banner').inner_text()
        assert 'Synthetic' not in page.locator('#event-title').inner_text()
        assert page.locator('#scenario-state').inner_text() == 'Replay complete'
        assert page.locator('#source-gate').inner_text() == 'Not verified'
        assert page.locator('#position').inner_text() == '0'
        assert page.locator('#fees').inner_text() == '$0.00'
        assert page.locator('#order-count').inner_text() == '0 orders'
        checks.append('Captured origin is explicit; replay completion does not claim a passed 24-hour gate or strategy orders')
        page.locator('#reset').click()
        assert page.locator('#frame-label').inner_text() == '1 / '+str(len(frames))
        assert page.locator('#recorded-price').inner_text() == '—'
        assert page.locator('#event-title').inner_text() == 'Recorded replay started'
        page.locator('#next').click()
        assert page.locator('#source-sequence').inner_text() == '2'
        page.locator('#previous').click()
        assert page.locator('#source-sequence').inner_text() == '1'
        checks.append('Reset/next/previous traverse actual source-linked events')
        first = next(i for i, frame in enumerate(frames) if frame['event_kind'] == 'market_observed')
        seek(page, first)
        displayed = page.locator('#recorded-price').inner_text().replace('$', '').replace(',', '')
        assert Decimal(displayed) == Decimal(links[first]['quote']['mid'])
        assert page.locator('#source-sequence').inner_text() == str(links[first]['market_sequence'])
        assert page.locator('#recorded-feed-status').inner_text() == 'Fresh'
        assert page.locator('#mark-state').inner_text() == 'Fresh'
        assert page.locator('[data-event]').count() <= 40
        checks.append('Displayed price, original sequence and recorded freshness agree with Rust-derived source links')
        page.locator('#play').click()
        page.wait_for_timeout(750)
        page.locator('#play').click()
        assert page.locator('#play').inner_text() == 'Play replay'
        assert int(page.locator('#frame-label').inner_text().split(' / ')[0]) > first+1
        checks.append('Playback advances recorded events; event trace stays bounded')
        last_mark = max(i for i, frame in enumerate(frames) if frame['event_kind'] == 'market_observed')
        seek(page, last_mark)
        page.screenshot(path=str(output/'recorded-paper-desktop.png'), full_page=True)
        page.screenshot(path=str(output/'recorded-paper-preview.png'))
        for width in (320,390,768,1440):
            page.set_viewport_size({'width':width, 'height':844})
            assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
            if width == 390:
                page.screenshot(path=str(output/'recorded-paper-mobile.png'), full_page=True)
        checks.append('Desktop and narrow mobile layouts have no horizontal overflow')
        offline = browser.new_context(viewport={'width':1440, 'height':1080})
        offline.set_offline(True)
        saved = offline.new_page()
        requests = []
        saved.on('request', lambda request: requests.append(request.url))
        saved.on('pageerror', lambda error: errors.append(str(error)))
        saved.set_content(html.read_text(), wait_until='load')
        seek(saved, first)
        assert saved.locator('#mark-state').inner_text() == 'Fresh'
        assert requests == [], requests
        checks.append('Exact portable captured-data HTML stays interactive offline with zero requests')
        saved.set_content(fixture_html.read_text(), wait_until='load')
        assert saved.locator('#lab-kind').inner_text() == 'Fixture replay'
        assert 'Synthetic market fixture.' in saved.locator('.banner').inner_text()
        for index, expected in ((11,'Stale'), (15,'Disconnected'), (23,'Disconnected'), (24,'Fresh')):
            seek(saved, index)
            assert saved.locator('#mark-state').inner_text() == expected
        seek(saved, 29)
        assert saved.locator('[data-recorded-series]').count() == 1
        assert saved.locator('#pnl-chart circle').count() == 3
        assert requests == [], requests
        checks.append('Explicit synthetic fixture proves stale/empty/reconnect behavior and separate price segments across gaps')
        assert errors == [], errors
        checks.append('No JavaScript errors')
        browser.close()
    result = dict(status='passed', checks=checks, javascript_errors=errors)
    (output/'market-browser-checks.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(status='passed', checks=len(checks), artifacts=str(output.resolve())), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', type=Path, required=True)
    parser.add_argument('--fixture-html', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--url')
    args = parser.parse_args()
    run(args.html, args.fixture_html, args.output_dir, args.url)

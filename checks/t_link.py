import os
HERE = os.path.dirname(os.path.abspath(__file__))
PAGE_DEFAULT = 'file://' + os.path.join(HERE, '..', 'index.html')
import asyncio, sys
from playwright.async_api import async_playwright
PAGE = sys.argv[1] if len(sys.argv) > 1 else PAGE_DEFAULT
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel='chrome', args=['--no-sandbox'])
        pg2 = await b.new_page(viewport={'width':1440,'height':900}); await pg2.goto(PAGE); await pg2.wait_for_timeout(500)
        await pg2.select_option('#place', index=7); await pg2.select_option('#grid', index=0); await pg2.select_option('#travel', '1'); await pg2.select_option('#water', '1')
        await pg2.click('button[data-need="1"]'); await pg2.click('input[type=checkbox][data-good="TR_03"]')
        await pg2.click('#back') if await pg2.is_visible('#back') else None
        await pg2.click('button[data-need="0"]'); await pg2.click('input[type=checkbox][data-good="F_22"]'); await pg2.fill('input[data-q="F_11"]', '120'); await pg2.keyboard.press('Tab'); await pg2.wait_for_timeout(300)
        a = await pg2.evaluate("(() => { const c = window.__ube.calc(); return {total: c.total, needs: c.needs, href: location.href, place: document.querySelector('#place').value}; })()")
        pg3 = await b.new_page(viewport={'width':390,'height':844}); await pg3.goto(a['href']); await pg3.wait_for_timeout(600)
        c = await pg3.evaluate("(() => { const c = window.__ube.calc(); return {total: c.total, needs: c.needs, place: document.querySelector('#place').value, meat: document.querySelector('input[data-q=\"F_11\"]').value, head: document.querySelector('#total').textContent}; })()")
        print('link carries:', a['href'].split('#')[1] if '#' in a['href'] else a['href'][-80:])
        print('round trip gives the same numbers:', a['total'] == c['total'] and a['needs'] == c['needs'] and a['place'] == c['place'], '|', a['total'], c['total'], c['place'], 'meat', c['meat'], 'headline', c['head'])
        await b.close()
asyncio.run(main())

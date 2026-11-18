# Classic (space-taking) scrollbars, as on Windows: the wide plate must not be wider than the visible page.
import os
HERE = os.path.dirname(os.path.abspath(__file__))
PAGE_DEFAULT = 'file://' + os.path.join(HERE, '..', 'index.html')
import asyncio, sys
from playwright.async_api import async_playwright
PAGE = sys.argv[1] if len(sys.argv) > 1 else PAGE_DEFAULT
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel='chrome', args=['--no-sandbox'], ignore_default_args=['--hide-scrollbars'])
        bad = 0
        for w in (1385, 1440, 1108, 1100, 1920, 767, 390):
            pg = await b.new_page(viewport={'width': w, 'height': 700}); await pg.goto(PAGE); await pg.wait_for_timeout(700)
            r = await pg.evaluate("(() => { const d = document.documentElement, b = document.querySelector('#board').getBoundingClientRect(); return {inner: innerWidth, client: d.clientWidth, scroll: d.scrollWidth, mode: document.querySelector('#app').className, boardRight: Math.round(b.right * 10) / 10}; })()")
            over = r['scroll'] - r['client']; bad += over > 0
            print(w, r, 'OVERFLOW %d px' % over if over > 0 else 'ok'); await pg.close()
        await b.close(); print('widths with sideways overflow:', bad)
asyncio.run(main())

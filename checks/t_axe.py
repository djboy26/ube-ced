import os
HERE = os.path.dirname(os.path.abspath(__file__))
PAGE_DEFAULT = 'file://' + os.path.join(HERE, '..', 'index.html')
import asyncio, sys, json
from playwright.async_api import async_playwright
PAGE = sys.argv[1] if len(sys.argv) > 1 else PAGE_DEFAULT
AXE = open(os.path.join(HERE, 'node_modules', 'axe-core', 'axe.min.js')).read()   # npm i axe-core, in this folder
async def run(pg, label):
    await pg.evaluate(AXE)
    r = await pg.evaluate("axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']}}).then(r => r.violations.map(v => ({id: v.id, impact: v.impact, n: v.nodes.length, ex: v.nodes[0].html.slice(0, 140), why: v.nodes[0].failureSummary.slice(0, 200)})))")
    print(label, 'violations:', len(r)); [print('   ', json.dumps(v)[:420]) for v in r]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel='chrome', args=['--no-sandbox'])
        for w in (1440, 767, 390):
            pg = await b.new_page(viewport={'width': w, 'height': 900}); await pg.goto(PAGE); await pg.wait_for_timeout(600)
            await run(pg, f'{w}px closed:')
            if w < 1100: await pg.click('#bk-toggle')
            await pg.click('button[data-need="0"]'); await pg.wait_for_timeout(300)
            await run(pg, f'{w}px food open:')
            await pg.close()
        await b.close()
asyncio.run(main())

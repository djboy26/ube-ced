# Every piece of page text and every control must be on top where it stands: nothing drawn later may cover it.
import os
HERE = os.path.dirname(os.path.abspath(__file__))
PAGE_DEFAULT = 'file://' + os.path.join(HERE, '..', 'index.html')
import asyncio, sys, json
from playwright.async_api import async_playwright
PAGE = sys.argv[1] if len(sys.argv) > 1 else PAGE_DEFAULT
JS = """(() => { const vis = e => { for (let p = e; p; p = p.parentElement) { const c = getComputedStyle(p); if (c.display === 'none' || c.visibility === 'hidden' || Number(c.opacity) < 0.05) return false; } return true; };
  const els = [...document.querySelectorAll('h1, h2, p, .eyebrow, select, button, input, a, label')].filter(e => !e.closest('svg') && !e.closest('dialog:not([open])') && vis(e) && (e.matches('select,input,button') || e.textContent.trim()));
  const bad = []; let n = 0;
  for (const e of els) { e.scrollIntoView({block: 'center', inline: 'nearest'}); const rs = [...e.getClientRects()].filter(r => r.width > 3 && r.height > 3); if (!rs.length) continue; const r = rs[0]; n++;
    const x = Math.min(innerWidth - 2, Math.max(1, r.left + Math.min(r.width / 2, 12))), y = r.top + r.height / 2; if (y < 0 || y > innerHeight) continue;
    const hit = document.elementFromPoint(x, y); if (!hit) continue;
    if (!(hit === e || e.contains(hit) || hit.contains(e) && !hit.matches('main,#app,#wrap,#board,body,html') || hit.closest('label') && hit.closest('label').contains(e) || e.closest('label') && e.closest('label').contains(hit) || (hit.closest('button,li,p') && hit.closest('button,li,p').contains(e))))
      bad.push({el: e.tagName + (e.id ? '#' + e.id : '') + '.' + String(e.className).slice(0, 18), txt: (e.textContent || e.getAttribute('aria-label') || '').trim().slice(0, 40), under: hit.tagName + (hit.id ? '#' + hit.id : '') + '.' + String(hit.className.baseVal !== undefined ? hit.className.baseVal : hit.className).slice(0, 18)}); }
  scrollTo(0, 0); return {n, bad}; })()"""
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel='chrome', args=['--no-sandbox']); total = 0
        for w in (1440, 1100, 1920, 767, 390):
            for state in ('start', 'food open'):
                pg = await b.new_page(viewport={'width': w, 'height': 900}); await pg.goto(PAGE); await pg.wait_for_timeout(600)
                if state == 'food open':
                    if w < 1100: await pg.click('#bk-toggle')
                    await pg.click('button[data-need="0"]'); await pg.wait_for_timeout(300)
                r = await pg.evaluate(JS); total += len(r['bad'])
                print(f"{w}px, {state}: {r['n']} texts and controls, covered {len(r['bad'])}"); [print('    ', json.dumps(o)[:190]) for o in r['bad'][:6]]
                await pg.close()
        await b.close(); print('covered in all:', total)
asyncio.run(main())

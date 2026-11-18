# Words must not sit on other words. Collects the boxes of every visible piece of text (page text and labels in the drawing)
# and reports pairs that overlap by more than a sliver.
import os
HERE = os.path.dirname(os.path.abspath(__file__))
PAGE_DEFAULT = 'file://' + os.path.join(HERE, '..', 'index.html')
import asyncio, sys, json
from playwright.async_api import async_playwright
PAGE = sys.argv[1] if len(sys.argv) > 1 else PAGE_DEFAULT
JS = """(() => { const vis = e => { const s = getComputedStyle(e); if (s.visibility === 'hidden' || s.display === 'none' || Number(s.opacity) < 0.05) return false; for (let p = e; p; p = p.parentElement) { const c = getComputedStyle(p); if (c.display === 'none' || c.visibility === 'hidden' || Number(c.opacity) < 0.05) return false; } return true; };
  const items = [];
  for (const t of document.querySelectorAll('svg text')) { if (!t.textContent.trim() || !vis(t)) continue; const r = t.getBoundingClientRect(); if (r.width < 2 || r.height < 2) continue; items.push({k: 'svg', txt: t.textContent.trim().slice(0, 40), x: r.left, y: r.top + scrollY, w: r.width, h: r.height, id: items.length}); }
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) { const p = n.parentElement; if (!n.textContent.trim() || !p || p.closest('svg') || p.closest('script,style,option,dialog:not([open])') || !vis(p)) continue;
    const range = document.createRange(); range.selectNodeContents(n);
    for (const r of range.getClientRects()) { if (r.width < 2 || r.height < 2) continue; items.push({k: 'html', txt: n.textContent.trim().slice(0, 40), x: r.left, y: r.top + scrollY, w: r.width, h: r.height, node: p.tagName + '.' + String(p.className).slice(0, 20), id: items.length, over: !!(p.closest('#bk-panel') && document.querySelector('#app').className === 'stack'), blk: (p.closest('p,h1,h2,li,button,label,.eyebrow,select') || p).outerHTML.length + ':' + (p.closest('p,h1,h2,li,button,label,.eyebrow,select') || p).textContent.slice(0, 30)}); } }
  const out = [], W = document.documentElement.clientWidth;
  for (let i = 0; i < items.length; i++) for (let j = i + 1; j < items.length; j++) { const a = items[i], b = items[j]; if (a.k === 'html' && b.k === 'html' && a.blk === b.blk) continue; if ((a.over || b.over) && !(a.over && b.over)) continue;   // the opened basket panel lies over the drawing on purpose
    const ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x), oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
    // boxes include line spacing above and below the letters: count an overlap only when it is deeper than that
    if (ox > 3 && oy > Math.min(a.h, b.h) * 0.38 && Math.max(a.x, b.x) < W && a.x + a.w > 0) out.push({a: a.k + ':' + a.txt, b: b.k + ':' + b.txt, ox: Math.round(ox), oy: Math.round(oy), at: [Math.round(Math.max(a.x, b.x)), Math.round(Math.max(a.y, b.y))]}); }
  return {n: items.length, out}; })()"""
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel='chrome', args=['--no-sandbox']); total = 0
        for w in (1440, 1100, 1920, 767, 390):
            for state in ('start', 'car, fossil, 41 L, Aalborg', 'food open'):
                pg = await b.new_page(viewport={'width': w, 'height': 900}); await pg.goto(PAGE); await pg.wait_for_timeout(600)
                if state.startswith('car'):
                    await pg.select_option('#place', index=1); await pg.select_option('#grid', index=0); await pg.select_option('#travel', '1'); await pg.select_option('#water', '1')
                if state == 'food open':
                    if w < 1100: await pg.click('#bk-toggle')
                    await pg.click('button[data-need="0"]')
                await pg.wait_for_timeout(300)
                r = await pg.evaluate(JS); total += len(r['out'])
                print(f"{w}px, {state}: {r['n']} pieces of text, overlapping pairs {len(r['out'])}"); [print('    ', json.dumps(o)[:200]) for o in r['out'][:8]]
                await pg.close()
        await b.close(); print('overlapping pairs in all:', total)
asyncio.run(main())

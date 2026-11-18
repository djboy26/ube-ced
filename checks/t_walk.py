# Random walks through the real controls; after every step the page's own sums and its visible text must agree.
import os
HERE = os.path.dirname(os.path.abspath(__file__))
PAGE_DEFAULT = 'file://' + os.path.join(HERE, '..', 'index.html')
import asyncio, json, random, sys
from playwright.async_api import async_playwright
PAGE = sys.argv[1] if len(sys.argv) > 1 else PAGE_DEFAULT
STEP = """(a) => { const fire = (e) => { e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new Event('change', {bubbles: true})); };
  if (a.t === 'sel') { const e = document.querySelector('#' + a.id); e.selectedIndex = Math.floor(a.r * e.options.length); fire(e); }
  else if (a.t === 'good') { const l = [...document.querySelectorAll('input[type=checkbox][data-good]')]; l[Math.floor(a.r * l.length)].click(); }
  else if (a.t === 'need') { const l = [...document.querySelectorAll('input[type=checkbox][data-need]')]; l[Math.floor(a.r * l.length)].click(); }
  else if (a.t === 'qty') { const l = [...document.querySelectorAll('input[data-q]')]; const e = l[Math.floor(a.r * l.length)]; e.value = a.v; fire(e); }
  else if (a.t === 'reset') { const b = [...document.querySelectorAll('button')].find(x => /reset the basket/i.test(x.textContent)); if (b) b.click(); }
  const u = window.__ube, c = u.calc(), on = g => !u.st.off.has(g.id), rows = u.goods.filter(on).map(g => u.rowVal(g));
  const txt = document.body.innerText, head = txt.match(/\\n([\\d,]+)\\n\\nkWh a year/);
  const bad = [];
  if (c.needs.reduce((x, y) => x + y, 0) !== c.total) bad.push('needs do not sum to the total');
  if (rows.reduce((x, y) => x + y, 0) !== c.total) bad.push('goods do not sum to the total');
  if (c.br.reduce((x, y) => x + y, 0) !== c.total) bad.push('root branches do not sum to the total: ' + c.br.reduce((x, y) => x + y, 0) + ' vs ' + c.total);
  if (rows.some(v => !(v >= 0) || !Number.isFinite(v))) bad.push('a good is negative or not a number');
  if (!head || Number(head[1].replace(/,/g, '')) !== c.total) bad.push('headline text ' + (head && head[1]) + ' vs ' + c.total);
  if (c.total > 0 && (c.panels * c.perPanel < c.total || (c.panels - 1) * c.perPanel >= c.total)) bad.push('panel count');
  if (c.total > 0 && (c.shares * u.D.share_kwh < c.total || (c.shares - 1) * u.D.share_kwh >= c.total)) bad.push('wind shares');
  if (c.band && !(c.band[0] <= c.total && c.total <= c.band[1])) bad.push('range does not bracket the total');
  if (document.documentElement.scrollWidth > document.documentElement.clientWidth + 1) bad.push('sideways overflow ' + document.documentElement.scrollWidth);
  if (/NaN|undefined|Infinity/.test(txt)) bad.push('NaN/undefined in the text');
  return {bad, total: c.total}; }"""
async def walk(b, w, h, n, seed):
    rnd = random.Random(seed); pg = await b.new_page(viewport={'width': w, 'height': h}); errs = []
    pg.on('console', lambda m: errs.append(m.text[:160])); pg.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)[:200]))
    await pg.goto(PAGE); await pg.wait_for_timeout(600); bad = []; hi = 0
    for i in range(n):
        x = rnd.random()
        if x < .22: a = {'t': 'sel', 'id': rnd.choice(['place', 'grid', 'travel', 'water']), 'r': rnd.random()}
        elif x < .47: a = {'t': 'good', 'r': rnd.random()}
        elif x < .52: a = {'t': 'need', 'r': rnd.random()}
        elif x < .97: a = {'t': 'qty', 'r': rnd.random(), 'v': rnd.choice(['', '0', '-5', '1e9', 'abc', '3.7', str(rnd.randint(1, 400)), str(rnd.randint(1, 60000)), str(round(rnd.random() * 30, 2))])}
        else: a = {'t': 'reset'}
        r = await pg.evaluate(STEP, a); hi = max(hi, r['total'])
        if r['bad']: bad.append((i, a, r['bad']))
    await pg.close(); return bad, errs, hi
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel='chrome', args=['--no-sandbox'])
        for w, h, n, seed in ((1440, 900, 1500, 11), (767, 900, 900, 12), (390, 844, 900, 13)):
            bad, errs, hi = await walk(b, w, h, n, seed)
            print(f'{w}px: {n} steps, problems {len(bad)}, console messages {len(errs)}, largest basket seen {hi:,} kWh'); [print('   ', x) for x in bad[:6]]; [print('   console:', e) for e in errs[:4]]
        await b.close()
asyncio.run(main())

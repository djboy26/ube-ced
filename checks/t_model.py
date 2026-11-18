# Independent check: the page's numbers against model v5 (public repo, unmodified), for typed quantities and switches.
import os
HERE = os.path.dirname(os.path.abspath(__file__))
PAGE_DEFAULT = 'file://' + os.path.join(HERE, '..', 'index.html')
import sys, json, copy, asyncio
sys.path.insert(0, '.')
import model_dump as md
m = md.m
MAP = json.load(open(os.path.join(HERE, 'mapping.json')))
LAB = ['Fossil_2.5', 'DK_2023_1.6', 'Renewable_1.0']
PAGE = PAGE_DEFAULT
GOODS = json.load(open(os.path.join(HERE, 'page_goods.json')))['goods']
Q0 = {g['id']: g['q0'] for g in GOODS if g.get('qu')}

def model(case):
    params = copy.deepcopy(md.params); cfg = copy.deepcopy(md.cfg); basket = [dict(r) for r in md.basket]
    sc = m.default_scenario(params, cfg)
    fq = cfg['food']['central']['line_kg_cap_yr']
    qty = dict(case.get('qty', {}))
    for gid in case.get('off', []):
        if gid in Q0 and gid.startswith('F_'): qty[gid] = 0.0          # an unticked food is 0 g for the model
    for gid, val in qty.items():
        f = val / Q0[gid]
        if gid == 'TR_01E': sc['pkm_scale'] = f
        elif gid == 'C_01': sc['floor_area'] = sc['floor_area'] * f
        elif gid == 'H_02': sc['hot_water_L'] = val
        elif gid == 'A_01':
            c = params['cooking']['variants'][sc['cooking']]
            for k in ('kWh_per_cap_yr', 'low', 'high'): c[k] *= f
        else:
            lines = MAP[gid] if gid.startswith('F_') else [gid]         # phone and laptop: only the electricity line moves
            for lid in lines:
                if lid in fq: fq[lid] *= f
                for r in basket:
                    if r['line_id'] == lid: r['quantity'] *= f
    if case.get('travel'): sc['modal_split'] = 'danish_actual'
    if case.get('water'): sc['hot_water_L'] = 41.0
    res = m.run_once(params, basket, cfg, sc)
    L = {l['line_id']: l for l in res['lines']}
    off = set(case.get('off', []))
    out = {}
    for g in GOODS:
        gid = g['id']
        out[gid] = [0.0] * 3 if (gid in off or (gid == 'TR_03' and 'TR_03' not in case.get('on', []))) else [sum(L[l]['primary_' + lab] for l in MAP[gid]) for lab in LAB]
    return out

CASES = {
 'defaults': {},
 'food': {'qty': {'F_01': 180, 'F_11': 0, 'F_15': 120, 'F_04': 60, 'F_03': 400, 'F_23': 10}},
 'km 9000': {'qty': {'TR_01E': 9000}},
 'car, km 7000': {'travel': 1, 'qty': {'TR_01E': 7000}},
 'm2 35': {'qty': {'C_01': 35}},
 'hot water 35 L typed': {'qty': {'H_02': 35}},
 'hot water 41 L switch': {'water': 1},
 'plug numbers': {'qty': {'A_01': 120, 'A_02': 40, 'A_03': 150, 'A_04': 0, 'A_05': 60, 'CM_02': 50, 'CM_03': 8, 'CM_05': 45}},
 'clothes and water': {'qty': {'T_01': 8, 'T_02': 3, 'W_01': 120, 'W_02': 110}},
 'meat unticked': {'off': ['F_11']},
 'tomatoes unticked, healthcare off': {'off': ['F_04', 'HC_02']},
 'roads and rails ticked': {'on': ['TR_03']},
 'everything at once': {'travel': 1, 'water': 1, 'on': ['TR_03'], 'off': ['F_22', 'TR_04'], 'qty': {'F_01': 300, 'F_07': 500, 'F_11': 150, 'TR_01E': 14000, 'C_01': 48, 'A_02': 200, 'CM_05': 60, 'T_01': 12, 'W_01': 200}},
}

SETJS = """(c) => { const set = (sel, v) => { const e = document.querySelector(sel); e.value = String(v); e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new Event('change', {bubbles: true})); };
  set('#travel', c.travel ? 1 : 0); set('#water', c.water ? 1 : 0);
  for (const id of (c.off || []).concat(c.on || [])) { const e = document.querySelector('input[type=checkbox][data-good="' + id + '"]'); e.click(); }
  for (const [id, v] of Object.entries(c.qty || {})) set('input[data-q="' + id + '"]', v);
  const u = window.__ube, out = {};
  for (const k of [0, 1, 2]) { set('#grid', k); const c2 = u.calc(); out[k] = {total: c2.total, needs: c2.needs, shown: document.body.innerText.match(/\\n([\\d,]+)\\n\\nkWh a year/) ? document.body.innerText.match(/\\n([\\d,]+)\\n\\nkWh a year/)[1] : null,
      goods: Object.fromEntries(u.goods.map(g => [g.id, u.st.off.has(g.id) ? 0 : u.real(g, k)])), rows: Object.fromEntries(u.goods.map(g => [g.id, u.st.off.has(g.id) ? 0 : u.rowVal(g)])), sel: [...document.querySelector('#grid').options].map(o => o.value)}; }
  return out; }"""

async def main():
    from playwright.async_api import async_playwright
    worst = 0.0; fails = []; n = 0
    async with async_playwright() as p:
        b = await p.chromium.launch(channel='chrome', args=['--no-sandbox'])
        for name, case in CASES.items():
            pg = await b.new_page(viewport={'width': 1440, 'height': 900}); errs = []
            pg.on('console', lambda mm: errs.append(mm.text[:150])); pg.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)[:200]))
            await pg.goto(PAGE); await pg.wait_for_timeout(500)
            got = await pg.evaluate(SETJS, case); mod = model(case)
            cw = 0.0
            for k in range(3):
                mt = 0.0
                for gid, mv in mod.items():
                    pv = got[str(k)]['goods'][gid]; gap = abs(pv - mv[k]); cw = max(cw, gap); n += 1; mt += mv[k]
                    if gap > 0.01: fails.append((name, LAB[k], gid, round(pv, 3), round(mv[k], 3)))
                    # whole kWh: the start state rounds by largest remainder, so a shown row can sit up to 0.55 from the model
                    if abs(got[str(k)]['rows'][gid] - mv[k]) >= 1.0: fails.append((name, LAB[k], gid, 'shown whole kWh', got[str(k)]['rows'][gid], round(mv[k], 3)))
                T = got[str(k)]['total']
                if abs(T - sum(got[str(k)]['needs'])) > 0 or abs(T - sum(got[str(k)]['rows'].values())) > 0: fails.append((name, LAB[k], 'page sums disagree'))
                if abs(T - mt) > 0.5 * 44: fails.append((name, LAB[k], 'total', T, round(mt, 2)))
                if got[str(k)]['shown'] is not None and int(got[str(k)]['shown'].replace(',', '')) != T: fails.append((name, LAB[k], 'headline text', got[str(k)]['shown'], T))
            worst = max(worst, cw)
            print('%-36s  totals %s  model %s  largest gap %.4f kWh%s' % (name, [got[str(k)]['total'] for k in range(3)], [round(sum(v[k] for v in mod.values())) for k in range(3)], cw, ('  CONSOLE ' + str(errs)) if errs else ''))
            await pg.close()
        await b.close()
    print('values compared:', n, ' largest gap:', round(worst, 5), 'kWh', ' failures:', len(fails)); [print('  FAIL', f) for f in fails[:30]]
asyncio.run(main())

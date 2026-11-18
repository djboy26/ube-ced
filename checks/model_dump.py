# Runs model v5 from the public repo, unmodified, and dumps line-level primary energy for a scenario.
import os
HERE = os.path.dirname(os.path.abspath(__file__))
PAGE_DEFAULT = 'file://' + os.path.join(HERE, '..', 'index.html')
import sys, json
M = os.environ.get('UBE_MODEL_V5', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'ube-ced', 'model', 'wave4', 'ube_model_v5'))
sys.path.insert(0, M); os.chdir(M)
import ube_model_v5 as m
params = m.load_parameters(); findings = m.load_findings(); cfg = m.v5_config(params, findings)
basket = m.load_basket(cfg)
def run(over=None, qty=None):
    sc = m.default_scenario(params, cfg); sc.update(over or {})
    b = [dict(r) for r in basket]
    if qty:                      # direct quantity overrides on basket rows (fields the page lets the reader type)
        for r in b:
            if r['line_id'] in qty: r['quantity'] = qty[r['line_id']]
    res = m.run_once(params, b, cfg, sc)
    return {'totals': res['totals'], 'lines': {l['line_id']: {'in': l['in_floor'], 'sector': l['sector'], **{k: l[k] for k in l if k.startswith('primary_')}} for l in res['lines']},
            'q': {k: v for k, v in res['context']['quantities'].items()}, 'scenario': {k: v for k, v in sc.items() if isinstance(v, (int, float, str))}}
if __name__ == '__main__':
    r = run()
    print(json.dumps({'totals': r['totals'], 'scenario': r['scenario'], 'n_lines': len(r['lines']), 'in_floor': sum(1 for l in r['lines'].values() if l['in'])}, indent=1))
    print('labels', list(params['pef_scenarios'].items()))
    for lid in ['F_01','F_04','F_25','TR_01E','TR_01L','TR_02','TR_03','H_01','H_02','H_03','C_01','HC_01','HC_02','A_01']:
        l = r['lines'].get(lid); print(lid, l and (l['in'], round(l['primary_DK_2023_1.6'], 3)), 'q=', round(r['q'].get(lid, float('nan')), 4))

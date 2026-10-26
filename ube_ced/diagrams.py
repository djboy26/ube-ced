"""Inline SVG for the report. No dependencies. Two mandatory depictions (project standing rule):
(1) the backward-opening supply chain from the finished good, tier by tier;
(2) the interdependent Leontief loop that a tree cannot draw."""
from __future__ import annotations
from html import escape
import math
import numpy as np
from .system import System
from .solve import Solution

FONT = "font-family:ui-sans-serif,system-ui,Segoe UI,Helvetica,Arial;font-size:12px"
C_NODE, C_EDGE, C_ACC, C_MUT, C_TXT = "#eef2f7", "#8a94a6", "#c8541b", "#4a6b8a", "#1a1f2b"


def _fmt(v: float) -> str:
    if v == 0: return "0"
    if abs(v) >= 100: return f"{v:,.0f}"
    if abs(v) >= 10: return f"{v:,.1f}"
    if abs(v) >= 1: return f"{v:,.2f}"
    return f"{v:.3g}"


# ---------------------------------------------------------------- (1) backward-opening tree
def backward_tree_svg(system: System, sol: Solution, depth: int = 3, top: int = 4) -> str:
    """Root = functional unit process. Each node opens into its inputs; each edge is labelled with the
    kWh that flow through it per functional unit: a_ij * (L f)_j ... attributed via epsilon_i * a_ij * x_j."""
    A, eps, f = system.A, sol.epsilon, sol.f
    x = sol.L @ f                                   # gross output of every process per functional unit
    root = int(np.argmax(f))
    nodes, edges = [], []                           # nodes: (id, tier, label, kwh); edges: (parent_id, child_id, kwh)
    counter = [0]

    def add(i, tier, parent, via_kwh, scale):
        nid = counter[0]; counter[0] += 1
        own = float(system.e[i] * x[i] * scale)     # external energy entering directly at this node (scaled by share)
        nodes.append((nid, tier, system.processes[i], via_kwh, own))
        if parent is not None:
            edges.append((parent, nid, via_kwh))
        if tier >= depth:
            return
        inputs = [(k, float(A[k, i] * x[i] * scale * eps[k])) for k in range(system.n) if A[k, i] > 0]
        inputs.sort(key=lambda t: -t[1])
        shown, rest = inputs[:top], inputs[top:]
        for k, kwh in shown:
            if kwh <= 0: continue
            share = (A[k, i] * x[i] * scale) / x[k] if x[k] > 0 else 0.0   # fraction of k's output used here
            add(k, tier + 1, nid, kwh, share)
        if rest:
            rk = sum(v for _, v in rest)
            if rk > 0:
                oid = counter[0]; counter[0] += 1
                nodes.append((oid, tier + 1, f"{len(rest)} other inputs", rk, 0.0)); edges.append((nid, oid, rk))

    add(root, 0, None, sol.ced, 1.0)

    # layout: classic tree. Leaves take consecutive rows; a parent sits at the centre of its children's band.
    children = {}
    for p_, c_, _ in edges:
        children.setdefault(p_, []).append(c_)
    row = {}; next_row = [0]
    def place(nid):
        ch = children.get(nid, [])
        if not ch:
            row[nid] = next_row[0]; next_row[0] += 1
        else:
            for c_ in ch: place(c_)
            row[nid] = (row[ch[0]] + row[ch[-1]]) / 2
    place(nodes[0][0])
    W_COL, H_ROW, NW, NH, GAP = 330, 44, 200, 34, 130
    tier_of = {nid: t for nid, t, *_ in nodes}
    pos = {nid: (30 + tier_of[nid] * W_COL, 40 + row[nid] * H_ROW) for nid in row}
    width = 60 + (max(tier_of.values()) + 1) * W_COL - GAP + 40
    height = 80 + next_row[0] * H_ROW
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" style="{FONT};max-width:{width}px">']
    out.append(f'<text x="30" y="20" fill="{C_TXT}" font-weight="600">Backward-opening chain: start at the finished good, open each input one tier back. Edge = kWh external energy flowing through that input, per functional unit.</text>')
    maxk = max(k for *_, k in edges) if edges else 1
    for p_, c_, kwh in edges:
        (x1, y1), (x2, y2) = pos[p_], pos[c_]
        sw = 1 + 6 * (kwh / maxk)
        xa, xb = x1 + NW, x2
        out.append(f'<path d="M{xa},{y1+NH/2} C{xa+GAP*0.5},{y1+NH/2} {xb-GAP*0.5},{y2+NH/2} {xb},{y2+NH/2}" fill="none" stroke="{C_EDGE}" stroke-width="{sw:.1f}" opacity="0.75"/>')
        out.append(f'<text x="{xb-8}" y="{y2+NH/2-6}" fill="{C_ACC}" text-anchor="end" font-size="11">{_fmt(kwh)} kWh</text>')
    for nid, tier, label, via, own in nodes:
        X, Y = pos[nid]
        fill = C_NODE if tier else "#fde8dc"
        out.append(f'<rect x="{X}" y="{Y}" width="{NW}" height="{NH}" rx="6" fill="{fill}" stroke="{C_EDGE}"/>')
        out.append(f'<text x="{X+8}" y="{Y+14}" fill="{C_TXT}" font-weight="600">{escape(label)}</text>')
        sub = f"tier {tier}" + (f" · external in: {_fmt(own)} kWh" if own > 0 else "")
        out.append(f'<text x="{X+8}" y="{Y+28}" fill="{C_MUT}" font-size="10.5">{escape(sub)}</text>')
    out.append("</svg>")
    return "\n".join(out)


# ---------------------------------------------------------------- (2) the Leontief loop
def _sccs(adj: list[list[int]]) -> list[list[int]]:
    """Tarjan. Returns strongly connected components."""
    n = len(adj); index = [None] * n; low = [0] * n; on = [False] * n; st = []; out = []; idx = [0]
    def strong(v):
        index[v] = low[v] = idx[0]; idx[0] += 1; st.append(v); on[v] = True
        for w in adj[v]:
            if index[w] is None:
                strong(w); low[v] = min(low[v], low[w])
            elif on[w]:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = st.pop(); on[w] = False; comp.append(w)
                if w == v: break
            out.append(comp)
    for v in range(n):
        if index[v] is None: strong(v)
    return out


def loop_svg(system: System, sol: Solution) -> str:
    A = system.A; n = system.n
    adj = [[j for j in range(n) if A[i, j] > 0] for i in range(n)]   # i supplies j
    comps = [c for c in _sccs(adj) if len(c) > 1 or A[c[0], c[0]] > 0]
    W, H = 820, 360
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" style="{FONT};max-width:{W}px">']
    out.append(f'<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{C_ACC}"/></marker></defs>')
    out.append(f'<text x="20" y="22" fill="{C_TXT}" font-weight="600">The interdependent loop a tree cannot draw. Arrow = "supplies". A cycle means the inverse, not addition.</text>')
    if not comps:
        out.append(f'<text x="20" y="60" fill="{C_MUT}">No cycle in this system. (I − A)⁻¹ then equals the finite tier sum and plain addition would suffice.</text></svg>')
        return "\n".join(out)
    comp = max(comps, key=len)
    cx, cy, R = 200, 200, 120
    pts = {}
    for k, i in enumerate(comp):
        ang = -math.pi / 2 + 2 * math.pi * k / len(comp)
        pts[i] = (cx + R * math.cos(ang), cy + R * math.sin(ang))
    for i in comp:
        for j in comp:
            if A[i, j] > 0:
                if i == j:
                    X, Y = pts[i]
                    out.append(f'<path d="M{X+18},{Y-6} C{X+60},{Y-50} {X+60},{Y+40} {X+18},{Y+8}" fill="none" stroke="{C_ACC}" stroke-width="1.6" marker-end="url(#arr)"/>')
                    continue
                (x1, y1), (x2, y2) = pts[i], pts[j]
                dx, dy = x2 - x1, y2 - y1; d = math.hypot(dx, dy); ux, uy = dx / d, dy / d
                # offset parallel pairs so both directions are visible
                ox, oy = -uy * 7, ux * 7
                out.append(f'<line x1="{x1+ux*26+ox:.1f}" y1="{y1+uy*26+oy:.1f}" x2="{x2-ux*26+ox:.1f}" y2="{y2-uy*26+oy:.1f}" stroke="{C_ACC}" stroke-width="1.6" marker-end="url(#arr)"/>')
                mx, my = (x1 + x2) / 2 + ox * 2.2, (y1 + y2) / 2 + oy * 2.2
                out.append(f'<text x="{mx:.1f}" y="{my:.1f}" fill="{C_MUT}" font-size="10.5" text-anchor="middle">{_fmt(A[i,j])} {escape(system.units[i])}/{escape(system.units[j])}</text>')
    for i in comp:
        X, Y = pts[i]
        out.append(f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="24" fill="{C_NODE}" stroke="{C_EDGE}"/>')
        out.append(f'<text x="{X:.1f}" y="{Y+4:.1f}" fill="{C_TXT}" text-anchor="middle" font-size="11" font-weight="600">{escape(system.processes[i][:12])}</text>')
    # right panel: what the loop costs
    out.append(f'<text x="380" y="70" fill="{C_TXT}" font-weight="600">Loop members: {len(comp)} of {n} processes</text>')
    out.append(f'<text x="380" y="92" fill="{C_MUT}">ρ(A) = {sol.rho:.4f}  (converges because &lt; 1)</text>')
    t1 = sol.tiers[1] if len(sol.tiers) > 1 else 0
    out.append(f'<text x="380" y="114" fill="{C_MUT}">Tier 1 (plain addition) = {_fmt(t1)} kWh</text>')
    out.append(f'<text x="380" y="136" fill="{C_MUT}">All tiers (the inverse)  = {_fmt(sol.ced)} kWh</text>')
    out.append(f'<text x="380" y="158" fill="{C_ACC}" font-weight="600">Addition misses {_fmt(sol.ced - t1)} kWh ({100*(sol.ced-t1)/sol.ced if sol.ced else 0:.1f} %)</text>')
    out.append(f'<text x="380" y="190" fill="{C_MUT}">99 % of the total is reached by tier {sol.tier_99}; 99.9 % by tier {sol.tier_999}.</text>')
    if len(comps) > 1:
        out.append(f'<text x="380" y="212" fill="{C_MUT}">{len(comps)-1} further smaller cycle(s) not drawn.</text>')
    out.append("</svg>")
    return "\n".join(out)


# ---------------------------------------------------------------- bars
def bars_svg(title: str, items: dict[str, float], unit: str = "kWh", color: str = C_MUT) -> str:
    items = {k: v for k, v in items.items() if v != 0}
    if not items:
        return f'<p style="color:{C_MUT}">{escape(title)}: nothing to show.</p>'
    ks = sorted(items, key=lambda k: -abs(items[k]))
    mx = max(abs(v) for v in items.values()) or 1
    total = sum(items.values()) or 1
    W, rowh, lab = 640, 22, 210
    H = 40 + rowh * len(ks)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" style="{FONT};max-width:{W}px">']
    out.append(f'<text x="0" y="16" fill="{C_TXT}" font-weight="600">{escape(title)}</text>')
    for r, k in enumerate(ks):
        y = 30 + r * rowh; v = items[k]; w = (W - lab - 90) * abs(v) / mx
        out.append(f'<text x="0" y="{y+14}" fill="{C_TXT}">{escape(str(k)[:30])}</text>')
        out.append(f'<rect x="{lab}" y="{y+3}" width="{w:.1f}" height="{rowh-8}" fill="{color}" rx="2"/>')
        out.append(f'<text x="{lab+w+6:.1f}" y="{y+14}" fill="{C_MUT}">{_fmt(v)} {unit} · {100*v/total:.1f} %</text>')
    out.append("</svg>")
    return "\n".join(out)


def interval_svg(p05: float, med: float, p95: float, central: float) -> str:
    W, H = 640, 90
    lo, hi = min(p05, central) * 0.95, max(p95, central) * 1.05
    sx = lambda v: 40 + (W - 80) * (v - lo) / (hi - lo if hi > lo else 1)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" style="{FONT};max-width:{W}px">']
    out.append(f'<text x="0" y="16" fill="{C_TXT}" font-weight="600">Interval (5th – 95th percentile) with median; the central deterministic value marked.</text>')
    out.append(f'<line x1="{sx(p05):.1f}" y1="50" x2="{sx(p95):.1f}" y2="50" stroke="{C_MUT}" stroke-width="10" stroke-linecap="round" opacity="0.5"/>')
    out.append(f'<line x1="{sx(med):.1f}" y1="38" x2="{sx(med):.1f}" y2="62" stroke="{C_TXT}" stroke-width="2"/>')
    out.append(f'<circle cx="{sx(central):.1f}" cy="50" r="5" fill="{C_ACC}"/>')
    out.append(f'<text x="{sx(p05):.1f}" y="80" fill="{C_MUT}" text-anchor="middle">p05 {_fmt(p05)}</text>')
    out.append(f'<text x="{sx(med):.1f}" y="30" fill="{C_TXT}" text-anchor="middle">median {_fmt(med)}</text>')
    out.append(f'<text x="{sx(p95):.1f}" y="80" fill="{C_MUT}" text-anchor="middle">p95 {_fmt(p95)}</text>')
    out.append(f'<text x="{sx(central):.1f}" y="{80 if abs(sx(central)-sx(p05))>60 and abs(sx(central)-sx(p95))>60 else 30}" fill="{C_ACC}" text-anchor="middle">central {_fmt(central)}</text>')
    out.append("</svg>")
    return "\n".join(out)

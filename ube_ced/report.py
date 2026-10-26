"""Section 5: the fixed report. JSON (machine) + HTML (human, self-contained, inline SVG) + short Markdown."""
from __future__ import annotations
from datetime import datetime, timezone
from html import escape
from pathlib import Path
import json
import numpy as np
from ._version import __version__ as _v
from .system import System, basket_vector
from .records import BasketItem, Status
from .solve import solve, Solution
from .stress import stress
from .propagate import propagate
from . import diagrams as dg


def build_report(system: System, basket: list[BasketItem] | None = None, draws: int = 10_000, seed: int = 0,
                 could_not_obtain: str = "", version: str | None = None) -> dict:
    fu = system.declaration.functional_unit
    if basket is None:
        f = system.unit_demand(fu["process"], float(fu["quantity"]))
        basket_rows = [{"process": fu["process"], "quantity": float(fu["quantity"]), "unit": fu["unit"], "status": "n/a (functional unit)"}]
    else:
        f = basket_vector(system, basket)
        basket_rows = [{"process": b.process, "quantity": b.quantity, "unit": b.unit, "status": b.status.value,
                        "low": b.low, "high": b.high, "source": b.source} for b in basket]
    sol = solve(system, f)
    st = stress(system, f)
    mc = propagate(system, f, basket, draws=draws, seed=seed)

    # status summary (weakest link for DERIVED is the modeller's duty at extension level; here we attribute external energy by its own status)
    by_status = {s.value: 0.0 for s in Status}
    Lf = sol.L @ f
    for x in system.external:
        by_status[x.status.value] += float(x.value * Lf[system.index(x.process)])
    per_item = []
    if basket:
        for b in basket:
            per_item.append({"process": b.process, "quantity": b.quantity, "unit": b.unit,
                             "kwh": float(sol.epsilon[system.index(b.process)] * b.quantity),
                             "epsilon": float(sol.epsilon[system.index(b.process)])})
    rep = {
        "identity": {"system": system.name, "declaration": system.declaration.as_dict(),
                     "input_hashes": dict(system.source_files), "core_version": version or _v, "seed": seed,
                     "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")},
        "headline": {"unit": "kWh external energy per functional unit",
                     "interval": {"p05": mc["p05"], "median": mc["median"], "p95": mc["p95"], "mean": mc["mean"]},
                     "central": sol.ced},
        "basket": basket_rows, "per_item": per_item,
        "decomposition": {"by_tag": sol.by_tag, "by_tier": sol.tiers, "by_sector": sol.by_sector,
                          "epsilon": {p: float(v) for p, v in zip(system.processes, sol.epsilon)}},
        "assumptions": [{k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in r.items()} for r in st],
        "sources": [{"kind": "coefficient", "key": f"{r.input} -> {r.output}", "value": r.value, "unit": r.unit, "status": r.status.value, "source": r.source}
                    for r in system.records if r.status != Status.ASSUMED] +
                   [{"kind": "external", "key": f"EXTERNAL -> {x.process}", "tags": x.tags, "value": x.value, "unit": x.unit, "status": x.status.value, "source": x.source}
                    for x in system.external if x.status != Status.ASSUMED],
        "status_summary": {"external_kwh_by_status": by_status,
                           "record_counts": {s.value: sum(1 for r in system.records if r.status == s) + sum(1 for x in system.external if x.status == s) for s in Status}},
        "convergence": {"rho": sol.rho, "tier_99": sol.tier_99, "tier_999": sol.tier_999, "tiers_computed": len(sol.tiers),
                        "reconciliation_gap": sol.reconciliation_gap, "rejected_draws": mc["rejected"],
                        "draws": mc["draws"], "draw_floor": mc["draw_floor"], "draw_floor_reason": mc["draw_floor_reason"],
                        "correlation_groups": mc["correlation_groups"], "zero_coefficients": sol.zero_coefficients},
        "conventions": [dict(c) for c in system.declaration.conventions],
        "could_not_obtain": could_not_obtain or "(not stated — the modeller must fill this)",
    }
    rep["_svg"] = {"tree": dg.backward_tree_svg(system, sol), "loop": dg.loop_svg(system, sol),
                   "interval": dg.interval_svg(mc["p05"], mc["median"], mc["p95"], sol.ced),
                   "tiers": dg.bars_svg("By upstream tier (e·Aᵏ·f)", {f"tier {k}": v for k, v in enumerate(sol.tiers) if v > 0}),
                   "sectors": dg.bars_svg("By originating process (e_i · (L f)_i)", sol.by_sector),
                   "tags": {k: dg.bars_svg(f"By tag '{k}'", v) for k, v in sol.by_tag.items()},
                   "items": dg.bars_svg("By basket line (ε_i · q_i)", {f"{r['process']} ({r['quantity']:g} {r['unit']})": r["kwh"] for r in per_item}) if per_item else ""}
    return rep


def _table(rows: list[dict], cols: list[str]) -> str:
    if not rows:
        return "<p class='mut'>none</p>"
    h = "".join(f"<th>{escape(c)}</th>" for c in cols)
    b = ""
    for r in rows:
        b += "<tr>" + "".join(f"<td>{escape(_cell(r.get(c)))}</td>" for c in cols) + "</tr>"
    return f"<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>"


def _cell(v) -> str:
    if v is None: return "—"
    if isinstance(v, float): return dg._fmt(v)
    if isinstance(v, dict): return "; ".join(f"{k}: {vv}" for k, vv in v.items()) if v else "—"
    return str(v)


def to_html(rep: dict) -> str:
    i, h, c, cv = rep["identity"], rep["headline"], rep["convergence"], rep["decomposition"]
    svg = rep["_svg"]
    decl = i["declaration"]
    conv_rows = rep["conventions"]
    css = """
    :root{--bg:#fbfbfd;--fg:#1a1f2b;--mut:#4a6b8a;--acc:#c8541b;--line:#d9dee7;--card:#fff}
    body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 ui-sans-serif,system-ui,Segoe UI,Helvetica,Arial;padding:16px}
    main{max-width:980px;margin:0 auto} h1{font-size:22px;margin:0 0 4px} h2{font-size:16px;margin:28px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}
    .mut{color:var(--mut)} .acc{color:var(--acc)} .card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:10px 0}
    .big{font-size:30px;font-weight:700} table{border-collapse:collapse;width:100%;font-size:13px} th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line);vertical-align:top}
    th{color:var(--mut);font-weight:600} code{background:#eef2f7;padding:1px 4px;border-radius:3px} .grid{display:grid;grid-template-columns:1fr 1fr;gap:12px} @media(max-width:700px){.grid{grid-template-columns:1fr}}
    """
    parts = [f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>CED report</title><style>{css}</style></head><body><main>"]
    parts.append(f"<h1>{escape(i['system'])}</h1><div class='mut'>Functional unit: {escape(str(decl['functional_unit']['quantity']))} {escape(decl['functional_unit']['unit'])} of {escape(decl['functional_unit']['process'])} · {escape(decl['place'])} · {escape(decl['instant'])} · core {escape(i['core_version'])} · seed {i['seed']} · {escape(i['generated_utc'])}</div>")
    # 2 headline
    parts.append("<h2>2 · Headline</h2><div class='card'>")
    parts.append(f"<div class='mut'>{escape(h['unit'])}</div><div class='big'>{dg._fmt(h['interval']['p05'])} – {dg._fmt(h['interval']['p95'])}</div><div>median {dg._fmt(h['interval']['median'])} · mean {dg._fmt(h['interval']['mean'])} · <span class='acc'>central (deterministic) {dg._fmt(h['central'])}</span></div>")
    parts.append(svg["interval"] + "</div>")
    # the two mandatory depictions
    parts.append("<h2>The chain, two ways</h2><div class='card'>" + svg["tree"] + "</div><div class='card'>" + svg["loop"] + "</div>")
    # 3 decomposition
    parts.append("<h2>3 · Decomposition</h2><div class='grid'>")
    if svg["items"]: parts.append("<div class='card'>" + svg["items"] + "</div>")
    for k, s in svg["tags"].items(): parts.append("<div class='card'>" + s + "</div>")
    parts.append("<div class='card'>" + svg["tiers"] + "</div><div class='card'>" + svg["sectors"] + "</div></div>")
    parts.append("<div class='card'><b>ε per unit of each process</b>" + _table([{"process": k, "kWh per unit": v} for k, v in cv["epsilon"].items()], ["process", "kWh per unit"]) + "</div>")
    # 4 assumptions
    parts.append("<h2>4 · Assumptions (ASSUMED records, ×0.5 / ×2 swing, largest first)</h2><div class='card'>")
    parts.append(_table(rep["assumptions"], ["kind", "key", "value", "unit", "x0.5", "x2", "swing", "swing_pct"]) + "</div>")
    # 5 sources
    parts.append("<h2>5 · Sources (MEASURED / DATABASE / DERIVED records)</h2><div class='card'>" + _table(rep["sources"], ["kind", "key", "value", "unit", "status", "source"]) + "</div>")
    # 6 status
    ss = rep["status_summary"]
    parts.append("<h2>6 · Status summary</h2><div class='card'>" + _table([{"status": k, "external kWh attributed": v, "records": ss["record_counts"][k]} for k, v in ss["external_kwh_by_status"].items()], ["status", "external kWh attributed", "records"]) + "</div>")
    # 7 convergence
    parts.append("<h2>7 · Convergence and reconciliation</h2><div class='card'>" + _table([
        {"item": "ρ(A)", "value": c["rho"]}, {"item": "tier reaching 99 %", "value": c["tier_99"]}, {"item": "tier reaching 99.9 %", "value": c["tier_999"]},
        {"item": "tiers computed", "value": c["tiers_computed"]}, {"item": "inversion vs series gap (relative)", "value": f"{c['reconciliation_gap']:.2e}"},
        {"item": "Monte Carlo draws", "value": f"{c['draws']} (floor {c['draw_floor']})"}, {"item": "rejected draws (non-productive)", "value": c["rejected_draws"]},
        {"item": "correlation groups", "value": ", ".join(c["correlation_groups"]) or "none declared (samples independent; interval may be too narrow)"},
        {"item": "zero coefficients in A", "value": c["zero_coefficients"]}], ["item", "value"]) + f"<p class='mut'>{escape(c['draw_floor_reason'])}</p></div>")
    # 8 conventions
    parts.append("<h2>8 · Declared conventions (verbatim from the specific model)</h2><div class='card'>" + _table(conv_rows, ["name", "value", "reason"]) + f"<p class='mut'><b>Boundary notes:</b> {escape(decl['boundary_notes'])}</p></div>")
    # 9 could not obtain
    parts.append("<h2>9 · What could not be obtained</h2><div class='card'>" + escape(rep["could_not_obtain"]) + "</div>")
    # 1 identity at the end for reference
    parts.append("<h2>1 · Identity</h2><div class='card'>" + _table([{"file": k, "sha256": v} for k, v in i["input_hashes"].items()], ["file", "sha256"]) + "</div>")
    parts.append("</main></body></html>")
    return "\n".join(parts)


def to_markdown(rep: dict) -> str:
    h, c = rep["headline"], rep["convergence"]
    lines = [f"# {rep['identity']['system']}", "",
             f"**{dg._fmt(h['interval']['p05'])} – {dg._fmt(h['interval']['p95'])} {h['unit']}** (median {dg._fmt(h['interval']['median'])}; central {dg._fmt(h['central'])})", ""]
    for k, v in rep["decomposition"]["by_tag"].items():
        lines.append(f"- by tag `{k}`: " + ", ".join(f"{kk} {dg._fmt(vv)}" for kk, vv in v.items()))
    lines.append(f"- ρ(A) {c['rho']:.4f}; 99 % by tier {c['tier_99']}; reconciliation gap {c['reconciliation_gap']:.1e}; draws {c['draws']}, rejected {c['rejected_draws']}")
    if rep["assumptions"]:
        a = rep["assumptions"][0]
        lines.append(f"- largest assumption swing: {a['key']} ({a['swing_pct']:.1f} %)")
    lines.append(f"- could not obtain: {rep['could_not_obtain']}")
    return "\n".join(lines) + "\n"


def write_report(rep: dict, out_dir: str | Path) -> dict:
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in rep.items() if not k.startswith("_")}
    (out_dir / "report.json").write_text(json.dumps(clean, indent=2, default=float), encoding="utf-8")
    (out_dir / "report.html").write_text(to_html(rep), encoding="utf-8")
    (out_dir / "report.md").write_text(to_markdown(rep), encoding="utf-8")
    return {"json": str(out_dir / "report.json"), "html": str(out_dir / "report.html"), "md": str(out_dir / "report.md")}

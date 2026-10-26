"""D10: a named set of overrides producing a new System. Files are never edited."""
from __future__ import annotations
from dataclasses import replace
from .system import System
from .records import Record, ExternalRecord


def scenario(system: System, name: str, coefficients: dict | None = None, external: dict | None = None) -> System:
    """coefficients: {(input, output): new_value}; external: {(process, tag_signature or None): new_value}.
    Scaling keeps low/high in proportion so the uncertainty shape is preserved."""
    s = system.copy()
    s.name = f"{system.name} :: {name}"
    recs = []
    for r in s.records:
        key = (r.input, r.output)
        if coefficients and key in coefficients:
            v = float(coefficients[key]); k = v / r.value if r.value else 1.0
            r = replace(r, value=v, low=r.low * k, high=r.high * k, note=(r.note + f" [scenario {name}]").strip())
        recs.append(r)
    exts = []
    for x in s.external:
        if external and x.process in external:
            v = float(external[x.process]); k = v / x.value if x.value else 1.0
            x = replace(x, value=v, low=x.low * k, high=x.high * k, note=(x.note + f" [scenario {name}]").strip())
        exts.append(x)
    s.records, s.external = recs, exts
    return s

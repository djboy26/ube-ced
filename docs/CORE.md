# The core, in one page

![core block diagram](core_block_diagram.svg)

| Stage | What goes in | What comes out | Refuses when |
|---|---|---|---|
| **load + validate** | a System YAML (processes, coefficient records, external records, declaration), optionally a basket YAML | a frozen `System` with input hashes | any record lacks value/unit/status/low/high; a non-ASSUMED record lacks a source; bounds do not bracket; units do not match the two processes; the declaration is missing a field; a process is duplicated |
| **solve** | `System`, demand vector f | ε per process; CED; tiers; by-sector; by-tag | Hawkins-Simon fails (a sub-block consumes ≥ it produces); inversion and tier series disagree beyond 1e-9 |
| **stress** | `System`, f | every ASSUMED record at ×0.5 and ×2 with its swing | never (nan if a stressed system is non-productive) |
| **propagate** | `System`, f, draws, seed | p05 · median · p95 · mean, rejected draws | draws below 10,000 |
| **report** | all of the above | report.json, report.html (inline SVG), report.md | never; section 9 is mandatory text |
| **battery** | a System file | 13 pass/fail rows | — |
| **conform** | a specific-model directory | per-case pass/fail, second-solver scan | — |

Run the fictional example:

```bash
cd examples/reference_condition
ube-ced run system.yaml --out out                      # one person-day (the functional unit)
ube-ced run system.yaml --basket basket_vulnerable_day.yaml --out out_v
ube-ced battery system.yaml --basket basket_vulnerable_day.yaml
ube-ced conform .
```

Open `out/report.html`. The two depictions required of every UBE description are both there: the backward-opening chain from the finished good, and the loop (steel needs electricity, electricity needs steel) that no tree can draw.

The full specification is `docs/SPEC_v2_core.md`.

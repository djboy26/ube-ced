# ube-ced

**Cumulative Energy Demand of survival goods, in primary kWh, by Leontief input-output.**
Reference implementation and the Danish survival-floor model of the Universal Basic Energy (UBE) project.

[![tests](https://github.com/djboy26/ube-ced/actions/workflows/tests.yml/badge.svg)](https://github.com/djboy26/ube-ced/actions)
License: code MIT, data and documents CC-BY-4.0.

## The claim this repository exists to make reproducible

Universal Basic Energy proposes that the cost of a survival basket be measured in the primary energy
the supply chain actually spends to deliver it, at the recipient's location, and that this quantity,
not a sum of money, be the unit the floor is guaranteed in.

The arithmetic is one equation:

```
ε = e_d · (I − A)⁻¹          primary kWh per unit of each process
CED(f) = ε · f               primary kWh for a basket f
```

`A` is the technical-coefficients matrix (physical units of input i per unit of output j),
`e_d` the direct primary-energy intensity of each process, `f` the final-demand vector.
The inverse resolves the infinite upstream regress (fertiliser needs electricity needs steel needs
electricity ...) in a single matrix operation; the power series `I + A + A² + ...` converges whenever
the Hawkins-Simon condition holds.

## What is here

| Path | What | Status |
|---|---|---|
| `ube_ced/` | Reference core: `System`, Leontief inverse, CED, tier and sector decomposition, basket, Monte Carlo. numpy only. | tested |
| `data/tomato_sixsector_2026-04.yaml` | Six-sector worked example from the April 2026 technical note. | **illustrative** |
| `model/wave4/ube_model_v5/` | The Danish survival-floor model, v5 (19 Sep 2026). Standard library only. 63 basket lines, Statistics Denmark IO tables, dwelling heat-balance, dietary-guideline food quantities, Monte Carlo. | **PROVISIONAL**, every output row says so |
| `docs/CANONICAL_FIGURES.md` | The one list of figures the project stands behind, and the figures it has withdrawn. | authoritative |
| `docs/ERRATA.md` | Arithmetic in the April note that does not reproduce from its own matrix. | |
| `docs/OPEN_QUESTIONS.md` | What is not settled. | |
| `docs/METHOD.md` | Axioms, definitions, consequences. | |

## Headline numbers, with their status

| Quantity | Value | Basis | Status |
|---|---|---|---|
| Danish survival floor, v5 | **6,761 kWh / person / year** | primary, LHV, DK-2023 grid PEF 1.6 | PROVISIONAL |
| same, fossil grid PEF 2.5 | 8,024 | | PROVISIONAL |
| same, renewable PEF 1.0 | 5,920 | | PROVISIONAL |
| Interval the project publishes | 6,500 – 9,400 kWh / person / year | canonical figures doc, Sept 2026 | |
| Winter tomato delivered in Denmark | about 11 kWh / kg | traced to recipient, ×1.4 loss multiplier | canonical |
| Six-sector toy tomato | 9.02 kWh / kg | `data/tomato_sixsector_2026-04.yaml` | illustrative |

**Withdrawn and not to be cited:** tomato 4.77 kWh/kg, tomato 18 kWh/kg, floor 11,953 kWh/yr,
"47 % of the floor is heating". See `docs/CANONICAL_FIGURES.md`.

## Run it

```bash
pip install -e ".[test]"
python -m pytest -q                       # reference core
python examples/01_tomato.py              # 9.021 kWh/kg, tiers, sectors
python examples/02_scenarios.py           # heat pump, renewable grid, open-field, vertical farm
cd model/wave4/ube_model_v5
python regression_tests.py                # 7 tests incl. reproduction of Statistics Denmark multipliers
python ube_model_v5.py                    # regenerates survival_goods_results_v5.csv
python verify_results_v5.py               # second implementation re-derives every cell
```

The v5 model regenerates its own results file byte-for-byte from the basket CSV, the parameter JSON
and the Statistics Denmark extracts (SHA-256 recorded). Delete the output, run it again, get the same file.

## How this differs from neighbouring proposals

| Proposal | Question it answers | Unit of the guarantee |
|---|---|---|
| NEF *Universal Basic Energy* (UK, 2022) | who pays the bill | money, via a rising-block tariff |
| Jun, *Universal Basic Energy Equity* (Korea, 2026) | who owns the generator | money, as dividends from infrastructure equity |
| Korean basic-energy-guarantee literature | minimum household energy services | delivered kWh of electricity and heat |
| **this repository** | what survival physically costs to deliver | **primary kWh, cumulative, at the recipient** |

The three above are compatible with this one. None of them computes the denominator.

## Cite

See `CITATION.cff`. A Zenodo DOI is minted on each tagged release.

## Author

Sourabh Jogalekar, Universal Basic Energy project. sourabhrj26@gmail.com

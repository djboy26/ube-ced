# Sources and provenance

Every number in `data/` must trace to a line here. If it does not, it is illustrative and the YAML says so.

## tomato_sixsector_2026-04.yaml

| Entry | Value | Status | Source |
|---|---|---|---|
| All A coefficients | see file | **illustrative** | UBE technical note, April 2026, §2.2. The note states: "values are illustrative but grounded in the supply chain analyses". No per-coefficient citation exists. |
| e_d Electricity | 2.5 kWh/kWh | scenario value | Fossil PEF, see pef_scenarios.yaml |
| e_d Diesel | 9.7 kWh/L | approximate | Diesel LHV 35.9 MJ/L = 9.97 kWh/L plus upstream; a production-energy ratio of 0.21 MJ/MJ (Oil & Gas Sci Tech 2020, 75:56, Table 2) gives 12.1 kWh/L primary. The note's 9.7 is below that. Flagged in ERRATA. |
| e_d Steel | 6.0 kWh/kg | approximate | Typical BF-BOF primary energy 20–25 GJ/t = 5.6–6.9 kWh/kg (worldsteel). |
| e_d Water | 0.3 kWh/m³ | approximate | Danish supply ~0.5 kWh/m³ electricity (project taxonomy doc) × PEF would exceed 0.3. Flagged in ERRATA. |

## pef_scenarios.yaml

| Scenario | PEF | Source |
|---|---|---|
| fossil | 2.5 | Thermal grid, ~40% conversion. |
| dk_2023 | 1.6 | Energistyrelsen, Danish grid 2023. Project policy baseline. |
| renewable | 1.0 | Convention: wind/solar counted at delivered energy. Contested; see OPEN_QUESTIONS Q3. |
| eu_2023_1791 | 1.9 | Directive (EU) 2023/1791, Annex, default PEF. |

## Figures used elsewhere in the project that are NOT in this repo yet

| Figure | Value | Where it lives | Why not here |
|---|---|---|---|
| Almería → Copenhagen route tomato | 2.55 kWh/kg (90% CI 2.29–2.87) | Project note 23 Oct 2026, Monte Carlo n=200,000 | Process-chain model, not yet expressed as an A matrix. Next milestone. |
| Danish market-average tomato | 11 kWh/kg | Project ruling Sept 2026, model line F_04 | Derivation not yet reconstructed in open form. See OPEN_QUESTIONS Q1. |
| Danish survival floor | 10,672–11,953 kWh/yr primary | Project locked parameter | Four unreconciled sources. See OPEN_QUESTIONS Q2. |

## Reference data sets for a validated system
- ecoinvent (licensed)
- AGRIBALYSE 3.x (free, French agri-food)
- Pérez Neira D. et al. (2018) Sci Total Environ 628–629:1627–1636. Almería heated multi-tunnel tomato.
- Torrellas M. et al. (2012) LCA of greenhouse tomato, Mediterranean vs Northern Europe.
- Millward-Hopkins J. et al. (2020) Providing decent living with minimum energy. Global Environ Change 65:102168.

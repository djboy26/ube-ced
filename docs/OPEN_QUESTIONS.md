# Open questions

Stated here so that nobody downstream mistakes a working value for a settled one.

## Q1. The 11 kWh/kg tomato: derivation in open form

The canonical figure for a winter tomato delivered to a person in Denmark is about 11 kWh/kg primary,
traced to the recipient including a Ã—1.4 loss multiplier. It is a market-weighted average across the
countries Denmark actually buys from (Spain ~40 %, Netherlands most of the rest, Denmark ~12 %).
The per-route components are not yet published as an A matrix in this repository. The AlmerÃ­a â†’
Copenhagen unheated route alone is 2.55 kWh/kg (90 % interval 2.29â€“2.87, Monte Carlo n = 200,000,
23 Oct 2026). Next milestone: express the market-weighted chain here so the 11 regenerates from source.

## Q2. The survival floor: which number

| Source | kWh / person / year | Basis |
|---|---|---|
| Model v5, this repo, DK-2023 grid | 6,761 | primary, LHV, PROVISIONAL |
| Model v5, fossil / renewable PEF | 8,024 / 5,920 | primary |
| Canonical figures doc, Sept 2026 | 6,500 â€“ 9,400 | primary, LHV, Danish 2023 grid |
| Earlier project figure (withdrawn) | 10,672 â€“ 11,953 | could not be reproduced from the model said to produce it |
| Taxonomy doc, household energy only | 7,800 â€“ 8,200 | final energy, not comparable |
| Millward-Hopkins et al. 2020, cold-climate upper bound | 4,720 â€“ 5,110 | final energy, not comparable |

The project publishes the interval. v5 sits inside it. The upper end of the interval comes from the
calibration range 1.0â€“2.5 on the dwelling heat balance (v5 step 4), carried through the Monte Carlo.
What would close this: an independent dwelling-energy reproduction against metered Danish stock
(BBR + ENE2HA by dwelling class), which is on the list.

## Q3. The renewable accounting convention

Counting wind and solar at delivered energy (PEF 1.0) is one convention. Counting them at the
physical-energy-content method or the direct-equivalent method gives different primary factors for
the same kWh. The project reports the triple (2.5 / 1.6 / 1.0) and has not ruled on the convention.
This also decides whether the energy stored in food and wood fibre counts as part of a good's CED.

## Q4. Healthcare

The healthcare line is a Leontief IO construction, about 640 / 1,000 / 2,200 kWh/cap/yr across the
three PEF scenarios, and must be caveated in any external citation until verified against EXIOBASE
Denmark. It reproduces Statistics Denmark's own human-health multiplier to within 2.4 %
(66.5 vs 64.9 GJ per million DKK), which is encouraging but is a check of the IO arithmetic, not of
the basket quantity.

## Q5. Diesel fuel-mix basis

Whether diesel's upstream primary energy is taken from a fossil-only refining chain or a
biofuel-blended Danish pump mix. Outstanding project decision.

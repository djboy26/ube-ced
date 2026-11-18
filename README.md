# UBE calculator: the public page

This branch (`calculator-site`) holds the public calculator page. The model it reads from is on `main`.

| Path | What it is |
|---|---|
| `index.html` | The whole page in one file. Fonts, drawing and data are inside it; it makes no outside requests. |
| `og.png` | The picture shown when the link is shared (1200 x 630). |
| `deploy/` | The build step used on Vercel. It fetches the two files above at a pinned commit, checks their SHA-256, and stamps the public address into the share tags. To publish a new version of the page: commit the new `index.html`, then put that commit's hash and the new SHA-256 values in `deploy/build.mjs`, and redeploy. |
| `checks/` | Checks of the page against model v5 and of the page against itself. |

## What the page computes

Primary energy for one person for one year in Denmark, in kWh, from model v5 (`main`, `model/wave4/ube_model_v5`).
The start state is 7,543 kWh a year on Denmark's 2023 grid: the model's floor of 6,761 plus healthcare 782 (provisional).
A typed number moves its kWh in proportion, which is how the model treats that quantity.

## Checks (18 Nov 2026)

Run from `checks/`, with `main` checked out beside this branch or `UBE_MODEL_V5` pointing at `model/wave4/ube_model_v5`.

| Script | What it does | Result |
|---|---|---|
| `t_model.py` | Runs model v5 unmodified for 13 cases (typed food, km, m2, litres, plug numbers, clothes, water, car, 41 litres, unticked goods, all at once) and types the same into the page. 44 goods x 3 grids each. | 1,716 values, largest gap 0.0003 kWh |
| `t_walk.py` | 3,300 random steps through the real controls at 1,440, 767 and 390 px, run with hidden and with classic scrollbars. After each step: goods sum to needs, needs to the total, root branches to the total, headline text equals the total, panels and wind shares cover it, the range brackets it, no sideways overflow. | 0 problems, 0 console messages |
| `t_link.py` | Sets a state, opens the shared link in a fresh page. | same numbers |
| `t_axe.py` | axe-core, WCAG 2 A and AA, three widths, basket closed and open. | 0 violations |
| `t_scrollbar.py` | Classic scrollbars at seven widths: the page must not be wider than its visible area. | 0 widths overflow |
| `t_overlap.py` | Boxes of every visible piece of text, five widths, three states: no words on other words. | 0 overlapping pairs |
| `t_covered.py` | Every text block and control, five widths, two states: nothing drawn later covers it. | 0 covered |

Shown whole kWh are rounded by largest remainder at the start state so every column sums to its total; a shown row can sit up to 0.55 kWh from the model's unrounded value.

The last three scripts fail on version 10 as it was and pass on this page.

Not checked here: the 18 town figures against an outside source (they come from the v5 dwelling model with PVGIS climate, built in an earlier session), real phones, Safari, Firefox.

## Fixes made on 18 Nov 2026

Three faults in version 10 of 11 Nov 2026, all on windows 1,100 px and wider. Nothing else in the page changed.

| Fault | Fix |
|---|---|
| The title, the place picker and the two small headings were painted under the drawing and could not be seen or used. | `.plate .head,.plate .eb{z-index:2}` |
| With scrollbars that take room (Windows), the plate was fitted before the scrollbar appeared and came out 15 px too wide, so the page scrolled sideways. | `html{overflow-y:scroll}` keeps the scrollbar's room from the start. |
| The last line of "How it's counted" ran into the key below it. | That block is 428 px wide instead of 372, and it and Fig. 3 start 22 px higher. |

All figures await independent checking.

# UBE CED Framework — Specification v2: the Core (UBE 101)

Status: v2, approved for implementation 26 Oct 2026 (DJ). Implemented in ube-ced 0.2.0. The project copy lives in the UBE project docs; this file is the repository copy.

## 0. Division of labour, fixed

| Layer | Contains | Does not contain |
|---|---|---|
| **Core** (this document) | Energy accounting at a fully specified reference condition. The formalism, the solver, provenance, uncertainty propagation, the report. Static. | Any place, year, grid, fuel mix, averaging rule, renewable convention, boundary preference, or number. |
| **Specific models** (§6) | Everything the core leaves open, declared explicitly, plus their own data and physics. | A second solver. Redefinitions of core terms. |

DJ's rulings of 26 Oct 2026 on diesel basis (Danish pump mix, option B) and the open rulings on renewable treatment and food energy content are **specific-model declarations**, recorded in the Denmark model's boundary file, not in the core.

---

## 1. Axioms of the core

**A1 (Conservation).** Energy delivered to a process came from somewhere and does not return. Every unit of output carries the energy its chain spent.

**A2 (Reference condition).** The core describes one place, one instant, one fully specified supply chain. Every process has exactly one known source for each of its inputs. There are no mixes, no averages, no marginal units. (The STP of this framework.)

**A3 (Decomposability).** At the reference condition, the chain is a finite set of n processes. Each produces one output in one physical unit and consumes fixed physical quantities of other processes' outputs per unit of its own.

**A4 (External energy).** Energy that enters the chain from outside it enters at identifiable processes in known quantities per unit of that process's output. The core calls this *external energy*; it does not name it primary, stock, flow, renewable or fossil. Those are tags (D6).

**A5 (Cost ≠ value).** The energy a chain spent is a physical quantity. The worth of the output is not. The core computes the first and has no term for the second.

**A6 (Provenance).** A number without a source is an assumption. It is admissible only when labelled as such, and the label travels to every output.

**A7 (Uncertainty).** Every input has an uncertainty. The output is therefore an interval. A point value alone is incomplete.

---

## 2. Definitions

**D1. Process.** A named node; one output, one unit. Set P = {p₁ … pₙ}.

**D2. Coefficient record.** The unit of data. Never a bare float.

| Field | Required | Meaning |
|---|---|---|
| `input`, `output` | yes | a_ij: units of input consumed per unit of output |
| `value` | yes | central value, ≥ 0 |
| `unit` | yes | input unit per output unit; must match the two processes |
| `status` | yes | MEASURED · DATABASE · DERIVED · ASSUMED |
| `source` | yes unless ASSUMED | citation, year, locator, accessed date |
| `low`, `high` | yes | bounds that bracket `value`; sampled triangularly (D7) |
| `tags` | no | free labels, e.g. `source_class: stock` |

**D3. External energy intensity e.** For each process, a coefficient record whose `input` is the reserved name `EXTERNAL` and whose unit is kWh per unit of the process's output. A process may have several EXTERNAL records with different `tags`; they sum.

**D4. Reference-condition declaration.** Required before any solve.

| Field | Content |
|---|---|
| `functional_unit` | the output being costed, quantity and unit |
| `place`, `instant` | where and when the reference condition holds |
| `boundary_notes` | which inputs are inside the chain and which are external, in prose |
| `conventions` | a list of named choices the specific model made (§6); the core stores them, validates presence, and does not interpret them |

**D5. Status.**

| Status | Meaning |
|---|---|
| MEASURED | measured for this chain |
| DATABASE | from a recognised LCI database or peer-reviewed study of a comparable process |
| DERIVED | computed by a registered extension (§6) from MEASURED/DATABASE inputs; reported at the weakest input status |
| ASSUMED | stated without a source; listed in every report and stress-tested (C8) |

**D6. Tags.** Free key:value labels on any record. The core treats them as opaque strings and offers decomposition by any tag (C5). It defines none. (`stock` / `flow`, `renewable` / `fossil`, `domestic` / `imported` are examples a specific model may use.)

**D7. Uncertainty representation.** Three numbers per record: `low`, `value`, `high`. Sampling is triangular between them. The output is reported as numbers (median, 5th, 95th percentile), never as a distribution name. `fixed` is permitted only for definitional constants (3.6 MJ/kWh).

**D8. System.** (P, A, e, declaration) assembled from D1–D4. Unspecified a_ij are zero and the count of zeros is reported.

**D9. Final demand f.** Length-n vector of physical quantities, each entry a coefficient record of the functional unit.

**D10. Scenario.** A named set of overrides producing a new System from an existing one. Files are never edited by a scenario.

---

## 3. Consequences

**C1 (Solver).** ε = e · (I − A)⁻¹ and CED(f) = ε · f, in kWh of external energy per functional unit. [A1, A3, A4, D8, D9]

**C2 (Existence).** (I − A)⁻¹ exists and is non-negative iff Hawkins-Simon holds (all leading principal minors of I − A positive; for A ≥ 0, equivalently ρ(A) < 1). The solver refuses otherwise and names the failing sub-block. [A3]

**C3 (Tier series).** (I − A)⁻¹ = Σₖ Aᵏ. Term k is the k-th upstream tier. Reported until the residual < 10⁻⁹ of the total, with the tier at which 99 % is reached. [C1, C2]

**C4 (Sector attribution).** CED = Σᵢ e[i] · (L f)[i], exactly. [C1]

**C5 (Tag decomposition).** Because e is a sum of tagged records and C1 is linear, CED decomposes exactly by any tag: CED = Σ_t CED_t where CED_t uses only the EXTERNAL records carrying tag t. The core reports this for every tag key present. [A4, D3, D6, C1]

**C6 (Linearity).** CED(f₁ + f₂) = CED(f₁) + CED(f₂). A basket is the sum of its lines. [C1]

**C7 (Two implementations).** Every result is computed by inversion (C1) and by tier summation (C3). The core refuses to emit a result on which they disagree by more than 10⁻⁹ relative. [C1, C3]

**C8 (Assumption stress).** For each ASSUMED record, the central result is recomputed at value × 0.5 and × 2; the swing is reported beside the headline, largest first. [A6, D5]

**C9 (Uncertainty propagation).** Each record is sampled per D7, independently unless a correlation group is declared on the records; the system is re-solved per draw; draws failing C2 are counted. Output: median, mean, p5, p95, rejected-draw count. Floor 10,000 draws; the floor and its reason are printed in the report. [A7, D7, C1]

**C10 (Comparability).** Two results are comparable only if their D4 declarations are identical in every field. The core refuses to difference or ratio otherwise and names the differing field. [D4]

**C11 (Determinism).** Same inputs and seed, byte-identical output. Input SHA-256 hashes are written into the output. [A6]

**C12 (Report, not prose).** Every run emits the fixed report (§5). A figure not in a report is not a result of this framework. [A6, A7]

---

## 4. Interfaces

```
load_system(path)           -> System        # refuses on any D2/D4 violation; lists all violations at once
solve(System, f)            -> Solution      # C1–C7
stress(System, f)           -> StressTable   # C8
propagate(System, f, n)     -> Interval      # C9
scenario(System, overrides) -> System        # D10
build_report / write_report -> Report        # §5
battery(path)               -> BatteryResult # §7
conform(model_dir)          -> ConformResult # §6
```

File format: YAML, one System per file, coefficients as a list of D2 records. Any other format enters only through a registered extension that attaches provenance.

---

## 5. The report (fixed structure)

1. Identity: system name, full D4 declaration, input hashes, core version, seed.
2. Headline: interval (C9) then central value, in kWh of external energy per functional unit.
3. Decomposition by every tag key present (C5), by tier (C3), by sector (C4).
4. Assumptions: every ASSUMED record with its ×0.5 / ×2 swing (C8).
5. Sources: every MEASURED/DATABASE record with its citation.
6. Status summary: share of CED by status, weakest-link for DERIVED.
7. Convergence: tiers to 99 % and 99.9 %; rejected draws; draw count and floor.
8. Declared conventions (from D4), verbatim.
9. What could not be obtained: free text, mandatory, may say "nothing".

The HTML report also carries the two depictions required of every UBE description: the backward-opening chain from the finished good, and the interdependent loop a tree cannot draw.

---

## 6. Specific models: the conformance contract

A specific model is a directory with: System files; zero or more **extensions** (named modules that compute DERIVED records from their own physics and emit them as D2 records with provenance); a `conformance.yaml` naming the published results it reproduces; a README stating its conventions in prose.

**Conventions a specific model must declare** (the core validates that each is present; it never chooses):

| Convention | Examples of values | Denmark model ruling (DJ, 26 Oct 2026) |
|---|---|---|
| Aggregation over time | instant · hourly · annual mean | annual mean, as a simplification stated and justified |
| Attribution frame | average (attributional) · marginal (consequential) | average, consistent with Leontief IO |
| External-energy tagging | which sources are `stock`, which `flow`; how each is measured | open |
| Electricity external energy | per-generator at reference condition · grid factor by convention | open; must state convention and the number it would give under the alternatives |
| Fuel upstream basis | commodity chain · local pump mix | **local pump mix (B)**, with the reason: the boundary is the recipient's location and a Danish vehicle burns the Danish legal blend; the commodity-chain figure is also reported for comparison |
| Loss convention | carried by sold · none · explicit | open |
| Packaging, capital goods, food energy content | included · excluded | open |

Rules:

| Rule | Enforced by |
|---|---|
| S1. Computes through `solve()`. No second solver. | `conform()` scan; S2 is the real enforcement |
| S2. Reproduces its own published results through the core to 10⁻⁶ relative. | `conform()` |
| S3. Extensions only add records; they may not alter A, e, or the declaration after load. | System is frozen at load |
| S4. May narrow a declaration field; may not add fields the core lacks. | schema |
| S5. Every figure in its README appears in a generated report. | review |

First conformance target: Danish floor model v5, frozen. The core is complete when `conform(denmark_v5)` passes all 189 cells with no edit to v5.

---

## 7. Corruption battery

Mutations the core must catch at load or solve, or must produce a different output hash: transpose A; negate a value; swap two process units; make a sub-block non-productive; drop a status; drop a source on a DATABASE record; bounds that do not bracket the value; alter a declaration field; duplicate a process name; mismatched unit; external energy not in kWh; a changed coefficient and a changed external value must change the hash. Specific models inherit and may add.

---

## 8. Explicitly outside the core

Any country, good, year, grid, PEF, fuel mix, averaging rule, renewable convention, stock/flow assignment, loss rule, boundary preference, valuation, co-product allocation (deferred; until then declared ASSUMED by the extension), and time dynamics.

---

## 9. Settled and open

| # | Item | State |
|---|---|---|
| 1 | Uncertainty as three numbers per record, output as numbers | settled |
| 2 | 10,000-draw floor, stated in method | settled |
| 3 | Reconciliation 10⁻⁹ | settled |
| 4 | Conformance 10⁻⁶ | settled |
| 5 | Diesel basis | settled for Denmark model: B |
| 6 | Renewable / electricity convention | moved to Denmark model; open there |
| 7 | Food energy content in boundary | moved to Denmark model; open there |

---

## 10. Self-critique

- Tag decomposition (C5) is where the stock/flow idea lives without the core taking a position. The cost of that neutrality: the core cannot stop a specific model from tagging wind as `stock`. Only review can.
- The reference condition (A2) is an idealisation no real dataset meets. Every specific model is therefore an aggregation of reference conditions, and the aggregation rule is the single largest source of disagreement between models. The core makes that rule mandatory to declare; it cannot make it right.
- Independence of samples (C9) understates the interval when one external factor feeds many records. Correlation groups are available; nothing forces their use.
- Already known: the accounting is standard IO-LCA (Leontief 1970 on pollution, Bullard & Herendeen 1975 on energy). Specific to this framework: tag-native decomposition through the inverse, the reference-condition separation of core from convention, and the conformance contract. Neither wrong nor new on the arithmetic; the structure is the contribution.

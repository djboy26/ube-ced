# Method, from axioms

## Axioms

A1. Every good delivered to a person required energy to be spent along its supply chain, and that
energy does not return. (First and second laws.)

A2. A supply chain can be represented as a finite set of n processes, each producing one output in a
fixed physical unit, each consuming fixed quantities of the others' outputs per unit of its own.
(Leontief 1936; fixed-proportions production.)

A3. Primary energy enters the system from outside it, at identifiable processes, in known quantities
per unit of that process's output.

## Definitions

D1. A : n×n, a_ij = units of output i consumed per unit of output j. Columns are recipes.

D2. e_d : length n, e_d[i] = primary energy (kWh, lower heating value) entering from outside the
system per unit of output i.

D3. f : length n, the final demand, in physical units.

D4. L = (I − A)⁻¹, the total-requirements matrix.

D5. ε = e_d L, the cumulative energy intensity. ε[j] is primary kWh per unit of j, all tiers.

D6. CED(f) = ε f.

## Consequences

C1 (from A2, D4). L = Σ_{k≥0} A^k whenever ρ(A) < 1. The k-th term is the k-th upstream tier.
Proof: Neumann series. Hawkins-Simon (all leading principal minors of I − A positive) is equivalent,
for non-negative A, to ρ(A) < 1 and L ≥ 0.

C2 (from D5). The scalar case n = 1 gives ε = e_d / (1 − a), the geometric-series formula.

C3 (from D5, D6). CED is linear in f. A basket's CED is the sum of its items' CEDs. No interaction terms.

C4 (from D5). Tier decomposition: CED = Σ_k e_d A^k f. Sector decomposition: CED = Σ_i e_d[i] (L f)[i].
Both sum exactly to the total. Tested in `tests/test_core.py`.

C5 (from C1). A local edit to one coefficient propagates through every feedback loop with one
re-inversion. Scenarios are edits to A or e_d, nothing else.

C6 (from A3, D2). The primary energy factor of grid electricity is an e_d entry, so every
electricity-dependent CED is reported as a triple (fossil 2.5 / DK-2023 1.6 / renewable 1.0).

## What the method does not claim

N1. ε is a cost, not a value. Worth is situation-specific (the diamond–water paradox). UBE is not a
theory of value and never will be. The claim is bounded: for satiable survival needs, where demand
is inelastic and energy is the residual input, the energy-denominated cost is the physically
occurring description. Above the floor, prices do what only prices can do.

N2. A matrix from illustrative coefficients gives an illustrative result. The six-sector example in
`data/` is that. The Danish model in `model/denmark_v5/` is built from Statistics Denmark IO tables
and carries PROVISIONAL on every row until independently verified.

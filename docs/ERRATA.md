# Errata: the April 2026 technical note

The technical note *Computing the Thermodynamic Cost of Survival* (April 2026) prints a six-sector
A matrix and e_d vector (§2.2, §4.1) and then prints results (§3.3, §5.1, §6.1). The printed results
do not follow from the printed matrix. This repository runs the matrix as printed; the note's
arithmetic is superseded by `examples/01_tomato.py`.

| Quantity | Note prints | Matrix gives | Ratio |
|---|---|---|---|
| CED, 1 kg tomato | 8.74 kWh | **9.021 kWh** | 1.03 |
| Tier 1, e_d A f | 7.73 | 7.715 | 1.00 |
| Tier 2, e_d A² f | 0.89 | 0.985 | 1.11 |
| Tier 3, e_d A³ f | 0.11 | 0.268 | 2.43 |
| Tier 4 | 0.01 | 0.042 | 4.2 |
| L[Electricity, Tomato] | 3.68 kWh | 3.368 kWh | 0.92 |
| L[Diesel, Tomato] | 0.066 L | 0.0555 L | 0.84 |
| L[Water, Tomato] | 0.125 m³ | 0.1175 m³ | 0.94 |
| Spectral radius ρ(A) | not given | 0.1935 | |

Scenario table (§6.1), recomputed:

| Scenario | Note says | Computed |
|---|---|---|
| 100 % renewable grid (e_d elec 2.5 → 1.0) | ↓ 40–50 % | **−56.0 %** |
| Heat pump (A[elec, tomato] 3.0 → 1.0) | ↓ 55–65 % | −62.7 % |
| Green ammonia (A[diesel, fert] → 0) | ↓ 5–10 % | **−0.1 %** |
| Spanish open-field | ↓ 70–80 % | −74.9 % |
| Vertical farm (A[elec, tomato] → 20) | ↑ 300–500 % | +532.9 % |

The green-ammonia line is the one that matters: in the printed matrix, fertiliser is 0.005 kg per kg
of tomato and diesel-for-fertiliser is 0.1 L per kg fertiliser, so removing it changes the tomato by
0.005 × 0.1 × 9.7 ≈ 0.005 kWh. The note's 5–10 % cannot come from this matrix.

None of this touches the equation, which is exact. It touches an illustrative example whose numbers
were evidently written by hand. The note also flags two e_d values that are low against sources
(`data/SOURCES.md`): diesel 9.7 kWh/L against ~12 with upstream, water 0.3 kWh/m³ against ~0.5 delivered.

Status of the six-sector example after this erratum: **illustrative**, as the note itself says.
It is kept because it is the smallest system that exhibits every feature of the method (feedback
loops, tier convergence, scenario edits), not because any of its coefficients is measured.

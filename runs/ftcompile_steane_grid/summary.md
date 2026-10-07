# Steane flag round on the 3x4 grid: compilation vs single-fault tolerance

Verifier: Stim detector error model, exact check that no two single events (incl. no error) share a signature with different logical effect (= circuit distance >= 3, the project's C1 = 0 criterion). Noise for the check and C1: p = 0.001 on CX/prep/meas/incoming, p/10 idle on every other active qubit per CX. C1 = first-order logical failure probability / p under an optimal decoder.

## A. One round in detail: labels B0213B x6, hub 1

| Compiler | CNOTs | logical CNOTs kept (of 36) | single-fault FT | conflicting signatures | C1 |
|---|---:|---:|---:|---:|---:|
| unrouted | 36 | 36 | True | 0 | 0.000 |
| qiskit_default_no_routing | 24 | 24 | False | 8 | 1.067 |
| qiskit_opt1_no_routing | 36 | 36 | True | 0 | 0.000 |
| sabre_opt1 (5 seeds) | [102, 102, 102, 99, 105] | 36 | 0/5 seeds | [8, 9, 10, 6, 9] | [2.401, 2.801, 3.201, 2.801, 2.801] |
| sabre_default (5 seeds) | [78, 84, 78, 78, 81] | 24 | 0/5 seeds | [16, 16, 11, 17, 18] | [6.567, 7.167, 6.2, 6.767, 7.068] |
| bridge_shortest | 142 | 36 | False | 9 | 5.534 |
| bridge_ancilla_first | 142 | 36 | True | 0 | 0.000 |
| bridge_shortest + repair | 142 | 36 | True | 0 | 0.000 |

Repair of bridge_shortest: success=True, 59 verifier calls, 6 routes changed, CNOTs 142 -> 142.

| Route (check.interaction) | path before | path after |
|---|---|---|
| c0.i1 | 6-2-1-0 | 6-5-4-0 |
| c1.i1 | 6-2-1-0 | 6-5-4-0 |
| c2.i1 | 6-2-1-0 | 6-5-4-0 |
| c3.i1 | 0-1-2-6 | 0-4-5-6 |
| c4.i1 | 0-1-2-6 | 0-4-5-6 |
| c5.i1 | 0-1-2-6 | 0-4-5-6 |

Example witness for bridge_shortest (two single events, same detectors, different logical effect):

- logical flip none: `bridge:c0.i1 Z2 X1`
- logical flip (1,): `bridge:c0.i4 Z7 X11`, `bridge:c0.i4 X6 Y7`, `bridge:c0.i4 Y6 X7`

### Logical error rate after one round (order-2 lookup decoder)

| Compiler | p=0.002 | p=0.001 | p=0.0005 | p=0.00025 | log-log slope |
|---|---:|---:|---:|---:|---:|
| unrouted | 2.54e-03 (254/100000) | 5.93e-04 (178/300000) | 1.62e-04 (162/1000000) | 3.65e-05 (146/4000000) | 2.02 |
| qiskit_default_no_routing | 3.85e-03 (385/100000) | 1.56e-03 (156/100000) | 6.97e-04 (209/300000) | 2.90e-04 (174/600000) | 1.24 |
| sabre_opt1 | 1.80e-02 (1797/100000) | 5.95e-03 (595/100000) | 2.13e-03 (213/100000) | 8.25e-04 (165/200000) | 1.48 |
| bridge_shortest | 3.48e-02 (3475/100000) | 1.18e-02 (1185/100000) | 4.51e-03 (451/100000) | 1.70e-03 (170/100000) | 1.45 |
| bridge_shortest_repaired | 2.43e-02 (2428/100000) | 6.84e-03 (684/100000) | 1.75e-03 (175/100000) | 3.90e-04 (156/400000) | 1.98 |

Slope near 2 = second-order (fault-tolerant); near 1 = single faults cause logical errors.

## B. Sweep: 96 logical rounds (48 certified local templates x 2 hubs, same template on all checks)

| Compiler | single-fault FT | median CNOTs |
|---|---:|---:|
| sabre_opt1 | 0/96 | 103.5 |
| sabre_default | 0/96 | 78 |
| bridge_shortest | 0/96 | 156 |
| bridge_ancilla_first | 32/96 | 156 |

Repair (only bridge path changes, budget 150 verifier calls):

| Start from | failing rounds | repaired | stuck (no single change helps) | budget exhausted | median calls (repaired) | CNOT change (repaired, median) |
|---|---:|---:|---:|---:|---:|---:|
| bridge_shortest | 96 | 40 | 25 | 31 | 61 | +4 |
| bridge_ancilla_first | 64 | 25 | 39 | 0 | 13 | +8 |

## Scope

- One code (Steane, flag extraction, six serialized checks), one 12-node grid, one placement, one round with an ideal final read-out.
- Repair only changes the physical path of each logical CNOT; placement, hubs, templates and check order are fixed. "Stuck" means no single path change lowers the first-order failure; it does not prove that no path assignment works.
- Noise strengths are uniform and synthetic; the FT verdict itself does not depend on them.
- Runtime: 555s.

# Flag-bridge gadgets: matching hand-designed layouts automatically

Change from the earlier family: a data CNOT may target a flag (inside that flag's window) instead of the syndrome qubit, so flags double as bridges, as in Lao & Almudever (2020) and Rodriguez-Blanco et al. (2025). The four (or more) ancillas are generic: each check picks which one is its syndrome qubit and which are its flags. No remote CNOTs are used. Every round below passes the exact full-round single-fault check (circuit distance >= 3, idle noise included).

## Every split of a support between syndrome and flags is realizable

For each check, every way of assigning its four data qubits to the syndrome qubit or a flag has a certified pattern: one flag 16/16 splits, two flags 65/65 (all six checks: True). So whether a check can be done without routing is pure geometry: one flag needs an adjacent ancilla pair whose neighbours cover the support (6 CNOTs); two flags need a syndrome ancilla with two adjacent flag ancillas covering it (8 CNOTs).

## Exact minimum CNOTs per round (CP-SAT over all placements)

| Grid | Ancillas | Min CNOTs per round | Gadgets per support (flags) | Full-round FT verified |
|---|---:|---:|---|---|
| 2x5 | 3 | infeasible | - | - |
| 3x4 | 3 | 40 | 2, 1, 1 | True |
| 3x4 | 4 | 40 | 1, 2, 1 | True |
| 4x4 | 4 | 40 | 2, 1, 1 | True |
| 4x4 | 6 | 40 | 2, 1, 1 | True |
| 4x5 | 5 | 40 | 1, 2, 1 | True |
| 5x5 | 5 | 40 | 1, 2, 1 | True |
| 4x5 | 6 | 36 | 1, 1, 1 | True |
| 5x5 | 6 | 36 | 1, 1, 1 | True |

Why these are optimal for the family: each check costs 6 CNOTs only with one flag and no routing; otherwise at least 8 (a second flag) or 9 (any bridge replaces 1 CNOT by at least 4). X and Z checks share their support, so a support that cannot be done with one flag costs at least 2 x 2 extra. For every row with 40, CP-SAT proves that no placement gives all three supports a one-flag gadget, so 40 is the minimum there. 36 appears only with 6 ancillas on a large enough grid (not on 4x4); 3 ancillas already reach 40 on 3x4. Two-row grids cannot avoid routing at all.

3x4, 3 ancillas (40 CNOTs):

```
.. d1 d4 d6
d5 a0 a1 a2
.. d3 d0 d2
```

5x5, 6 ancillas (36 CNOTs):

```
.. d3 .. .. ..
a0 a1 d2 .. ..
d1 d0 a2 a3 ..
a4 a5 d4 d6 ..
.. d5 .. .. ..
```

Gadgets of the 3x4 round (tokens: digits = support positions, A/B = flag CNOTs; couplers: which ancilla each data CNOT uses):

| Check | Syndrome | Flags | Tokens | Couplers |
|---|---|---|---|---|
| X0 | a1 | a0, a2 | `AB0123AB` | `--SABA--` |
| X1 | a0 | a1 | `A0123A` | `-ASAS-` |
| X2 | a1 | a2 | `A0123A` | `-SASA-` |
| Z0 | a1 | a0, a2 | `AB0123AB` | `--SABA--` |
| Z1 | a0 | a1 | `A0123A` | `-ASAS-` |
| Z2 | a1 | a2 | `A0123A` | `-SASA-` |

## Logical error rate after one round

Order-2 lookup decoder, ideal final read-out; same noise model as before (p on CNOTs, prep, readout and incoming data; p/10 idle).

| Round | CNOTs | FT | p = 0.001 | p = 0.0005 | p = 0.00025 | slope |
|---|---:|---|---:|---:|---:|---:|
| routed, current layout (3x4) | 142 | True | 6.81e-03 | 1.52e-03 | 4.84e-04 | 1.91 |
| routed, best placement (3x4) | 78 | True | 2.26e-03 | 6.30e-04 | 1.55e-04 | 1.93 |
| flag-bridge, 3x4, 3 ancillas | 40 | True | 8.17e-04 | 1.90e-04 | 4.74e-05 | 2.05 |
| flag-bridge, 5x5, 6 ancillas | 36 | True | 6.83e-04 | 1.77e-04 | 4.26e-05 | 2.00 |
| no routing needed (all-to-all reference) | 36 | True | 6.12e-04 | 1.49e-04 | 4.10e-05 | 1.95 |

## Comparison with the hand-designed layouts

| Layout | Hardware | Ancillas | CNOTs per round | Source |
|---|---|---:|---:|---|
| Rodriguez-Blanco et al. 2025, citadel | 4x4 grid | 4 | 48 | rebuilt from their Fig. 2, FT verified |
| this search | 4x4 grid | 4 | 40 | above |
| this search | 3x4 grid | 3 | 40 | above |
| Lao & Almudever 2020, Steane-c1-L2 (serial) | IBM-20 | 6 | 36 | rebuilt from their Figs. 1c, 4a, 8a, FT verified |
| this search | IBM-20 | 2 | 36 | `run_ftcompile_published.py` |
| this search | 5x5 grid | 6 | 36 | above |
| Lao & Almudever 2020, Steane-c3-L2 (parallel) | IBM-20 | 4 | 30 | rebuilt from their Figs. 5b, 8c, FT verified |

Details, logical error rates and caveats: `runs/ftcompile_published/summary.md`. The minima above are for one check at a time; Lao's parallel block, which measures three checks with shared ancillas, needs fewer CNOTs than any serialized round (it uses IBM-20's diagonal couplers and a degree-5 ancilla).

## Scope

- Steane code, six serialized checks, square grids, one or two flags per check.
- Runtime: 92s.

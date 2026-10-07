# Parallel flag-bridge blocks on a square grid

All three checks of one type measured at once with shared ancillas and a single flag, as in Lao & Almudever's 30-CNOT parallel round, but restricted to nearest-neighbour CNOTs on a plain square grid. Model and search: `ftcompile/parallel.py`.

## Result

A full round (X block, then Z block) with **28 CNOTs**: 7 data + 4 ancillas inside a 4x4 grid, 14 CNOTs per check type. It passes the exact single-fault check (FT: True).

```
 ..  d0  d2  ..
 d1  F0  a1  d3
 d4  a2  a3  d6
 ..  d5  ..  ..
```

d0-d6 data, F0 the flag (starts in |+>, read out in X), a1/a2/a3 the syndrome qubits of the three checks. Z block in time order (the X block is the same with every CNOT reversed and |0>/|+>, Z/X swapped):

`CX(d2->a1) CX(F0->a1) CX(d0->F0) CX(F0->a2) CX(a1->a3) CX(d1->F0) CX(d6->a3) CX(F0->a1) CX(d4->a2) CX(a2->a3) CX(d0->F0) CX(d3->a1) CX(F0->a2) CX(d5->a2)`

How it works: the flag F0 spreads a cat state to a1 and a2, and a1 passes it on to a3. When an ancilla leaves the cat it also picks up everything the neighbour it leaves through has collected, so one coupling can count towards several checks (a1 ends with d0, d1 from F0 plus its own d2, d3). a3 enters through a1 and leaves through a2, using the fourth edge of the square; this is what makes 8 couplings enough (only d0, which is in all three checks, needs two). The full Stim check confirms that any two single faults with different logical effects leave different syndrome and flag patterns.

## Lower bound within the model

- 4 ancillas, every ancilla-CNOT sequence up to 7 CNOTs on all 5 shapes: 298 designs reach 13 or fewer CNOTs per block linearly; 0 of them pass the necessary hook conditions. At 14: 7133 designs, 680 pass the hook conditions.
- 5 ancillas, every ancilla-CNOT sequence up to 6 CNOTs on all 12 shapes: 1236 designs reach 13 or fewer CNOTs per block linearly; 0 of them pass the necessary hook conditions.
- 4 ancillas, sequences of at most 3 ancilla CNOTs (any number of couplings per data qubit): 3414 valid designs, 0 pass at 13.
- 5 ancillas, sequences of at most 3 ancilla CNOTs (any number of couplings per data qubit): 22302 valid designs, 0 pass at 13.

A block costs (ancilla CNOTs) + (data couplings), and every data qubit needs at least one coupling, so 13 CNOTs allows at most 6 ancilla CNOTs; with 4 or more ancilla CNOTs no data qubit can use more than 3 couplings, and sequences of at most 3 ancilla CNOTs are checked separately. The hook test is exact (CP-SAT over syndrome assignment, data placement and coupling choice) and only uses fault locations every schedule has (Z faults on ancillas between ancilla CNOTs, from idle and ancilla-CNOT noise), so failing it rules a design out.

**So with 4 or 5 ancillas and one flag, 14 CNOTs per type (28 per round) is the minimum on a square grid.**

Sanity check: the model reproduces Lao's block on IBM-20 (linear cost 15, hook test passes at 15: True, fails at 14 for that ancilla sequence: True, Stim FT: True).

## Comparison

| Round | Hardware | Ancillas | CNOTs | FT | p = 0.001 | p = 0.0005 | p = 0.00025 | slope |
|---|---|---:|---:|---|---:|---:|---:|---:|
| this search, parallel | 4x4 grid | 4 | 28 | True | 5.50e-04 | 1.23e-04 | 2.99e-05 | 2.10 |
| Poór, Rodatz & Kissinger 2025 (rebuilt) | all-to-all | 4 | 28 | True | 5.20e-04 | 1.37e-04 | 3.52e-05 | 1.94 |
| Lao & Almudever 2020, c3-L2 parallel | IBM-20 | 4 | 30 | True | 5.44e-04 | 1.28e-04 | 3.19e-05 | 2.05 |
| this search, serialized (earlier step) | 3x4 grid | 3 | 40 | True | 7.68e-04 | 1.95e-04 | 5.15e-05 | 1.95 |
| Rodriguez-Blanco et al. 2025, citadel | 4x4 grid | 4 | 48 | True | 9.38e-04 | 2.51e-04 | 6.50e-05 | 1.93 |
| all-to-all serialized reference | complete graph | 2 | 36 | True | 6.27e-04 | 1.48e-04 | 3.94e-05 | 2.00 |

Logical error rate after one round: order-2 lookup decoder, ideal final read-out, p on CNOTs, prep, read-out and incoming data, p/10 idle per CNOT on every other qubit.

## Related work

- Poór, Rodatz & Kissinger, "Ultra Low Overhead Syndrome Extraction for the Steane Code" (arXiv:2511.13700, 2025): the same count, 14 CNOTs per type with 4 ancillas, with no connectivity constraints and an adaptive protocol (discard flagged rounds, run an 11-CNOT recovery circuit). Rebuilt from their Fig. 2a, their round has 28 CNOTs and passes our check too (FT: True). But its four ancillas are coupled in all 6 pairs (4 triangles) and one ancilla has 6 partners, so it cannot be placed on a square grid, which has no triangles and at most 4 neighbours per qubit (exact subgraph search: fits a square grid False; fits IBM-20's crossed squares True). We know of no other 28-CNOT round that fits a square grid.
- Their optimality proof shows 11 CNOTs are needed without flags and that flagging an 11-CNOT circuit costs at least 3 more. It does not cover a 12-CNOT circuit plus one flag CNOT, so whether 13 per type is possible with unrestricted connectivity is open as far as we can tell. The hook test here cannot settle it: with all-to-all couplings many designs pass it, because it ignores faults between couplings in the same gap.
- Lao & Almudever 2020: 30 CNOTs with diagonal couplers (IBM-20). Rodriguez-Blanco et al. 2025: 48 CNOTs on a 4x4 grid. Chao & Reichardt and Reichardt (2018), Liou & Lai (arXiv:2208.00581): parallel flag circuits without connectivity limits.

## Scope and caveats

- Model: one flag per block; the other ancillas are read out in Z and may measure any stabilizer products (as in Poór et al.), redundant or 0, as long as the syndrome can be recovered; same design for the X and Z blocks; checks of one type measured together. By the Steane code's automorphisms one read-out basis per read-out subspace suffices (checked: identical results with all 168 bases for 4 ancillas). Rounds outside the model (two flags, mixing X and Z checks in one block, 6+ ancillas) are not covered by the lower bound.
- The lower bound uses our noise model, which has idle noise on every qubit after every CNOT; without idle noise fewer fault locations exist and the bound is not claimed.
- Fault tolerance is single-fault circuit distance 3 for one round plus an ideal read-out, not an adaptive protocol.
- Runtime: 999s (with --full).

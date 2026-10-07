# Published flag-bridge rounds, rebuilt and checked

The hand-designed Steane rounds of Rodriguez-Blanco et al. 2025 (arXiv:2504.01083) and Lao & Almudever 2020 (arXiv:1909.07628) were transcribed gate by gate from their figures (`ftcompile/published.py`) and run through the same exact single-fault check, decoder and noise model as our own layouts. Paper data labels were mapped onto this project's Steane labelling by matching stabilizer supports.

| Round | Hardware | Ancillas | CNOTs | Single-fault FT | p = 0.001 | p = 0.0005 | p = 0.00025 | slope |
|---|---|---:|---:|---|---:|---:|---:|---:|
| Rodriguez-Blanco et al. 2025, citadel (rebuilt) | 4x4 grid | 4 | 48 | True | 9.38e-04 | 2.51e-04 | 6.50e-05 | 1.93 |
| this search, 4x4 | 4x4 grid | 4 | 40 | True | 7.95e-04 | 2.01e-04 | 4.60e-05 | 2.06 |
| this search, 3x4 | 3x4 grid | 3 | 40 | True | 7.75e-04 | 1.91e-04 | 4.76e-05 | 2.01 |
| Lao & Almudever 2020, c1-L2 serial (rebuilt) | IBM-20 | 6 | 36 | True | 6.93e-04 | 1.60e-04 | 4.60e-05 | 1.96 |
| this search, IBM-20 | IBM-20 | 2 | 36 | True | 7.18e-04 | 1.64e-04 | 4.19e-05 | 2.05 |
| Lao & Almudever 2020, c3-L2 parallel (rebuilt) | IBM-20 | 4 | 30 | True | 5.44e-04 | 1.28e-04 | 3.19e-05 | 2.05 |
| all-to-all reference | complete graph | 2 | 36 | True | 6.27e-04 | 1.48e-04 | 3.94e-05 | 2.00 |

Logical error rate after one round, order-2 lookup decoder, ideal final read-out; p on CNOTs, prep, read-out and incoming data, p/10 idle on every other qubit per CNOT (every CNOT is its own time step, so the parallel round gets no credit for its shorter depth).

## What the rebuild shows

- Both published designs pass our check: one noisy round plus an ideal read-out has circuit distance 3.
- The citadel round costs 48 CNOTs (8 per check: one syndrome and two flags). On the same 4x4 grid with the same 4 ancillas the exact search needs 40, and 3 ancillas on a 3x4 grid also give 40.
- Lao's serial IBM-20 figures fix the gadget gate order but not which data qubit plays a, b, c, d. All 2240 readings the couplers allow (14 x 20 x 8 per plaquette) were checked: 2240 pass. Every reading costs 36 CNOTs with 6 ancillas. On the same IBM-20 graph the exact search reaches 36 with only 2 ancillas (picture below).
- Lao's parallel c3-L2 round measures all three Z (then X) checks in one 4-ancilla block and costs 30 CNOTs. It is fault-tolerant under our check too, and beats every serialized round here, ours included: "proven minimum" for our layouts means within the one-check-at-a-time family. It relies on IBM-20's crossed couplers (4 diagonal CNOTs per check type) and on a qubit with 5 partners (s2), so it cannot be placed on a square grid (maximum degree 4) as drawn.
- Fig. 1b "Circuit 3" of Rodriguez-Blanco et al., read literally, closes the two flags in the same order it opens them. Used for S2 it is rejected: non-deterministic syndrome/flag read-out. Their Fig. 2b circuits close in reverse order and are correct, so this is a drawing slip, not a flaw in their results.

Spread over readings of Lao c1-L2 at p = 0.001:

| Reading | Logical error rate | 95% interval |
|---|---:|---|
| (0, 0, 0) | 6.21e-04 | 5.66e-04 to 6.83e-04 |
| (8, 5, 6) | 6.34e-04 | 5.78e-04 to 6.96e-04 |
| (3, 17, 1) | 5.93e-04 | 5.39e-04 to 6.53e-04 |
| (10, 2, 1) | 6.70e-04 | 6.12e-04 to 7.33e-04 |
| (1, 4, 5) | 5.76e-04 | 5.22e-04 to 6.35e-04 |
| (1, 17, 0) | 6.00e-04 | 5.45e-04 to 6.60e-04 |
| (13, 14, 2) | 6.06e-04 | 5.51e-04 to 6.66e-04 |
| (2, 8, 1) | 6.10e-04 | 5.55e-04 to 6.71e-04 |

## Exact serialized optimum on IBM-20

| Ancillas | Min CNOTs | Full-round FT verified |
|---:|---:|---|
| 2 | 36 | True |
| 3 | 36 | True |
| 6 | 36 | True |

IBM-20, 2 ancillas, 36 CNOTs (rows of the 4 x 5 coupling graph of Lao Fig. 6b):

```
.. .. .. d3 d1
.. .. .. a0 d2
.. d4 a1 d6 ..
.. d0 d5 .. ..
```

## Caveats

- Different fault-tolerance criteria. Both papers use an adaptive protocol (stop at the first flag or non-trivial syndrome, then run a second full round) with flag-aware lookup or neural-network decoders. Ours is one non-adaptive round followed by an ideal read-out. Passing ours is evidence their circuits are sound, not a reproduction of their logical error rates.
- Different noise model from both papers (they use p/15 two-qubit depolarizing per Pauli, 2p/3 preparation/measurement flips, and explicit Hadamards); all rows here share ours, so the comparison between rows is fair, the absolute numbers are not theirs.
- Not rebuilt: Lao's Steane-c1-L1 (Surface-17), whose figure marks data qubits 2 and 6 at two places each ("2/-", "-/2"), and Steane-c2 (32-36 CNOTs), which uses Fig. 5a, whose data lines are not labelled.
- Rodriguez-Blanco et al. draw only the X checks; their Z checks are taken as the Hadamard dual, which their text implies ("share the same connectivity requirements").
- Runtime: 85s.

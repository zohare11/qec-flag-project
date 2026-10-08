# Steane syndrome extraction on heavy-hex (IBM): first results

Patch used: 154 qubits, 176 couplers; 44 qubits have 3 neighbours, 110 have 2 (`ftcompile/heavyhex.py`). Corner qubits (3 neighbours) only touch side qubits (2 neighbours), so the graph has no triangles, no squares, and its shortest cycle is a 12-qubit hexagon.

## 1. Off-the-shelf routing breaks fault tolerance

| Round routed by Qiskit (SABRE layout + routing) | Compilations | CNOTs after routing | Fault-tolerant |
|---|---:|---|---:|
| serialized flag round, 36 CNOTs | 16 | 72-126 | 0 of 16 |
| parallel round (this project, square grid), 28 CNOTs | 16 | 79-100 | 0 of 16 |
| parallel round (Poór et al.), 28 CNOTs | 16 | 82-115 | 0 of 16 |

Optimization levels 1 and 3, 8 seeds each. SWAPs move data qubits mid-round and a single fault on a SWAP spreads to two data qubits; none of the compiled rounds keeps circuit distance 3.

## 2. No routing-free round with one or two flags per check

| Ancillas | Exact search (CP-SAT over all placements) |
|---:|---|
| 2 | infeasible |
| 3 | infeasible |
| 4 | infeasible |
| 5 | infeasible |
| 6 | infeasible |

Why, in general: a one-flag gadget needs two adjacent ancillas whose other neighbours hold the 4 data qubits; adjacent qubits are one corner and one side qubit, with at most 2 + 1 = 3 free neighbours. A two-flag gadget works only as corner - side - corner, whose 4 free neighbours must be exactly that check's data. Two such gadgets cannot share a corner (the other gadget's side qubit would have to be a data qubit of this check), and the data qubit in all three checks has only 2 corner neighbours, so three disjoint gadgets cannot all reach it. So every heavy-hex round needs either three or more flags per check, or routing.

## 3. A parallel block needs at least 9 ancillas

| Connected ancillas | Sets checked | Most data positions next to them |
|---:|---:|---:|
| 4 | 128 | 4 |
| 5 | 194 | 5 |
| 6 | 304 | 5 |
| 7 | 496 | 6 |
| 8 | 830 | 6 |
| 9 | 1422 | 7 |

All 7 data qubits must sit next to the ancillas; a tree of a corners and side qubits has a + 2 free neighbours, so 7 needs 5 corners and 9 ancillas. A cat state over 9 ancillas costs 16 CNOTs before any data coupling, so one parallel block costs at least 23 CNOTs per check type here, against 14 on a square grid.

## 4. Status of the exact synthesis

`ftcompile/synth_sat.py` encodes a whole block (any ancilla CNOTs, any data couplings, data placement, all single ancilla Z faults and CNOT fault pairs) as SAT with XOR clauses (CryptoMiniSat). On the square grid it finds the 14-CNOT block from scratch in about 2 minutes, and Stim confirms it. On a 9-ancilla heavy-hex row it returned no answer within 15 minutes for 26 slots. Next: fix the ancilla CNOT skeleton (cat trees) and let the solver place the couplings, which is a much smaller problem.

Runtime: 112s.

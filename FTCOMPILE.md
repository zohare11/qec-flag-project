# ftcompile: Stim-based core for "does compilation keep fault tolerance?"

A small, independent rewrite of the project's core on top of [Stim](https://github.com/quantumlib/Stim).
It replaces the custom Pauli-propagation verifier for new work; the old `qecflag/` and
`ftrepair*/` code is kept as history.

## What it does

```
logical round (virtual qubits)  --compiler-->  physical program (graph nodes)
physical program  --to_stim-->  noisy Stim circuit + detectors + observables
Stim circuit      --single_fault_check-->  pass/fail + fault witnesses
```

| File | Contents |
|---|---|
| `ftcompile/core.py` | Steane code, flagged six-check round, 3x4 grid + placement, Stim circuit builder, exact single-fault check |
| `ftcompile/compilers.py` | bridge compiler (paths chosen by a policy or overridden), Qiskit compiler (SABRE routing and/or optimizer), unrouted reference |
| `ftcompile/repair.py` | witness-guided repair: change the path of the routes that appear in fault witnesses until the check passes |
| `ftcompile/decode.py` | order-2 maximum-likelihood lookup decoder and logical-error sampling |
| `ftcompile/exact.py` | exact repairability oracle: per-route fault signatures -> CP-SAT model over path choices (feasible? fewest route changes? fewest CNOTs?) |
| `ftcompile/placement.py` | the same oracle made fast enough for placement search: placement-independent Stim tail maps + bridge residual tables |
| `ftcompile/gadgets.py` | flag-bridge gadgets (data may couple to a flag), certified patterns, exact minimum-CNOT layouts with CP-SAT on grids or any coupling graph |
| `ftcompile/published.py` | published hand-designed rounds rebuilt gate by gate: Rodriguez-Blanco et al. 2025 (4x4 citadel), Lao & Almudever 2020 (IBM-20, serial and parallel) |
| `run_ftcompile_case.py` | the case study (writes `runs/ftcompile_steane_grid/summary.md`) |
| `run_ftcompile_exact.py` | oracle over all 96 rounds, compared with greedy repair (writes `exact_summary.md`; run the case study first) |
| `run_ftcompile_placement.py` | placement search on the 3x4 grid (writes `runs/ftcompile_placement/summary.md`) |
| `run_ftcompile_flagbridge.py` | flag-bridge layouts, exact optima on several grids (writes `runs/ftcompile_flagbridge/summary.md`) |
| `run_ftcompile_published.py` | the published rounds checked and compared with the exact optima on the same hardware (writes `runs/ftcompile_published/summary.md`) |
| `tests/test_ftcompile.py` | bridge identity, agreement with the old verifier, repair, Qiskit flag stripping, decoder sanity |
| `tests/test_ftcompile_exact.py` | the route decomposition is exact; oracle solutions verify; an impossible round is reported |
| `tests/test_ftcompile_placement.py` | fast evaluator matches full Stim on random placements; placement changes repairability |
| `tests/test_ftcompile_gadgets.py` | flag-bridge patterns measure correctly, window rule enforced, 3x4 optimum is 40 and verifies |
| `tests/test_ftcompile_published.py` | the rebuilt published rounds are FT with the stated CNOT counts; IBM-20 reaches 36 with 2 ancillas |

**Single-fault FT** = after one noisy round and an ideal final read-out, no single fault (or single
incoming data error) shares a detector signature with another single event that has a different
logical effect. That is circuit-level distance >= 3, the same criterion as the old `C1 = 0`.
It is checked exactly from Stim's detector error model in ~50 ms per circuit.

**Witness** = a conflicting signature plus the circuit locations behind it. Every noise instruction
is tagged with the compiler decision that created it (`bridge:c2.i3` = a fault on a bridge CNOT of
check 2, interaction 3), so a witness points straight at the route to change.

## Run it

```
source .venv/bin/activate
python -m pip install -r requirements.txt     # adds stim, qiskit, networkx, ortools
python -m pytest -q tests/test_ftcompile.py   # ~10 s
python run_ftcompile_case.py --quick          # ~1 min smoke run
python run_ftcompile_case.py                  # full case study, several minutes
python run_ftcompile_exact.py                 # exact oracle on all 96 rounds, ~5-10 minutes
python run_ftcompile_placement.py             # placement search, ~30-60 minutes (--quick: ~3 minutes)
python run_ftcompile_flagbridge.py            # flag-bridge optima, ~5 minutes
python run_ftcompile_published.py             # published rounds vs exact optima, ~2 minutes
```

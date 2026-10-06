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
| `run_ftcompile_case.py` | the case study (writes `runs/ftcompile_steane_grid/summary.md`) |
| `tests/test_ftcompile.py` | bridge identity, agreement with the old verifier, repair, Qiskit flag stripping, decoder sanity |

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
python -m pip install -r requirements.txt     # adds stim, qiskit, networkx
python -m pytest -q tests/test_ftcompile.py   # ~10 s
python run_ftcompile_case.py --quick          # ~1 min smoke run
python run_ftcompile_case.py                  # full case study, several minutes
```

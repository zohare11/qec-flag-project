# Phase 5 guide

Phase 5 keeps the same `qec_flag_project` and the same `.venv`.

## Install

```bash
cd ~/Downloads
unzip -q -o qec_flag_phase5_patch.zip
cp -R qec_flag_phase5_patch/. ~/qec_flag_project/
cd ~/qec_flag_project
source .venv/bin/activate
```

## Verify the environment

```bash
python run_phase5.py doctor
python -m pytest -q
```

The assistant-side merged project passed 446 tests.

## Inspect the fixed hardware model

```bash
python run_phase5.py build-cache
```

Expected headline values:

- 96 actions per check = 48 certified flag templates x 2 syndrome-hub placements.
- `96^6 = 782,757,789,696` complete six-check schedules.
- synthetic 12-node, 3x4 nearest-neighbour graph.

## Smoke run

```bash
python run_phase5.py all \
  --config configs/phase5_smoke.json \
  --out runs/phase5_smoke
```

If that output directory already exists, use a new name such as `runs/phase5_smoke_2`.

The smoke run is a software/integration test, not a scientific conclusion.

## Full run

```bash
python run_phase5.py all \
  --config configs/phase5_full.json \
  --out runs/phase5_full
```

Use a new output directory rather than deleting a previous run.

## Main output

Open and paste:

```text
runs/phase5_full/phase5_summary.md
```

The report compares reference, fixed, routing-only heuristic, hardware-aware local greedy, equal-budget random search, equal-budget coordinate search, policy greedy, and equal-budget policy beam. It also reports native-CX count, duration, hub usage, and reduced finite-p diagnostics.

## Scientific interpretation

Phase 5 is deliberately a reduced hardware-aware model. Remote CNOT routing is represented by SWAP-forward / CNOT / SWAP-back native gate counts and durations. Native edge calibration and data-idle exposure are folded into schedule-dependent effective logical fault weights before the exact Phase-4 malignant-pair calculation. The inserted routing gates are not individually fault-enumerated. A positive result would justify building an explicit native-circuit fault simulator next; it would not itself establish hardware performance.

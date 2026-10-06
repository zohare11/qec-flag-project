# Phase 6 guide

Phase 6 validates Phase-5 schedules with an explicit native routed-CNOT fault model. It does **not** train a new policy.

## 1. Environment

Use the existing project and virtual environment:

```bash
cd ~/qec_flag_project
source .venv/bin/activate
python run_phase6.py doctor
```

## 2. Tests

```bash
python -m pytest -q
```

## 3. Inspect one explicit native circuit

```bash
python run_phase6.py inspect-native
```

This expands the reference schedule into native routed CNOTs and reports explicit single-fault decoder checks, C1, and C2.

## 4. Smoke run

Point `--phase5-run` at the Phase-5 run directory containing `phase5_policy_seed*.npz`. For the normal naming used in the guide:

```bash
python run_phase6.py all \
  --config configs/phase6_smoke.json \
  --phase5-run runs/phase5_full \
  --out runs/phase6_smoke
```

If your Phase-5 folder was `phase5_full_2`, use that exact path instead.

## 5. Full run

```bash
python run_phase6.py all \
  --config configs/phase6_full.json \
  --phase5-run runs/phase5_full \
  --out runs/phase6_full
```

The full run validates fresh `hw_id`, `ood_hub0_bad`, `ood_logical_shift`, and `ood_mixed` contexts. It compares schedules selected by the Phase-5 reference, local greedy, random search, coordinate search, and each saved policy-beam model.

The main output is:

```text
runs/phase6_full/phase6_summary.md
```

Phase 6 reports:

- Phase-5 surrogate C2;
- explicit native C1 and C2;
- the small-p native score `p*C1 + p^2*C2`;
- whether every single native fault is correctable;
- rank correlation between the surrogate and explicit native model;
- whether the surrogate and native model select the same best listed method;
- direct finite-p native-fault Monte Carlo diagnostics on one fresh ID context.

A nonzero C1 is scientifically important: it means naive inserted routing gates have introduced a first-order logical-failure mechanism, so the Phase-5 reduced C2 model is not sufficient for that routed implementation.

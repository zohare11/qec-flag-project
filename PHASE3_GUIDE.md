# Phase 3: sequential fault-tolerant schedule synthesis

Use the same `qec_flag_project` and the same `.venv`. Do **not** create another virtual environment.

## 1. Verify the merged files

From the project root:

```bash
source .venv/bin/activate
python run_phase3.py doctor
```

## 2. Run all tests

```bash
python -m pytest -q
```

The exact pass count can increase if earlier phases add tests; there should be no failures.

## 3. Build the exact certified catalogs once

```bash
python run_phase3.py build-cache
```

This creates generated files under `cache/`. The expanded cache verifies 10,800 grammar-complete candidates and stores only the 4,896 certified schedules in a compact exact C2 representation. The first build takes longer than later runs; later commands load the cache.

Expected structural counts:

- Phase 3A: 360 candidates, 96 certified.
- Phase 3B: 10,800 candidates, 4,896 certified.
- Phase 3B certified breakdown: 96 A-only, 96 B-only, 4,704 using both flags.

## 4. Smoke run

```bash
python run_phase3.py all --config configs/phase3_smoke.json --out runs/phase3_smoke
```

This checks the complete training/evaluation/noise-diagnostic path.

## 5. Full run

```bash
python run_phase3.py all --config configs/phase3_full.json --out runs/phase3_full
```

If that directory already exists, use a new name such as `runs/phase3_full_2`. The runner refuses to overwrite nonempty evidence directories.

## 6. Read the results

Open:

```text
runs/phase3_full/phase3_summary.md
```

Also retained:

- `phase3_verification.json`
- `phase3_training_summary.json`
- `phase3_3A_evaluation.json`
- `phase3_3B_evaluation.json`
- `phase3_3A_cases.csv`
- `phase3_3B_cases.csv`
- `phase3_3A_noise.json`
- `phase3_3B_noise.json`
- one saved actor-critic `.npz` and training curve CSV per phase/seed

## What to inspect

### Phase 3A

The policy is asked to rediscover good schedules from the known one-flag family sequentially. This is a machinery-validation benchmark. Compare `policy_greedy`, `policy_beam`, random search, and the 96-schedule oracle.

### Phase 3B

The policy chooses flag A only, flag B only, or both flags and constructs the schedule. Inspect:

1. `oracle_kind_fraction`: does the exact expanded oracle genuinely choose different architectures under different noise contexts?
2. `expanded_vs_one_flag`: does adding the second flag ever strictly improve C2 over the best one-flag design?
3. policy-greedy regret: how good is one learned synthesis with no online cost search?
4. policy-beam versus equal-budget random search: does policy guidance improve a small online search budget?
5. OOD families: does the learned construction rule transfer when flag/data/readout/Pauli error structure changes?

## Interpretation

A successful Phase 3B result means the policy learned useful sequential design structure **within this grammar**. It does not establish arbitrary fault-tolerant circuit discovery or hardware advantage. A weak result is also useful: the exhaustive oracle and one-flag restriction reveal whether the expanded design space itself contains worthwhile circuits before attributing anything to RL.

# FT Compiler Repair Fork v1

This branch freezes the Phase-10 scheduling/RL line and starts a new research objective:

> Can an exact physical single-fault verifier automatically detect, localize, and repair fault-tolerance violations introduced by compilation?

The branch deliberately keeps the verifier authoritative. No learned model decides whether a circuit is safe.

## What is new

Two deterministic repair loops are implemented.

### A. Routing/lowering repair

A logically single-fault-tolerant six-check Steane extraction round is compiled physically. The repair benchmark deliberately injects one locally valid compiler choice that preserves logical fault tolerance but causes the bridge-routed physical implementation to fail exact single-fault certification.

The loop is:

1. verify the logical input is still single-fault FT;
2. compile with the old SWAP router and record physical fault witnesses;
3. replace SWAP routing with the bridge compiler;
4. if the same lowered circuit is still unsafe, extract the checks implicated by exact failing single-fault witnesses;
5. mutate only implicated local lowering choices using options that occur in the Phase-7 certified catalog;
6. rank proposed repairs with the cheap bridge proxy;
7. call the exact physical verifier on proposals in that order;
8. accept only a circuit with C1=0, zero conflicts, zero single-fault failures, and zero incoming-single-error failures.

The repair engine is in `ftrepair/routing_repair.py`.

### B. Parallel-schedule repair

The second loop starts from a resource-valid but unsafe aggressive parallel schedule.

1. exactly certify the schedule;
2. identify the physical single-fault outcomes that fail;
3. localize each witness to overlapping stabilizer-check streams;
4. score check pairs by witness weight;
5. add one pairwise precedence constraint;
6. reschedule;
7. recertify;
8. repeat until the schedule is safe or the constraint budget is exhausted.

A precedence constraint does more than prohibit simultaneous CNOTs. It prevents the two constrained CNOT streams from interleaving; priority decides which stream must complete first. Prep/measurement blocks remain free to overlap when resources allow.

The implementation is in `ftrepair/schedule_repair.py`.

## Safety objective

Repair is lexicographic. A candidate is inadmissible unless all of the following hold:

- ideal circuit behavior is correct;
- C1 = 0;
- single-fault decoder conflicts = 0;
- single-fault logical failures = 0;
- incoming-single-error failures = 0.

Only after those conditions are satisfied do proxy cost, native-CX count, duration, or number of edits matter.

## Install

Keep the current `qec_flag_project` and virtual environment. Merge this patch into the existing project; the old Phase 1-10 scripts remain untouched.

```bash
cd ~/Downloads
unzip -q -o ft_compiler_repair_fork_patch.zip
cp -R ft_compiler_repair_fork_patch/. ~/qec_flag_project/

cd ~/qec_flag_project
source .venv/bin/activate
```

## Basic checks

```bash
python run_ft_repair.py doctor
python -m pytest -q tests/test_ft_repair.py
```

The new repair-specific test file contains 5 tests.

## Inspect one routing repair

```bash
python run_ft_repair.py inspect-routing
```

The output shows the unsafe SWAP compilation, the still-unsafe bridge lowering when applicable, the localized check, the repair edits, verifier-call count, and the final certificate.

## Inspect one scheduling repair

```bash
python run_ft_repair.py inspect-schedule
```

The deterministic reference case uses `shortest_greedy`. The repair trace lists each added precedence constraint and the C1 value after recertification.

## Smoke experiment

```bash
python run_ft_repair.py all \
  --config configs/ft_repair_smoke.json \
  --out runs/ft_repair_smoke
```

Or use process-isolated execution:

```bash
python run_ft_repair.py split \
  --config configs/ft_repair_smoke.json \
  --out runs/ft_repair_smoke_split
```

## Full experiment

```bash
python run_ft_repair.py split \
  --config configs/ft_repair_full.json \
  --out runs/ft_repair_full
```

The full configuration evaluates six synthetic calibration families. It uses four controlled routing/lowering violations and four scheduling-repair cases per family.

## Outputs

The main report is:

`runs/ft_repair_full/ft_repair_summary.md`

Raw outputs:

- `ft_repair_results.json`
- `ft_repair_routing.csv`
- `ft_repair_scheduling.csv`

The routing CSV records whether the injected check was among the checks actually modified by the repair engine. The scheduling CSV records the number of constraints, verifier calls, final C1, remaining native-CX parallelism, and duration speedup relative to both full serialization and the safe Phase-10 ancilla-overlap fallback.

## What would count as a positive v1 result?

The strongest outcome is not merely 100% repair success. It is:

- exact repair success with few verifier calls;
- the changed checks coincide with witness-localized compiler choices;
- scheduling repair reaches C1=0 without globally serializing all CNOTs;
- repaired safe schedules retain a duration advantage over the known-safe fallback.

The smoke reference run already exercises that path, but it is only a development check.

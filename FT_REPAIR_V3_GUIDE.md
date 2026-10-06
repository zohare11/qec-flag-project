# FT Compiler Repair v3 Guide

## Purpose

FT Compiler Repair v3 is the next research branch after the Phase-10 scheduling study and the v1/v2 compiler-repair prototypes.  It tests a sharper hypothesis:

> Exact physical single-fault counterexamples contain enough local structure to guide *fine-grained* repairs of hardware routing and scheduling decisions without discarding all compiler optimization.

V3 is deliberately not an ML phase.  Every accepted circuit/schedule must pass the exact single-fault verifier already used in the earlier project.

## What changed from v2

V2 localized failures mostly at the stabilizer-check level and repaired schedules with whole-check pair precedence constraints.  V3 adds four major capabilities.

1. **Operation-level failure localization.** Native failure witnesses are aggregated by check, logical route, native bridge gate, physical edge, Pauli fault, and weight.
2. **Per-route physical repair.** A repair can change one bridge path without replacing the entire stabilizer check.  Hub/template/CNOT-order replacements remain available through the 96-action local compiler table.
3. **Operation-level schedule precedence.** A repair may constrain one physical operation to finish before another begins instead of serializing two entire check streams.
4. **Cross-layer portfolio repair.** Several exactly certified routing repairs can be carried forward into scheduling, so the final selection can account for downstream schedulability rather than accepting the first serially safe lowering.

V3 also adds process-local verifier caching and chunk-first exact deletion minimization of safe constraint sets.

## Safety contract

Optimization is lexicographically subordinate to safety.  A repair is accepted only when all of the following hold under the existing controlled Pauli/Clifford model:

- `C1 == 0`
- zero decoder single-fault conflicts
- zero single-fault logical failures
- zero incoming-single-data-error failures

A proxy score, path cost, schedule duration, edit count, or hitting-set objective can only rank *candidate* repairs.  None can certify safety.

## Main new files

- `run_ft_repair_v3.py`
- `ftrepair_v3/model.py` — physical compiler state and path-overridden bridge plans
- `ftrepair_v3/cache.py` — process-local exact-verifier memoization
- `ftrepair_v3/localization.py` — operation/route-level failure cores
- `ftrepair_v3/routing_cegis.py` — richer multi-defect routing/lowering CEGIS
- `ftrepair_v3/hittingset_bb.py` — bounded exact/greedy hitting-set utilities
- `ftrepair_v3/op_scheduler.py` — operation-level precedence scheduling and repair
- `ftrepair_v3/cross_layer.py` — staged and cross-layer routing/scheduling portfolios
- `ftrepair_v3/mutations.py` — hidden check-choice and physical-path mutation benchmarks
- `ftrepair_v3/experiment.py` — benchmark/report generation
- `tests/test_ft_repair_v3.py`

## Install

Overlay this patch on the same project and use the existing virtual environment:

```bash
cd ~/Downloads
unzip -q -o ft_compiler_repair_v3_patch.zip
cp -R ft_compiler_repair_v3_patch/. ~/qec_flag_project/
cd ~/qec_flag_project
source .venv/bin/activate
```

Do not create another environment.

## Doctor

```bash
python run_ft_repair_v3.py doctor
```

The branch should identify itself as `ft-compiler-repair-v3`.

## Tests

Run the new tests:

```bash
python -m pytest -q tests/test_ft_repair_v3.py
```

The v3 tests are computationally heavier than ordinary unit tests because several invoke the exact physical single-fault verifier.  If a combined run is slow, run the expensive tests individually rather than interpreting a timeout as a scientific failure.

The v1 regression suite can also be checked with:

```bash
python -m pytest -q tests/test_ft_repair.py
```

## Inspection commands

### Multi-defect lowering repair

```bash
python run_ft_repair_v3.py inspect-routing
```

This generates a hidden two-check compiler mutation and prints operation-level localization plus the repair trajectory.

### Physical path defect

```bash
python run_ft_repair_v3.py inspect-path
```

This searches for a semantics-preserving alternative bridge path that breaks physical single-fault FT, then asks v3 to repair it without being told the mutated route.

### Operation-level scheduling

```bash
python run_ft_repair_v3.py inspect-schedule
```

This starts from an aggressive resource-valid schedule.  The primary v3 scheduler first attempts pure operation-level CEGIS.  If that is insufficient, it constructs a conservative exactly safe stream-boundary seed, deletion-minimizes it, and tries to replace coarse stream boundaries with narrower local precedence atoms.

### Cross-layer selection

```bash
python run_ft_repair_v3.py inspect-cross-layer
```

This compares the first-safe staged pipeline with a portfolio that evaluates multiple serially certified routing repairs according to their downstream safe scheduling behavior.  This is intentionally expensive.

## Smoke

```bash
python run_ft_repair_v3.py all \
  --config configs/ft_repair_v3_smoke.json \
  --out runs/ft_repair_v3_smoke
```

The smoke configuration validates the v3 path without running every historical baseline.  It is a software/development check, not a scientific benchmark.

## Standard benchmark

Use process-isolated execution:

```bash
python run_ft_repair_v3.py split \
  --config configs/ft_repair_v3_standard.json \
  --out runs/ft_repair_v3_standard
```

The main report is:

```text
runs/ft_repair_v3_standard/ft_repair_v3_summary.md
```

The standard benchmark includes:

- hidden 1-, 2-, and 3-check lowering mutations;
- v3 versus v2 routing repair;
- a physical-path-defect benchmark;
- operation-level schedule repair;
- pure operation-CEGIS ablation;
- v2 pairwise schedule baseline;
- staged mixed repair;
- cross-layer repair portfolio.

## Full benchmark

Only run this after the standard benchmark is scientifically interpretable:

```bash
python run_ft_repair_v3.py split \
  --config configs/ft_repair_v3_full.json \
  --out runs/ft_repair_v3_full
```

The full configuration spans all six synthetic calibration families, two contexts per family, more routing/path defects, two schedule methods, and a larger cross-layer portfolio.  It is intentionally expensive.

## Output files

V3 writes:

- `ft_repair_v3_summary.md`
- `ft_repair_v3_results.json`
- `ft_repair_v3_routing.csv`
- `ft_repair_v3_routing_v2.csv`
- `ft_repair_v3_path.csv`
- `ft_repair_v3_schedule.csv`
- `ft_repair_v3_schedule_pure.csv`
- `ft_repair_v3_schedule_v2.csv`
- `ft_repair_v3_mixed_staged.csv`
- `ft_repair_v3_mixed_cross_layer.csv`

## How to interpret the routing benchmark

The important separation is:

1. Did the physical witnesses implicate the hidden bad checks/routes?
2. Did the repair language contain a safe replacement?
3. How many exact verifier calls were required?
4. Did the final repair modify only the necessary compiler decisions?

V3 therefore reports witness localization separately from successful changed-check recovery.

## How to interpret the scheduling benchmark

There are three distinct results:

- **Pure operation CEGIS:** tests whether local witness clauses alone are expressive enough.
- **V3 portfolio:** tests whether a conservative safe seed can be relaxed to recover safe physical concurrency.
- **V2 pairwise baseline:** quantifies whether fine-grained operation constraints improve retained compiler optimization.

A pure-operation failure is not silently converted into a success.  It remains visible as an ablation result even when the robust portfolio succeeds.

## Current scientific boundary

V3 remains a controlled Steane-code experiment on the existing synthetic 12-node graph.  It does not establish a general compiler theorem, device-level FT, or cross-code/cross-topology generalization.  If v3 materially improves multi-defect and mixed repair, the next major step should be graph generalization before adding another code family.

# FT Compiler Repair v2

This implementation extends the counterexample-guided compiler-repair fork from a single-defect proof of concept into a broader repair benchmark.

The research objective is:

> Given a logically fault-tolerant QEC circuit whose physical compilation has introduced one or more first-order fault-tolerance violations, can an exact physical-fault verifier localize the responsible compiler decisions and drive a low-overhead repair while preserving useful optimization such as concurrency?

The exact verifier remains authoritative. No proxy, search heuristic, or learned model can declare a circuit safe.

## What v2 adds

### 1. Multi-defect lowering benchmarks

V1 injected one unsafe local lowering choice. V2 can inject 1, 2, or 3 simultaneous hidden compiler mutations on distinct stabilizer checks.

Each generated case must satisfy both:

- the logical six-check Steane extraction circuit still passes the logical single-fault verification; and
- the physically bridge-lowered circuit fails exact physical single-fault certification.

The repair algorithm is not told the number or location of the injected defects. The hidden injected check set is retained only for evaluation.

The generator is in `ftrepair_v2/mutations.py`.

### 2. Best-first multi-defect routing/lowering CEGIS

`ftrepair_v2/routing_cegis.py` starts from the unsafe physically compiled circuit and repeatedly:

1. runs the exact physical single-fault verifier;
2. extracts failing physical fault witnesses;
3. localizes those witnesses to implicated stabilizer checks;
4. expands only local compiler choices on implicated checks;
5. ranks candidate repairs by number of changed checks first and cheap bridge-proxy C2 second;
6. exactly verifies candidates;
7. accepts only a physically certified result.

The hard safety condition is:

```text
C1 = 0
single-fault decoder conflicts = 0
single-fault logical failures = 0
incoming-single-error failures = 0
```

This is a multi-defect extension of the v1 routing repair. It does not use the hidden defect labels during search.

### 3. Exact minimum-hitting-set scheduling repair

V1 scheduled repair greedily added one check-pair precedence constraint at a time based on the latest witnesses.

V2 adds an explicit counterexample-to-constraint model:

```text
physical failing fault witness
        ↓
set of check-pair precedence constraints capable of removing
that unsafe concurrency/interleaving
        ↓
repair clause
```

Across a batch of witnesses, v2 solves an exact minimum-cardinality, then minimum-weight hitting-set problem. There are only 15 possible check pairs for six checks, so exact subset search is practical and deterministic.

The core solver is in `ftrepair_v2/hittingset.py` and the pure global CEGIS implementation is in `ftrepair_v2/schedule_cegis.py`.

### 4. Robust scheduling portfolio

The pure hitting-set formulation is deliberately retained as an ablation, because it exposes an important limitation: pairwise witness clauses are not always expressive enough to repair unsafe stream interleavings by themselves.

For the main v2 scheduler, the implementation therefore uses a verifier-driven portfolio:

1. attempt pure global hitting-set CEGIS;
2. if that fails, use the mature v1 witness-greedy repair as an independent safe seed;
3. exact-delta-minimize the safe precedence set by removing constraints one at a time and recertifying after every deletion.

This is scientifically more honest than silently calling the portfolio a pure hitting-set algorithm. The benchmark reports both:

- `V2 schedule portfolio`
- `Pure hitting-set ablation`
- `Witness-greedy schedule v1`

The portfolio is intended to improve repair quality while retaining the pure formulation as an ablation.

### 5. Mixed compiler repair

`ftrepair_v2/mixed_repair.py` handles an input that has both:

- unsafe lowering choices; and
- an aggressive unsafe parallel schedule.

The current implementation is staged:

```text
multi-defect lowering repair
        ↓
exactly certified physical circuit
        ↓
parallel scheduling repair
        ↓
exactly certified concurrent circuit
```

This is not yet a mathematically complete joint optimizer, but it exercises multiple compiler-transformation classes in one end-to-end repair workflow.

### 6. Baselines and evaluation

The v2 benchmark compares:

- v2 multi-defect routing CEGIS;
- v1 routing repair;
- v2 scheduling portfolio;
- pure hitting-set scheduling ablation;
- v1 witness-greedy scheduling repair;
- staged mixed v2 repair.

Metrics include:

- repair success rate;
- exact verifier calls;
- number of changed checks;
- hidden injected-check recall and precision;
- exact hidden defect-set recovery;
- number of precedence constraints;
- retention of true simultaneous native-CX execution;
- speedup relative to full serialization.

## Install

Keep the existing `qec_flag_project` and `.venv`.

```bash
cd ~/Downloads
unzip -q -o ft_compiler_repair_v2_patch.zip
cp -R ft_compiler_repair_v2_patch/. ~/qec_flag_project/

cd ~/qec_flag_project
source .venv/bin/activate
```

No new Python packages are required.

## Doctor

```bash
python run_ft_repair_v2.py doctor
```

The branch should report:

```text
ft-compiler-repair-v2
```

## Tests

V1 regression tests:

```bash
python -m pytest -q tests/test_ft_repair.py
```

Expected from the development environment:

```text
5 passed
```

V2 tests:

```bash
python -m pytest -q tests/test_ft_repair_v2.py
```

The five v2 tests cover:

1. exact hitting-set optimality;
2. generation of a hidden two-defect case;
3. successful two-defect physical repair;
4. scheduling repair with retained true native-CX parallelism;
5. mixed lowering+scheduling repair.

Because several of these tests invoke the exact physical verifier repeatedly, the whole v2 file can exceed short execution windows. They were also run individually during development.

## Inspect a hidden two-defect repair

```bash
python run_ft_repair_v2.py inspect-multidefect
```

The development reference produced:

```text
hidden injected checks: [0, 1]
repair success: true
exact verifier calls: 10
changed checks: [0, 1]
final C1: 0
```

The hidden set is printed by the inspection command only for evaluation. The repair routine itself receives only the mutated circuit.

## Inspect scheduling repair

```bash
python run_ft_repair_v2.py inspect-schedule
```

The development reference produced a safe schedule with:

```text
C1 = 0
4 precedence constraints
max simultaneous native CX = 2
speedup vs serialized ≈ 16.23%
```

For the same reference case, v1 required 8 precedence constraints and retained about 11.67% speedup.

The pure hitting-set ablation does not succeed on this reference case; the portfolio result therefore comes from the v1 safe seed followed by exact constraint minimization. This is reported explicitly in the benchmark.

## Inspect mixed repair

```bash
python run_ft_repair_v2.py inspect-mixed
```

The development reference first repairs one hidden unsafe lowering mutation and then repairs the aggressive schedule. It finishes with:

```text
routing safe: true
schedule safe: true
C1 = 0
max simultaneous native CX = 2
speedup vs serialized ≈ 16.23%
```

## Smoke benchmark

```bash
python run_ft_repair_v2.py all \
  --config configs/ft_repair_v2_smoke.json \
  --out runs/ft_repair_v2_smoke
```

The included smoke configuration intentionally uses one small nominal case so it completes quickly while exercising routing repair, the scheduling portfolio, the pure hitting-set ablation, and v1 baselines.

## Standard benchmark

A medium benchmark is included for routine development:

```bash
python run_ft_repair_v2.py split \
  --config configs/ft_repair_v2_standard.json \
  --out runs/ft_repair_v2_standard
```

Use `split` so each calibration family runs in its own Python process.

## Full benchmark

```bash
python run_ft_repair_v2.py split \
  --config configs/ft_repair_v2_full.json \
  --out runs/ft_repair_v2_full
```

The full configuration is intentionally much heavier. It includes:

- six calibration families;
- two contexts per family;
- 1-, 2-, and 3-defect lowering cases;
- three schedule methods;
- multiple certified base circuits;
- mixed repair cases;
- v1 and pure-hitting-set ablations.

Expect it to be substantially slower than the original v1 benchmark.

## Main outputs

```text
ft_repair_v2_summary.md
ft_repair_v2_results.json
ft_repair_v2_routing.csv
ft_repair_v2_routing_v1.csv
ft_repair_v2_scheduling.csv
ft_repair_v2_scheduling_pure.csv
ft_repair_v2_scheduling_v1.csv
ft_repair_v2_mixed.csv
```

## What would count as a strong result?

The next publication-shaped milestone would require more than high repair success on one code/graph.

Within the current benchmark, a strong v2 result would show:

- multi-defect repair success remains high as defect count increases from 1 to 3;
- the repair engine recovers the hidden defect set with high recall and precision;
- verifier-call growth remains moderate;
- the scheduling portfolio improves repair success and/or preserves more speedup than v1;
- mixed lowering+scheduling repair remains viable;
- successful scheduling repairs preserve genuine native-CX concurrency.

Even a strong result here is still a Steane/single-topology result. Cross-code and cross-topology generalization remains the next major scientific requirement.

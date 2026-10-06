# FT Compiler Repair v2 — Scientific Scope

## Primary question

Can exact physical-fault counterexamples support automatic repair of multiple interacting compiler-introduced fault-tolerance violations, while limiting the number of compiler edits and preserving useful physical optimization such as parallel execution?

## What is genuinely new relative to v1

V1 demonstrated repair of one controlled lowering defect and greedy schedule repair.

V2 broadens the problem in four ways:

1. **Multiple hidden lowering defects.** A benchmark instance may contain one, two, or three simultaneous local compiler mutations.
2. **Global witness reasoning.** Scheduling witnesses are translated into sets of possible precedence repairs and solved using an exact small-universe hitting-set formulation.
3. **Repair minimization.** Safe scheduling constraints can be exact-delta-minimized while repeatedly recertifying physical fault tolerance.
4. **Mixed transformation repair.** Lowering repair and scheduling repair can be exercised in one end-to-end compiled circuit.

## Benchmark semantics

The hidden mutation set is used only to calculate evaluation metrics such as localization recall and exact defect-set recovery.

The repair algorithm receives:

- the physically compiled circuit description;
- hardware calibration context;
- exact verifier counterexamples.

It does not receive the injected defect labels.

## Repair language

### Lowering repair

Allowed local alternatives come from local choices that occur in the previously physically certified Phase-7 catalog. Search changes only checks implicated by physical counterexamples and is ordered lexicographically by:

1. number of changed checks;
2. bridge proxy C2.

### Scheduling repair

The scheduling repair language remains pairwise check-stream precedence constraints. There are at most 15 such atoms for six checks, allowing an exact minimum-hitting-set calculation.

This repair language is intentionally restricted. A failure to repair does not prove that no safe parallel schedule exists.

## Exact safety condition

A result is safe only if all modeled first-order checks pass:

```text
C1 = 0
single-fault conflicts = 0
single-fault logical failures = 0
incoming-single-error failures = 0
```

No proxy or timing objective can override this rule.

## Important ablation

The pure hitting-set scheduling algorithm is retained separately from the main v2 scheduling portfolio.

Development testing showed that pure pairwise hitting-set reasoning can fail even when the older witness-greedy algorithm finds a safe seed. The main v2 portfolio therefore combines:

- pure global CEGIS;
- v1 witness-greedy seeding when necessary;
- exact deletion-based minimization of the resulting safe precedence set.

The benchmark reports all three methods separately so the contribution of each step is visible.

## Included

- Steane six-check flagged syndrome extraction.
- Existing physically certified bridge routing.
- Exact native Pauli single-fault propagation.
- Synthetic hardware calibration families.
- 1–3 controlled lowering defects.
- Routing/template/hub local compiler-choice repair.
- Unsafe parallel scheduling repair.
- Mixed lowering+scheduling repair.
- Exact verifier-call accounting.
- Hidden defect-set localization metrics.
- Concurrency and speedup retention metrics.

## Not yet included

- A second QEC code family.
- A second physical coupling graph.
- General compiler IR.
- Arbitrary routing primitives beyond the existing action/certified catalog.
- Joint global optimization of lowering and scheduling in one solver.
- Formal completeness of repair.
- Crosstalk, leakage, pulse-level control, or real device calibration.
- ML/RL-guided repair.

## Why cross-code/topology generalization is still required

A strong result in this benchmark would establish that the repair workflow is nontrivial within the existing Steane model, but it would not establish a general-purpose FT compiler-repair method.

The next serious scientific expansion should add at least:

1. one additional distance-3 code/gadget family; and
2. multiple physical hardware graphs or logical-to-physical layouts.

Only after that should broad novelty claims be considered.

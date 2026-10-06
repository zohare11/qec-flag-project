# FT Compiler Repair Fork v1 — Scientific Scope

## Research question

Can exact physical-fault counterexamples be used to automatically repair compiler transformations that preserve ideal circuit semantics but violate a quantum error-correction gadget's first-order fault-tolerance guarantee?

## Included

- Steane-code six-check flagged syndrome extraction inherited from the existing project.
- Existing synthetic 12-node nearest-neighbor hardware graph.
- Exact Pauli propagation for modeled native CNOT, preparation, measurement, and inherited idle fault locations.
- Existing schedule-specific decoders and single-fault certification machinery.
- Unsafe SWAP routing as a compiler-induced fault-tolerance violation.
- Unsafe resource-valid cross-check parallelization as a second compiler-induced violation.
- Counterexample localization.
- Deterministic routing/lowering repair.
- Deterministic pairwise-precedence scheduling repair.
- Hard recertification after every accepted repair.

## Not included

- General-purpose quantum compiler IR.
- Arbitrary QEC codes.
- Multiple physical hardware topologies.
- Formal completeness of the repair rule set.
- ZX-calculus fault-equivalence proofs.
- Crosstalk, leakage, pulse-level constraints, or measured device calibration.
- ML/RL-guided repair.

## Why the benchmark uses controlled injected lowering violations

A repair benchmark needs a known pre-compilation safety condition and a known post-compilation violation. Routing cases therefore begin with a Phase-7 certified round and replace one local lowering choice with another Phase-4-certified choice. The logical verifier must still pass, while the resulting physical bridge compilation must fail.

The repair engine is not told which check was injected. That check is retained only as evaluation metadata for measuring localization accuracy.

This is a controlled benchmark, not evidence that a production compiler would generate the exact same distribution of mistakes.

## Safety semantics

The authoritative condition is the modeled first-order property:

C1 = 0,

plus no single-fault decoder conflicts, no single-fault logical failures, and no failures on the incoming-single-error regression set.

A candidate with lower depth or lower proxy C2 is rejected if it fails this condition.

## Intended next expansion

A publication-oriented continuation should broaden along at least two axes before making a general novelty claim:

1. multiple hardware topologies / routing graphs;
2. more than one QEC gadget or code family.

If the deterministic repair search then becomes expensive, a learned proposal model can rank repair candidates while exact certification remains the acceptance oracle.

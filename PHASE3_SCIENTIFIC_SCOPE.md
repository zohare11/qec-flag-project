# Phase 3 scientific scope

Phase 3 changes the task from selecting one finished schedule to constructing an interaction schedule sequentially.

## Phase 3A

The policy emits the six controls of the already studied one-flag Steane Z-check, one operation at a time. There are 360 grammar-complete orders; exact single-fault certification accepts 96. The exhaustive 96-circuit oracle is retained to validate the sequential-learning machinery.

## Phase 3B

A second flag ancilla becomes available. The policy decides whether to use flag A only, flag B only, or both, and places all interactions sequentially. The finite grammar contains:

- 360 A-only candidate schedules,
- 360 B-only candidate schedules,
- 10,080 two-flag candidate schedules.

The verifier accepts 96 A-only, 96 B-only, and 4,704 two-flag schedules under the documented single-component certificate. The expanded certified catalog therefore has 4,896 schedules.

This is a meaningful expansion beyond the Phase-1/2 library, but it is still **structured schedule synthesis**, not unrestricted arbitrary-gate circuit discovery.

## Correctness model

Each schedule measures the same four-data-qubit Z parity ideally. Flag ancillas interact with the syndrome twice each, so their ideal action cancels while faults can leave a flag signal. Certification checks:

1. the schedule's ideal interaction grammar,
2. every enumerated single component fault,
3. every single incoming data Pauli,
4. consistency of a decoder given flag bits plus a hypothetical perfect final six-bit Steane syndrome.

The perfect final syndrome/recovery remains an idealization. These experiments do not simulate repeated noisy syndrome extraction, leakage, crosstalk, idling, or a complete logical memory experiment.

## Objective

For a certified schedule and 96-dimensional synthetic calibration context `w`, the exact second-order coefficient is

`C2(w) = sum_{i<=j} c_ij w_i w_j`,

where `c_ij` counts malignant different-location fault pairs in the stated model. Lower is better. All finite-p diagnostics retain the same ideal-final-recovery scope.

## Learning information

The actor-critic is not trained on exhaustive oracle labels. It receives only the terminal reward of the circuit it synthesized, normalized against one fixed reference schedule. Exhaustive costs are used for post-training evaluation and for reporting regret. Validation checkpointing uses selected-circuit cost relative to the fixed reference, not exhaustive oracle regret.

## Baselines

Phase 3 reports:

- fixed reference,
- best fixed schedule selected on training contexts,
- equal-budget random catalog search,
- policy-greedy synthesis (no online C2 search),
- policy-beam synthesis followed by a finite exact-evaluation budget,
- exact exhaustive oracle within the finite certified library,
- and in Phase 3B, the best one-flag oracle as an architecture-restriction baseline.

The exhaustive oracle is not a claim of global optimality over quantum circuits.

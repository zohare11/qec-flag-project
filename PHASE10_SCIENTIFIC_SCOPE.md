# Phase 10 scientific scope

## Claim tested

Phase 10 tests whether deterministic parallel scheduling of already certified bridge-routed Steane syndrome-extraction circuits can reduce wall-clock duration and data idling while preserving first-order fault tolerance.

## What is new relative to Phase 9

Phase 9 used a serialized operation clock. Phase 10 assigns explicit start/stop times to prep, native CNOT, and measurement operations. Different stabilizer checks may progress concurrently when their physical-qubit resources are disjoint.

The actual interleaved circuit is then re-simulated. This matters because operations that are independently safe in a serialized circuit can acquire new fault-propagation paths after cross-check interleaving.

## Physical admissibility

A proposed schedule is retained only if:

1. the ideal no-fault circuit is preserved;
2. physical resource constraints are satisfied;
3. every same-check dependency is preserved;
4. C1 is exactly zero in the modeled Pauli process;
5. there are no single-fault decoder conflicts;
6. there are no single-fault logical failures;
7. all incoming single-data errors remain correctable.

This is a lexicographic constraint, not a reward penalty.

## Timing and idle model

Each operation has a duration. The scheduler constructs the union of all event start/stop boundaries. During each resulting time slice, every persistent data qubit not participating in an active native CNOT receives an explicit idle-fault location.

Thus overlapping unrelated operations reduce memory-idle exposure only when they genuinely reduce the wall-clock timeline.

## Search scope

Phase 10 does not alter:

- the 74 Phase-8/9 continuously-idle-certified physical circuit catalog,
- bridge routing primitives,
- local flag templates,
- hardware placement,
- the Steane stabilizers,
- the Phase-9 repeated-round detector decoder.

The beam/local-search baselines search only static priority permutations among the six stabilizer-check programs. They do not search arbitrary gate permutations.

## Deliberate limitations

- synthetic 12-node topology and calibration families;
- no real backend calibration;
- no crosstalk or leakage;
- no pulse-level simultaneous-gate constraints beyond shared physical-qubit exclusion;
- no tunable pulse durations;
- no parallel measurement-control electronics model;
- same-check native operation order remains fixed;
- detector decoder remains an order-2 small-code hypergraph decoder with an ideal final memory boundary.

## Decision rule for a later learning phase

Learning should only be reintroduced if the physically admissible parallel-schedule space is nontrivial. If aggressive resource-valid parallel schedules systematically fail single-fault certification, the next step is to redesign/certify concurrency-aware extraction primitives rather than train a policy over unsafe schedules.

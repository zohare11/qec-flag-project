# Phase 7 scientific scope

## Research question

Can physical routing be redesigned so that complete routed Steane syndrome-extraction rounds retain the single-fault guarantee that was lost under the Phase-6 generic SWAP router?

## Phase 7A: forensic diagnosis

The Phase-6 native simulator is used to enumerate every first-order logical failure. For each failing native fault, Phase 7 records the check, route, physical path, native CNOT, Pauli fault, extraction observation, decoder correction, residual Pauli, and logical class.

The corresponding **unrouted logical circuit** is retained as a control. If that control fails, the routing diagnosis would be invalid. In the development reference it passes all single-fault and incoming-error checks.

## Phase 7B: routing primitive

Remote CNOTs are implemented with a nearest-neighbour bridge construction that leaves intermediate qubits unchanged ideally:

- 1 hop: 1 native CNOT;
- 2 hops: 4 native CNOTs;
- 3 hops: 8 native CNOTs.

On the fixed 3x4 graph, deterministic paths prefer no data qubits in the interior. Route selection is topology-only rather than calibration-dependent, so a certification remains valid when synthetic error rates or durations change.

This construction is **not declared fault tolerant a priori**. Some logically valid schedules still fail after bridge routing. Complete rounds therefore undergo exhaustive certification.

## Certification rule

A Phase-7 physical round is admitted only if:

1. the ideal routed computation matches the logical syndrome-extraction round;
2. every modeled single native fault is correctable;
3. the schedule-specific decoder has no single-fault signature conflicts;
4. every incoming single data Pauli remains correctable;
5. the resulting first-order coefficient is exactly `C1 = 0`.

This is a hard admissibility condition, not a soft reward penalty.

## Certified catalog

The project checks all 96 homogeneous combinations of the 48 Phase-4 logical templates and two syndrome hubs. It then constructs a small structured set of one-check variants around a safe base round and retains only variants that pass the same exhaustive certification.

This catalog is deliberately small. It is evidence that fault-tolerance-preserving routed implementations exist in the controlled model; it is not an exhaustive set of all possible physical circuits.

## Noise model

Native CNOT faults are propagated gate by gate with the same synthetic edge-scaled Pauli model used in Phase 6. Preparation and readout faults remain explicit. Persistent-data idle faults are explicit at route boundaries but not continuously scheduled after every native sub-gate.

## Decoder and boundary

The decoder remains schedule-specific and uses the noisy extraction record plus an ideal final memory-boundary syndrome. The experiment covers one serialized six-check Steane extraction round rather than repeated QEC cycles.

## Claims Phase 7 can support

If the certified catalog is nonempty and its entries retain `C1 = 0` across calibration families, Phase 7 supports the statement that the Phase-6 first-order failure was a property of the physical routing construction rather than an unavoidable consequence of placing the logical flagged circuit on this graph.

If certified rounds also improve finite-p logical failure relative to the naive SWAP implementation, that provides additional evidence that preserving the single-fault condition matters operationally in the controlled model.

## Claims Phase 7 cannot support

Phase 7 does not establish:

- fault tolerance on a real processor;
- a threshold result;
- repeated fault-tolerant memory;
- optimal physical routing;
- hardware advantage;
- superiority of reinforcement learning;
- generality beyond the fixed Steane-code, topology, decoder, and synthetic noise model used here.

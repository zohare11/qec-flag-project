# Phase 5 scientific scope

Phase 5 asks whether calibration-conditioned learned proposal search becomes more useful when a full Steane syndrome-extraction round is constrained by a fixed nearest-neighbour hardware graph and schedule-dependent routing/timing overhead.

## Added relative to Phase 4

- A fixed synthetic 12-node, 3x4 nearest-neighbour coupling graph.
- Seven fixed data-qubit locations, two alternative syndrome-hub locations, and two flag locations.
- Each Phase-4 local flag template can be executed from either syndrome hub, yielding 96 actions per stabilizer check and `96^6 = 782,757,789,696` complete schedules.
- Calibration-specific native-edge error multipliers and CNOT durations.
- Remote logical CNOTs use a SWAP-forward / CNOT / SWAP-back route whose logical mapping is restored.
- Persistent data-qubit idle exposure depends on complete-round duration.
- Hardware-aware local-greedy, routing-only, coordinate-search, random-search, policy-greedy, and policy-beam baselines.

## Important approximation

Phase 5 does **not** explicitly insert every routed native CNOT into the Pauli-frame fault enumerator. The routed native-CX error multipliers and idle exposure are collapsed into schedule-dependent effective logical fault weights, after which the exact Phase-4 malignant-pair calculation is applied. Native CX count and duration are reported separately.

Consequently, Phase 5 is a controlled hardware-aware search experiment, not a backend-accurate logical-error simulator. A positive result motivates an explicit native-circuit simulator in the next stage.

## Still outside scope

- measured hardware calibrations;
- named IBM/Google topology claims;
- parallel stabilizer scheduling;
- leakage/crosstalk;
- explicit routing-gate fault propagation;
- repeated QEC rounds and a scalable decoder;
- hardware or quantum advantage claims.

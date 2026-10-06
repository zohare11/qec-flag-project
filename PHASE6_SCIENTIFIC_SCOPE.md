# Phase 6 scientific scope

Phase 6 is a **validation phase**, not a new learning phase. It asks whether the reduced hardware-aware cost model used in Phase 5 ranks selected schedules similarly to an explicit routed-native-CNOT Pauli-fault model.

The logical schedule is expanded using the same fixed 12-node graph and SWAP-forward / CNOT / SWAP-back routes as Phase 5. Every inserted native CNOT is now a separate physical fault location with 15 non-identity two-qubit Pauli outcomes. Preparation and readout use the same representative Pauli model as earlier phases. Persistent data-qubit idling is represented by explicit X/Y/Z locations after each routed logical interaction for nonparticipating data qubits.

The explicit simulator retains the Phase-4/5 ideal initial/final memory boundaries and schedule-specific flag-aware decoder. It does not model repeated QEC rounds, leakage, crosstalk, coherent errors, or measured device calibrations. Idle noise is still discretized at route boundaries rather than continuously scheduled at every sub-gate.

A key new quantity is `C1`, the coefficient of first-order logical failure. If inserted routing gates create unflagged malignant single faults, `C1 > 0`; in that case, the implementation is not first-order fault tolerant under this model and Phase-5 `C2` alone is not an adequate leading-order metric. Phase 6 therefore reports both `C1` and `C2`, plus a small-p score `p*C1 + p^2*C2` and direct finite-p Monte Carlo diagnostics.

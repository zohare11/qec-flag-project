# Phase 8 scientific scope

Phase 8 asks whether the physically single-fault-certified bridge circuits from Phase 7 remain valid when idle exposure is resolved at every serialized preparation, native CNOT, and measurement interval, and how those circuits behave over repeated noisy extraction rounds without ideal recovery between rounds.

## Improvements over Phase 7

- Native bridge CNOT faults remain explicit.
- Persistent data idling is no longer one location per logical route. Each serialized prep/CX/meas interval creates explicit idle locations on inactive data qubits.
- The same routed extraction round is repeated three times in the default experiment with no correction inserted between rounds.
- The primary repeated-round decoder is a small-code minimum-weight fault-history lookup built from all modeled single-fault signatures across the repeated rounds and an ideal final memory-boundary syndrome. A temporal-majority Steane minimum-weight decoder is retained as a weaker baseline.

## Important nonclaims

This is not continuous-time Lindblad simulation. Prep and measurement durations are fixed synthetic constants. The decoder is not PyMatching/MWPM and is not intended as a scalable state-of-the-art repeated-QEC decoder. Checks remain serialized. The graph and calibrations are synthetic. The repeated-round result is therefore a stronger controlled validation, not a hardware threshold result.

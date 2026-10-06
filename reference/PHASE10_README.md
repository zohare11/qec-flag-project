# Phase 10 reference results

These are development/reference outputs generated while validating the Phase-10 patch. They are included so the user can compare installation behavior, not as a substitute for the user's own run.

The full reference result was executed family-by-family in fresh Python processes using `configs/phase10_full.json`, then merged. This is the same execution strategy automated by `python run_phase10.py split ...`.

Headline reference observation: across the five configured synthetic noise families, `serialized` and `ancilla_overlap` remained single-fault certified, while all seven tested schedulers that permitted overlapping native CNOTs had nonzero C1 and failed physical certification in the tested context. `ancilla_overlap` shortened the round by roughly 0.9–1.3% by overlapping only disjoint preparation/measurement work while retaining globally serialized native CNOTs.

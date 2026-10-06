# FT Repair v2 reference runs

`ft_repair_v2_smoke_summary.md` is a development smoke result, not the full scientific benchmark.

Additional development checks performed before packaging:

- hidden two-defect routing case: repaired successfully with 10 exact verifier calls, changing exactly checks 0 and 1, final C1=0;
- scheduling reference case: v2 portfolio repaired with 4 precedence constraints, retained max simultaneous native CX=2, and retained ~16.23% speedup versus serialization;
- same scheduling case with v1: 8 precedence constraints and ~11.67% speedup;
- pure hitting-set ablation on that case: did not reach a certified schedule;
- staged mixed one-defect lowering+scheduling case: repaired both stages successfully, 24 total exact verifier calls, max simultaneous native CX=2, ~16.23% speedup.

These are debugging/reference cases only. Use the standard/full configs for project results.

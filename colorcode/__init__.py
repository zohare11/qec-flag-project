"""Syndrome extraction schedules for the triangular 6.6.6 color code with one auxiliary per plaquette.

Modules:
    lattice     patch geometry, Kishony & Fowler (arXiv:2603.28852) schedules, schedule (de)serialisation
    circuits    Stim memory experiments (noisy-CNOT, SI1000, uniform depolarizing)
    hooks       hook errors and the exact circuit distance of a schedule (see `hooks` docstring)
    search      CEGAR search for schedules that reach a target circuit distance
    structured  the same search restricted to schedules repeated along each edge
    verify      independent circuit-level check on Stim's detector error model (small d)
    decoders    Tesseract and BP+OSD wrappers for logical error rates
"""

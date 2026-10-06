# Phase 8 guide

Phase 8 validates the Phase-7 certified physical catalog under gate-resolved data idling and then runs repeated syndrome-extraction memory experiments.

## Commands

```bash
cd ~/qec_flag_project
source .venv/bin/activate
python run_phase8.py doctor
python -m pytest -q
python run_phase8.py build-cache
python run_phase8.py inspect-timing
python run_phase8.py all --config configs/phase8_smoke.json --out runs/phase8_smoke
python run_phase8.py all --config configs/phase8_full.json --out runs/phase8_full
```

`build-cache` rechecks every Phase-7 catalog circuit under per-interval idle faults. `inspect-timing` prints one example timeline/certificate. The full report is `runs/phase8_full/phase8_summary.md`.

## Decoder

For each of the three repeated extraction rounds, the simulator records the six measured stabilizer bits. The primary decoder uses the full syndrome and flag history plus an ideal final memory-boundary syndrome and chooses a minimum-weight correction compatible with modeled single-fault histories. Because the Steane pilot is small, this is implemented as an exact lookup rather than MWPM/PyMatching. A temporal-majority Steane decoder is also reported as a weaker baseline.

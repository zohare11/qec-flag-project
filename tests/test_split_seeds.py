"""Split mode must give each calibration family the seed it gets in a combined run.

Regression test for the bug where `split` wrote one sub-config per family and
every subprocess therefore used family slot 0 (identical base calibrations).
"""
import json
from pathlib import Path

import pytest

import ftrepair_v3.experiment as v3


class _Stop(Exception):
    pass


def _family_seed(monkeypatch, cfg):
    seen = []
    real = v3.sample_hardware_contexts

    def spy(n, seed, family):
        if seed == cfg['seed'] + 777:  # nominal context used to build the cases
            return real(n, seed, family)
        seen.append((family, seed))
        raise _Stop

    monkeypatch.setattr(v3, 'sample_hardware_contexts', spy)
    monkeypatch.setattr(v3, 'generate_check_choice_cases', lambda *a, **k: [])
    monkeypatch.setattr(v3, 'generate_path_defect_cases', lambda *a, **k: [])
    monkeypatch.setattr(v3, 'ensure_catalog', lambda *a, **k: [])
    with pytest.raises(_Stop):
        v3.run_all(Path('.'), cfg, Path('/tmp/_unused_split_seed_test'))
    return seen[0]


def test_split_subconfig_reproduces_combined_seeds(monkeypatch):
    base = {'families': ['hw_id', 'ood_edge_hotspot', 'ood_logical_shift', 'ood_mixed'], 'seed': 33101}
    for slot, fam in enumerate(base['families']):
        # what run_ft_repair_v3.py split_run now writes for this family
        sub = dict(base); sub['families'] = [fam]; sub['family_seed_slots'] = {fam: slot}
        assert _family_seed(monkeypatch, sub) == (fam, 33101 + 1000 * slot)


def test_split_runners_record_seed_slots():
    root = Path(__file__).resolve().parents[1]
    for runner in ('run_ft_repair.py', 'run_ft_repair_v2.py', 'run_ft_repair_v3.py'):
        assert "family_seed_slots" in (root / runner).read_text(), runner

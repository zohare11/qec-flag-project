"""Color code schedules (skipped without stim / pycryptosat / python-sat / ortools)."""
from pathlib import Path

import pytest

pytest.importorskip('stim')
pytest.importorskip('pycryptosat')
pytest.importorskip('pysat')
pytest.importorskip('ortools')

from colorcode import hooks, search, verify  # noqa: E402
from colorcode.circuits import memory_circuit  # noqa: E402
from colorcode.lattice import check_schedule, lattice, schedule_from_colors, schedule_from_json  # noqa: E402

SCHED = Path(__file__).resolve().parent.parent / 'colorcode' / 'schedules'


@pytest.mark.parametrize('d', [3, 5, 7, 9])
def test_patch_sizes_and_kf_schedule_is_valid(d):
    data, plaq = lattice(d)
    assert len(data) == (3 * d * d + 1) // 4
    assert sum(len(p['sup']) == 4 for p in plaq) == 3 * (d - 1) // 2
    assert check_schedule(plaq, schedule_from_colors(plaq))


@pytest.mark.parametrize('d,expected', [(5, 4), (7, 6), (9, 7)])
def test_kf_distance_matches_their_formula(d, expected):
    data, plaq = lattice(d)
    assert expected == d - (d + 3) // 6
    assert hooks.static_distance(data, plaq, schedule_from_colors(plaq), lo=expected - 1)[0] == expected


def test_circuit_level_distance_equals_hook_distance_at_d5():
    c, *_ = memory_circuit(5, noise='cnot')
    assert not verify.logical_within(c, 3)
    assert verify.logical_within(c, 4)


def test_full_distance_is_impossible_at_d5():
    assert search.search(5, target=5, verbose=False)['status'] == 'INFEASIBLE'


def test_d9_schedule_reaches_distance_8():
    d, data, plaq, sched = schedule_from_json((SCHED / 'd9_distance8.json').read_text())
    assert d == 9
    assert hooks.has_logical(data, plaq, sched, 7) is None
    assert hooks.has_logical(data, plaq, sched, 8) is not None

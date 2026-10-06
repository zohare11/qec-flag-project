"""Stim must agree with the project's single-fault verifier (skipped if stim is missing)."""
import json
from pathlib import Path

import pytest

pytest.importorskip('stim')

from tools.stim_xcheck import compare, unrouted_plan  # noqa: E402
from qecflag.phase5_noise import sample_hardware_contexts  # noqa: E402
from qecflag.phase6_native import build_native_plan  # noqa: E402
from qecflag.phase7_routing import build_bridge_plan  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def ctx():
    return sample_hardware_contexts(1, 7101, 'hw_id').context(0)


@pytest.fixture(scope='module')
def entries():
    return json.loads((ROOT / 'cache' / 'phase7_certified_bridge_catalog.json').read_text())['entries'][:3]


def test_stim_agrees_on_unrouted_swap_and_bridge(ctx, entries):
    for e in entries:
        labels, hubs = e['labels'], e['hubs']
        unrouted = compare(unrouted_plan(labels, hubs), ctx)
        swap = compare(build_native_plan(labels, hubs, ctx), ctx)
        bridge = compare(build_bridge_plan(labels, hubs, ctx), ctx)
        for r in (unrouted, swap, bridge):
            assert r['agree'], r
        assert unrouted['stim_pass'] and bridge['stim_pass']
        assert not swap['stim_pass']  # naive SWAP routing breaks single-fault FT

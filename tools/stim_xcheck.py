"""Independent Stim cross-check of the project's single-fault ("C1 = 0") verifier.

The project's certification asks: after one noisy, routed Steane round with an
ideal final syndrome boundary, can every single fault (or single incoming data
error) be told apart from every other single event with a different logical
effect?  That is the same as asking whether the circuit-level distance is >= 3,
which Stim can answer directly from its detector error model (DEM).

This script rebuilds a NativeRoundPlan as a Stim circuit with the SAME fault
locations as qecflag/phase6_native.py:
  - incoming single data errors          -> DEPOLARIZE1 on data at the start
  - ancilla preparation faults           -> X_ERROR after R, Z_ERROR after RX
  - 15-outcome Pauli after every native CX -> DEPOLARIZE2
  - one data-idle location per routed interaction (non-active data) -> DEPOLARIZE1
  - readout faults                       -> X_ERROR before M, Z_ERROR before MX
Detectors are every syndrome/flag bit plus the ideal final boundary (via MPP);
observables are X_L.X_R and Z_L.Z_R against a noiseless reference qubit.

A "conflict" is a set of detectors produced by two single events with different
logical effect.  The circuit is single-fault FT exactly when there are none.
The script compares Stim's conflict count with the project's decoder
(single_fault_conflicts) circuit by circuit.

Usage (from the project root, with stim installed: python -m pip install stim):
    python tools/stim_xcheck.py            # Phase-7 catalog: unrouted / SWAP / bridge
    python tools/stim_xcheck.py --paths    # also single-path mutations (v3 model)
Exit code is 1 if Stim and the project's verifier disagree on any circuit.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import stim
except ImportError:  # pragma: no cover - friendly message for the CLI
    stim = None

from qecflag.physics import SUPPORTS
from qecflag.phase3_physics import FLAG_A, FLAG_B, schedule_from_label
from qecflag.phase4_physics import CHECKS
from qecflag.phase5_hardware import DATA_NODES, HUB_NODES, FLAG_NODES
from qecflag.phase6_native import (
    NativeCX, NativeRoute, NativeCheckPlan, NativeRoundPlan,
    native_fault_records, build_native_decoder,
)

REF = 12  # noiseless reference qubit (physical nodes are 0..11)
GENS = [('X', s) for s in SUPPORTS] + [('Z', s) for s in SUPPORTS]  # same order as CHECKS / code_tables


def _require_stim():
    if stim is None:
        raise SystemExit('stim is not installed. Run:  python -m pip install stim')


def _stab_targets(kind: str, mask: int):
    qs = [q for q in range(7) if (mask >> q) & 1]
    out = []
    for i, q in enumerate(qs):
        node = DATA_NODES[q]
        out.append(stim.target_x(node) if kind == 'X' else stim.target_z(node))
        if i != len(qs) - 1:
            out.append(stim.target_combiner())
    return out


def _logical_targets(kind: str):
    out = []
    for q in range(7):
        node = DATA_NODES[q]
        out += [stim.target_x(node) if kind == 'X' else stim.target_z(node), stim.target_combiner()]
    out.append(stim.target_x(REF) if kind == 'X' else stim.target_z(REF))
    return out


def plan_to_stim(plan: NativeRoundPlan, p: float = 1e-3) -> "stim.Circuit":
    """Stim circuit with the same fault locations as phase6_native.simulate_native."""
    _require_stim()
    c = stim.Circuit()
    n_meas = 0

    def mpp(targets):
        nonlocal n_meas
        c.append('MPP', targets)
        n_meas += 1
        return n_meas - 1

    def rec(i):
        return stim.target_rec(i - n_meas)

    init_stab = [mpp(_stab_targets(k, s)) for k, s in GENS]
    init_lx, init_lz = mpp(_logical_targets('X')), mpp(_logical_targets('Z'))
    c.append('TICK')
    c.append('DEPOLARIZE1', list(DATA_NODES), p)  # incoming single data errors

    for cp in plan.checks:
        flags = ([FLAG_NODES[FLAG_A]] if cp.used_a else []) + ([FLAG_NODES[FLAG_B]] if cp.used_b else [])
        syn_basis = 'Z' if cp.check_type == 'Z' else 'X'   # Z check: syndrome |0>, flags |+>
        flag_basis = 'X' if cp.check_type == 'Z' else 'Z'  # X check: syndrome |+>, flags |0>
        ancillas = [(cp.hub_node, syn_basis)] + [(f, flag_basis) for f in flags]
        for q, b in ancillas:
            if b == 'Z':
                c.append('R', [q]); c.append('X_ERROR', [q], p)
            else:
                c.append('RX', [q]); c.append('Z_ERROR', [q], p)
        for route in cp.routes:
            for cx in route.cxs:
                c.append('CX', [cx.control, cx.target])
                c.append('DEPOLARIZE2', [cx.control, cx.target], p)
            idle = [node for q, node in enumerate(DATA_NODES) if q != route.active_data]
            c.append('DEPOLARIZE1', idle, p)
        meas = {}
        for q, b in ancillas:
            if b == 'Z':
                c.append('X_ERROR', [q], p); c.append('M', [q])
            else:
                c.append('Z_ERROR', [q], p); c.append('MX', [q])
            meas[q] = n_meas; n_meas += 1
        c.append('DETECTOR', [rec(meas[cp.hub_node]), rec(init_stab[cp.check])])
        for f in flags:
            c.append('DETECTOR', [rec(meas[f])])
        c.append('TICK')

    final = [mpp(_stab_targets(k, s)) for k, s in GENS]
    for i in range(6):
        c.append('DETECTOR', [rec(final[i]), rec(init_stab[i])])
    flx, flz = mpp(_logical_targets('X')), mpp(_logical_targets('Z'))
    c.append('OBSERVABLE_INCLUDE', [rec(flx), rec(init_lx)], 0)
    c.append('OBSERVABLE_INCLUDE', [rec(flz), rec(init_lz)], 1)
    return c


def stim_conflicts(circuit) -> int:
    """Number of detector sets reached by single events with different logical effect."""
    dem = circuit.detector_error_model(decompose_errors=False)
    groups = defaultdict(set)
    groups[frozenset()].add(frozenset())  # the no-error event
    for inst in dem.flattened():
        if inst.type != 'error':
            continue
        t = inst.targets_copy()
        dets = frozenset(x.val for x in t if x.is_relative_detector_id())
        obs = frozenset(x.val for x in t if x.is_logical_observable_id())
        groups[dets].add(obs)
    return sum(1 for o in groups.values() if len(o) > 1)


def project_verdict(plan: NativeRoundPlan, context) -> tuple[int, bool]:
    """(conflict count, single-fault FT pass) from the project's own verifier."""
    records = native_fault_records(plan, context)
    dec = build_native_decoder(plan, records)
    ok = dec.single_fault_conflicts == 0 and dec.single_fault_failures == 0 and dec.incoming_failures == 0
    return int(dec.single_fault_conflicts), bool(ok)


def unrouted_plan(labels, hubs) -> NativeRoundPlan:
    """All-to-all control: each logical interaction is one direct CX (graph ignored)."""
    checks = []
    for ci, ((ctype, support), label, hub) in enumerate(zip(CHECKS, labels, hubs)):
        template = schedule_from_label(label)
        hub_node = HUB_NODES[hub]
        routes = []
        for ri, tok in enumerate(template):
            ep, act = (DATA_NODES[support[tok]], support[tok]) if tok < 4 else (FLAG_NODES[tok], -1)
            s, t = (hub_node, ep) if ctype == 'X' else (ep, hub_node)
            routes.append(NativeRoute(tok, act, (s, t), (NativeCX(s, t, 0, 250.0, ci, tok, ri, 0),), 250.0))
        checks.append(NativeCheckPlan(ci, ctype, tuple(support), label, hub, hub_node,
                                      FLAG_A in template, FLAG_B in template, tuple(routes)))
    return NativeRoundPlan(tuple(labels), tuple(hubs), tuple(checks), 0, 0.0)


def compare(plan, context) -> dict:
    s = stim_conflicts(plan_to_stim(plan))
    t, ok = project_verdict(plan, context)
    return {'stim_conflicts': s, 'project_conflicts': t, 'stim_pass': s == 0, 'project_pass': ok,
            'agree': (s == t) and ((s == 0) == ok)}


def main(argv=None) -> int:
    _require_stim()
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--paths', action='store_true', help='also check single-path mutations (v3 model)')
    ap.add_argument('--limit', type=int, default=0, help='only the first N catalog entries')
    ap.add_argument('--out', type=Path, default=None, help='optional JSON file for per-circuit results')
    args = ap.parse_args(argv)

    from qecflag.phase5_noise import sample_hardware_contexts
    from qecflag.phase6_native import build_native_plan
    from qecflag.phase7_routing import build_bridge_plan

    ctx = sample_hardware_contexts(1, 7101, 'hw_id').context(0)  # Phase-7 catalog nominal context
    entries = json.loads((ROOT / 'cache' / 'phase7_certified_bridge_catalog.json').read_text())['entries']
    if args.limit:
        entries = entries[:args.limit]
    t0 = time.time()
    results = defaultdict(list)
    for e in entries:
        labels, hubs = tuple(e['labels']), tuple(e['hubs'])
        results['unrouted'].append(compare(unrouted_plan(labels, hubs), ctx))
        results['swap'].append(compare(build_native_plan(labels, hubs, ctx), ctx))
        results['bridge'].append(compare(build_bridge_plan(labels, hubs, ctx), ctx))
    if args.paths:
        from ftrepair_v3.model import RoutingState, build_plan, physical_path_candidates
        base = RoutingState.from_parts(entries[0]['labels'], entries[0]['hubs'])
        for c in range(6):
            for r in range(len(entries[0]['labels'][c])):
                for path in physical_path_candidates(base, c, r, context=None, max_paths=6):
                    results['path_mutation'].append(compare(build_plan(base.with_path(c, r, path), ctx), ctx))

    total = agree = 0
    print(f'{"family":15s} {"circuits":>8s} {"agree":>6s} {"stim pass":>10s} {"project pass":>13s}')
    for name, rows in results.items():
        a = sum(r['agree'] for r in rows); total += len(rows); agree += a
        print(f'{name:15s} {len(rows):8d} {a:6d} {sum(r["stim_pass"] for r in rows):10d} '
              f'{sum(r["project_pass"] for r in rows):13d}')
    print(f'TOTAL agreement {agree}/{total}  ({time.time() - t0:.1f}s)')
    if args.out:
        args.out.write_text(json.dumps(results, indent=1))
    return 0 if agree == total else 1


if __name__ == '__main__':
    raise SystemExit(main())

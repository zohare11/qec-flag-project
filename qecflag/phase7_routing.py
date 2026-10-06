"""Phase 7: fault-tolerance-aware physical routing primitives.

Phase 6 showed that generic SWAP-forward/CNOT/SWAP-back routing can create
first-order logical failures.  Phase 7 adds an alternative nearest-neighbour
remote-CNOT construction (a CNOT bridge) and, critically, does not assume that
the primitive is fault tolerant.  Complete routed rounds are exhaustively
single-fault certified before they are admitted to the Phase-7 catalog.

The bridge implements an endpoint CNOT while restoring all intermediate qubits.
For the fixed 3x4 grid used in Phases 5-7, every required interaction has an
ancilla-interior path of at most three hops.  Paths are chosen topologically,
independent of calibration, so certification is not invalidated by a later
change in edge error rates or durations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import numpy as np

from .physics import code_tables
from .phase3_physics import FLAG_A, FLAG_B, schedule_from_label
from .phase4_physics import CHECKS, N_CHECKS
from .phase5_hardware import (
    DATA_NODES, HUB_NODES, FLAG_NODES, candidate_paths, HardwareContext,
)
from .phase6_native import (
    NativeCX, NativeRoute, NativeCheckPlan, NativeRoundPlan, NativeRisk,
    native_fault_records, build_native_decoder,
)

A = FLAG_A
B = FLAG_B
_DATA_SET = frozenset(DATA_NODES)


def ft_candidate_paths(source: int, target: int) -> tuple[tuple[int, ...], ...]:
    """Return deterministic candidate paths, preferring no interior data nodes.

    This is a topology rule, not a noise-aware path optimizer.  Keeping route
    choice independent of calibration makes single-fault certification reusable
    across the synthetic calibration families.
    """
    paths = tuple(p for p in candidate_paths(int(source), int(target)) if len(p) - 1 <= 3)
    if not paths:
        raise ValueError(f'No <=3-hop path from {source} to {target}')
    ancilla_only = tuple(p for p in paths if not any(node in _DATA_SET for node in p[1:-1]))
    pool = ancilla_only if ancilla_only else paths
    return tuple(sorted(pool, key=lambda p: (len(p), p)))


def choose_ft_path(source: int, target: int) -> tuple[int, ...]:
    return ft_candidate_paths(source, target)[0]


def bridge_cnot_pairs(path: Iterable[int]) -> tuple[tuple[int, int], ...]:
    """Nearest-neighbour CNOT sequence for endpoint CNOT, interiors restored.

    The path is oriented control -> target.  On the Phase-7 graph only 1-, 2-,
    and 3-hop routes are required.  The 2-hop sequence has four CNOTs.  The
    3-hop sequence has eight CNOTs.  Both are linear reversible identities on
    every intermediate qubit and CNOT on the endpoints.
    """
    p = tuple(int(x) for x in path)
    d = len(p) - 1
    if d == 1:
        return ((p[0], p[1]),)
    if d == 2:
        a, b, c = p
        return ((a, b), (b, c), (a, b), (b, c))
    if d == 3:
        a, b, c, dnode = p
        return (
            (a, b), (b, c), (c, dnode), (b, c),
            (a, b), (b, c), (c, dnode), (b, c),
        )
    raise ValueError(f'Bridge primitive supports 1-3 hops, got {d}')


def _edge_id(u: int, v: int) -> int:
    from .phase5_hardware import EDGE_INDEX
    a, b = (u, v) if u < v else (v, u)
    return int(EDGE_INDEX[(a, b)])


def _expand_bridge(path: tuple[int, ...], context: HardwareContext,
                   check: int, token: int, route_index: int) -> tuple[NativeCX, ...]:
    out = []
    for gi, (control, target) in enumerate(bridge_cnot_pairs(path)):
        eid = _edge_id(control, target)
        out.append(NativeCX(
            control=int(control), target=int(target), edge_id=eid,
            duration_ns=float(context.edge_duration[eid]), check=int(check),
            token=int(token), route_index=int(route_index), gate_index=int(gi),
        ))
    return tuple(out)


def build_bridge_plan(labels: Iterable[str], hubs: Iterable[int],
                      context: HardwareContext) -> NativeRoundPlan:
    labels = tuple(str(x) for x in labels)
    hubs = tuple(int(x) for x in hubs)
    if len(labels) != N_CHECKS or len(hubs) != N_CHECKS:
        raise ValueError('Expected six labels and six hubs')
    if any(h not in (0, 1) for h in hubs):
        raise ValueError('hub choices must be 0 or 1')
    context.validate()

    checks: list[NativeCheckPlan] = []
    total_cx = 0
    total_duration = 0.0
    for ci, ((check_type, support), label, hub) in enumerate(zip(CHECKS, labels, hubs)):
        template = schedule_from_label(label)
        hub_node = HUB_NODES[hub]
        routes: list[NativeRoute] = []
        for ri, token in enumerate(template):
            if 0 <= token < 4:
                endpoint = DATA_NODES[support[token]]
                active_data = int(support[token])
            elif token == A:
                endpoint = FLAG_NODES[A]
                active_data = -1
            elif token == B:
                endpoint = FLAG_NODES[B]
                active_data = -1
            else:
                raise ValueError(f'Unknown token {token}')

            # Path orientation is always physical CNOT control -> target.
            source, target = ((hub_node, endpoint) if check_type == 'X'
                              else (endpoint, hub_node))
            path = choose_ft_path(source, target)
            cxs = _expand_bridge(path, context, ci, token, ri)
            duration = float(sum(g.duration_ns for g in cxs))
            routes.append(NativeRoute(
                token=int(token), active_data=active_data, path=path,
                cxs=cxs, duration_ns=duration,
            ))
            total_cx += len(cxs)
            total_duration += duration

        checks.append(NativeCheckPlan(
            check=ci, check_type=check_type, support=tuple(support), label=label,
            hub=hub, hub_node=hub_node, used_a=A in template, used_b=B in template,
            routes=tuple(routes),
        ))
    return NativeRoundPlan(labels, hubs, tuple(checks), int(total_cx), float(total_duration))


@dataclass(frozen=True)
class SingleFaultCertificate:
    passed: bool
    conflicts: int
    single_fault_failures: int
    incoming_failures: int
    c1: float
    native_cx: int
    duration_ns: float
    fault_outcomes: int
    physical_fault_locations: int


def _risk_from_plan(plan: NativeRoundPlan, context: HardwareContext,
                    pair_block: int = 128, compute_c2: bool = True) -> NativeRisk:
    """Phase-6 native risk calculation for an already constructed plan."""
    records = native_fault_records(plan, context)
    decoder = build_native_decoder(plan, records)
    canon, _, _, _ = code_tables()
    single_corr = decoder.corrections_for(records.observation)
    single_fail = canon[records.data ^ single_corr] != 0
    c1 = float(records.weight[single_fail].sum())
    single_count = int(np.count_nonzero(single_fail))

    c2 = 0.0
    malignant_count = 0
    if compute_c2:
        n = len(records.data)
        all_j = np.arange(n, dtype=np.int32)[None, :]
        data_all = records.data[None, :]
        obs_all = records.observation[None, :]
        loc_all = records.location[None, :]
        weight_all = records.weight[None, :]
        for start in range(0, n, int(pair_block)):
            stop = min(n, start + int(pair_block))
            ii = np.arange(start, stop, dtype=np.int32)[:, None]
            valid = (all_j > ii) & (loc_all != records.location[start:stop, None])
            if not np.any(valid):
                continue
            data = records.data[start:stop, None] ^ data_all
            obs = records.observation[start:stop, None] ^ obs_all
            corr = decoder.corrections_for(obs)
            fail = (canon[data ^ corr] != 0) & valid
            malignant_count += int(np.count_nonzero(fail))
            if np.any(fail):
                prod = records.weight[start:stop, None] * weight_all
                c2 += float(prod[fail].sum())

    return NativeRisk(
        plan=plan, records=records, decoder=decoder, c1=c1, c2=float(c2),
        single_fault_failure_count=single_count,
        malignant_pair_count=int(malignant_count),
    )


def bridge_native_risk(labels: Iterable[str], hubs: Iterable[int],
                       context: HardwareContext, pair_block: int = 128,
                       compute_c2: bool = True) -> NativeRisk:
    return _risk_from_plan(
        build_bridge_plan(labels, hubs, context), context,
        pair_block=pair_block, compute_c2=compute_c2,
    )


def certify_bridge_round(labels: Iterable[str], hubs: Iterable[int],
                         context: HardwareContext) -> SingleFaultCertificate:
    risk = bridge_native_risk(labels, hubs, context, compute_c2=False)
    locations = int(len(np.unique(risk.records.location)))
    passed = bool(
        risk.c1 == 0.0
        and risk.decoder.single_fault_conflicts == 0
        and risk.decoder.single_fault_failures == 0
        and risk.decoder.incoming_failures == 0
    )
    return SingleFaultCertificate(
        passed=passed,
        conflicts=int(risk.decoder.single_fault_conflicts),
        single_fault_failures=int(risk.decoder.single_fault_failures),
        incoming_failures=int(risk.decoder.incoming_failures),
        c1=float(risk.c1), native_cx=int(risk.plan.native_cx),
        duration_ns=float(risk.plan.duration_ns),
        fault_outcomes=int(len(risk.records.data)), physical_fault_locations=locations,
    )

@dataclass(frozen=True)
class BridgeProxyMetrics:
    c2: float
    native_cx: int
    duration_ns: float
    hub0_fraction: float
    two_flag_fraction: float


def _gate_slice(token: int) -> slice:
    slot = token if 0 <= token < 4 else (4 if token == A else 5)
    start = 3 + 15 * slot
    return slice(start, start + 15)


def _single_data_index(check_type: str, data_code: int) -> int:
    if check_type == 'Z':
        pa, pb = data_code, 0
    else:
        pa, pb = 0, data_code
    return 4 * pa + pb - 1


def bridge_proxy_metrics(labels: Iterable[str], hubs: Iterable[int],
                         context: HardwareContext) -> BridgeProxyMetrics:
    """Cheap collapsed proxy used only to rank already-certified bridge rounds."""
    from .phase4_physics import round_c2
    labels = tuple(labels); hubs = tuple(int(x) for x in hubs)
    plan = build_bridge_plan(labels, hubs, context)
    eff = np.asarray(context.logical, dtype=np.float64).copy()
    active_by_data = np.zeros(7, dtype=np.float64)
    data_locations: list[list[tuple[int, int]]] = [[] for _ in range(7)]

    for cp in plan.checks:
        ci = cp.check
        eff[ci, 0] *= context.prep_scale[cp.hub_node]
        eff[ci, 93] *= context.meas_scale[cp.hub_node]
        if cp.used_a:
            eff[ci, 1] *= context.prep_scale[FLAG_NODES[A]]
            eff[ci, 94] *= context.meas_scale[FLAG_NODES[A]]
        if cp.used_b:
            eff[ci, 2] *= context.prep_scale[FLAG_NODES[B]]
            eff[ci, 95] *= context.meas_scale[FLAG_NODES[B]]
        for route in cp.routes:
            scale = float(sum(context.edge_error[g.edge_id] for g in route.cxs))
            eff[ci, _gate_slice(route.token)] *= scale
            if route.active_data >= 0:
                q = int(route.active_data)
                active_by_data[q] += route.duration_ns
                data_locations[q].append((ci, int(route.token)))

    idle_by_data = np.maximum(0.0, plan.duration_ns - active_by_data)
    for q in range(7):
        locs = data_locations[q]
        if not locs:
            continue
        idle_weight = float(context.idle_rate[DATA_NODES[q]] * idle_by_data[q])
        share = idle_weight / len(locs)
        for ci, token in locs:
            check_type, _ = CHECKS[ci]
            start = _gate_slice(token).start
            for code in (1, 2, 3):
                eff[ci, start + _single_data_index(check_type, code)] += share / 3.0

    return BridgeProxyMetrics(
        c2=float(round_c2(labels, eff)), native_cx=int(plan.native_cx),
        duration_ns=float(plan.duration_ns),
        hub0_fraction=float(np.mean(np.asarray(hubs) == 0)),
        two_flag_fraction=float(np.mean(['A' in x and 'B' in x for x in labels])),
    )

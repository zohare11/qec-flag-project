"""FT compiler repair v3 physical compiler-state model.

V3 separates logical extraction choices from physical routing choices.  A
``RoutingState`` contains the six logical flag schedules/hub assignments plus
optional per-logical-interaction bridge-path overrides.  The overrides allow the
repair engine to change one physical route without replacing an entire
stabilizer check.

The authoritative safety check remains the existing exact single-fault native
simulator.  This module only changes how a physical plan is constructed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping
import hashlib
import numpy as np

from qecflag.phase3_physics import FLAG_A, FLAG_B, schedule_from_label
from qecflag.phase4_physics import CHECKS, N_CHECKS, verification_summary
from qecflag.phase5_hardware import (
    DATA_NODES, HUB_NODES, FLAG_NODES, EDGE_INDEX, candidate_paths, HardwareContext,
)
from qecflag.phase6_native import NativeCX, NativeRoute, NativeCheckPlan, NativeRoundPlan
from qecflag.phase7_routing import bridge_cnot_pairs, choose_ft_path, _risk_from_plan

A = FLAG_A
B = FLAG_B
RouteKey = tuple[int, int]  # (check, logical route index)


def _norm_path(path: Iterable[int]) -> tuple[int, ...]:
    p = tuple(int(x) for x in path)
    if len(p) < 2:
        raise ValueError('route path must contain distinct endpoints')
    if len(p) - 1 > 3:
        raise ValueError('v3 bridge primitive supports at most three hops')
    if len(set(p)) != len(p):
        raise ValueError('route path must be simple')
    for u, v in zip(p[:-1], p[1:]):
        e = (u, v) if u < v else (v, u)
        if e not in EDGE_INDEX:
            raise ValueError(f'non-edge {u}-{v} in physical path')
    return p


@dataclass(frozen=True)
class RoutingState:
    labels: tuple[str, ...]
    hubs: tuple[int, ...]
    path_overrides: tuple[tuple[int, int, tuple[int, ...]], ...] = tuple()

    def __post_init__(self):
        labels = tuple(map(str, self.labels))
        hubs = tuple(map(int, self.hubs))
        if len(labels) != N_CHECKS or len(hubs) != N_CHECKS:
            raise ValueError('expected six stabilizer checks')
        if any(h not in (0, 1) for h in hubs):
            raise ValueError('hub choices must be 0 or 1')
        norm = []
        seen = set()
        for c, r, p in self.path_overrides:
            key = (int(c), int(r))
            if key in seen:
                raise ValueError(f'duplicate path override {key}')
            seen.add(key)
            norm.append((key[0], key[1], _norm_path(p)))
        object.__setattr__(self, 'labels', labels)
        object.__setattr__(self, 'hubs', hubs)
        object.__setattr__(self, 'path_overrides', tuple(sorted(norm, key=lambda x: (x[0], x[1], x[2]))))

    @classmethod
    def from_parts(cls, labels: Iterable[str], hubs: Iterable[int],
                   path_overrides: Mapping[RouteKey, Iterable[int]] | None = None):
        items = tuple((int(c), int(r), tuple(map(int, p))) for (c, r), p in (path_overrides or {}).items())
        return cls(tuple(map(str, labels)), tuple(map(int, hubs)), items)

    @property
    def override_map(self) -> dict[RouteKey, tuple[int, ...]]:
        return {(c, r): p for c, r, p in self.path_overrides}

    def with_path(self, check: int, route: int, path: Iterable[int] | None):
        m = self.override_map
        key = (int(check), int(route))
        if path is None:
            m.pop(key, None)
        else:
            m[key] = _norm_path(path)
        return RoutingState.from_parts(self.labels, self.hubs, m)

    def with_check(self, check: int, label: str, hub: int, clear_paths: bool = True):
        c = int(check)
        labels = list(self.labels); hubs = list(self.hubs)
        labels[c] = str(label); hubs[c] = int(hub)
        m = self.override_map
        if clear_paths:
            m = {k: v for k, v in m.items() if k[0] != c}
        return RoutingState.from_parts(labels, hubs, m)

    def signature(self) -> tuple:
        return self.labels, self.hubs, self.path_overrides


def logical_ft(labels: Iterable[str]) -> bool:
    v = verification_summary(tuple(labels))
    return bool(v['single_fault_conflicts'] == 0 and v['single_fault_logical_failures'] == 0
                and v['single_incoming_error_failures'] == 0)


def _token_endpoint(check: int, token: int) -> tuple[int, int]:
    check_type, support = CHECKS[int(check)]
    if 0 <= token < 4:
        endpoint = int(DATA_NODES[support[token]])
        active_data = int(support[token])
    elif token == A:
        endpoint = int(FLAG_NODES[A]); active_data = -1
    elif token == B:
        endpoint = int(FLAG_NODES[B]); active_data = -1
    else:
        raise ValueError(f'unknown token {token}')
    return endpoint, active_data


def route_endpoints(state: RoutingState, check: int, route: int) -> tuple[int, int, int, int]:
    c = int(check); r = int(route)
    check_type, _support = CHECKS[c]
    template = schedule_from_label(state.labels[c])
    if r < 0 or r >= len(template):
        raise IndexError((c, r))
    token = int(template[r])
    endpoint, active_data = _token_endpoint(c, token)
    hub_node = int(HUB_NODES[state.hubs[c]])
    source, target = ((hub_node, endpoint) if check_type == 'X' else (endpoint, hub_node))
    return int(source), int(target), token, active_data


def physical_path_candidates(state: RoutingState, check: int, route: int,
                             context: HardwareContext | None = None,
                             max_paths: int = 8,
                             include_data_interiors: bool = True) -> tuple[tuple[int, ...], ...]:
    """Bounded alternative bridge paths for one logical interaction.

    Candidate paths are calibration-independent as a set.  When a context is
    supplied it is used only to order candidates by a cheap physical penalty;
    exact single-fault verification still decides safety.
    """
    source, target, _token, _active = route_endpoints(state, check, route)
    paths = [tuple(map(int, p)) for p in candidate_paths(source, target) if 1 <= len(p) - 1 <= 3]
    if not include_data_interiors:
        data = set(DATA_NODES)
        anc = [p for p in paths if not any(x in data for x in p[1:-1])]
        if anc:
            paths = anc
    current = state.override_map.get((int(check), int(route)), choose_ft_path(source, target))
    if current not in paths:
        paths.append(current)

    def key(p):
        if context is None:
            return (0.0, len(p), p)
        edge_ids = [EDGE_INDEX[(u, v) if u < v else (v, u)] for u, v in zip(p[:-1], p[1:])]
        # Bridge gate multiplicity is not uniform across edges, so score the
        # actual expanded CNOT pairs.
        risk = 0.0; dur = 0.0
        for u, v in bridge_cnot_pairs(p):
            eid = EDGE_INDEX[(u, v) if u < v else (v, u)]
            risk += float(context.edge_error[eid])
            dur += float(context.edge_duration[eid])
        return (risk, dur, len(p), p)

    paths = sorted(set(paths), key=key)
    # Keep current path in the returned set even if its proxy score is poor.
    chosen = [current] + [p for p in paths if p != current]
    return tuple(chosen[:max(1, int(max_paths))])


def _expand_path(path: tuple[int, ...], context: HardwareContext,
                 check: int, token: int, route_index: int) -> tuple[NativeCX, ...]:
    out = []
    for gi, (control, target) in enumerate(bridge_cnot_pairs(path)):
        eid = EDGE_INDEX[(control, target) if control < target else (target, control)]
        out.append(NativeCX(
            control=int(control), target=int(target), edge_id=int(eid),
            duration_ns=float(context.edge_duration[eid]), check=int(check),
            token=int(token), route_index=int(route_index), gate_index=int(gi),
        ))
    return tuple(out)


def build_plan(state: RoutingState, context: HardwareContext) -> NativeRoundPlan:
    context.validate()
    overrides = state.override_map
    checks = []
    total_cx = 0; total_duration = 0.0
    for ci, ((check_type, support), label, hub) in enumerate(zip(CHECKS, state.labels, state.hubs)):
        template = schedule_from_label(label)
        hub_node = int(HUB_NODES[hub])
        routes = []
        for ri, token0 in enumerate(template):
            token = int(token0)
            endpoint, active_data = _token_endpoint(ci, token)
            source, target = ((hub_node, endpoint) if check_type == 'X' else (endpoint, hub_node))
            path = overrides.get((ci, ri), choose_ft_path(source, target))
            path = _norm_path(path)
            if path[0] != source or path[-1] != target:
                raise ValueError(f'path override {(ci,ri)} endpoints {path[0]}->{path[-1]} != {source}->{target}')
            cxs = _expand_path(path, context, ci, token, ri)
            duration = float(sum(x.duration_ns for x in cxs))
            routes.append(NativeRoute(token=int(token), active_data=int(active_data), path=path,
                                      cxs=cxs, duration_ns=duration))
            total_cx += len(cxs); total_duration += duration
        checks.append(NativeCheckPlan(
            check=ci, check_type=check_type, support=tuple(support), label=label,
            hub=int(hub), hub_node=hub_node, used_a=A in template, used_b=B in template,
            routes=tuple(routes),
        ))
    return NativeRoundPlan(state.labels, state.hubs, tuple(checks), int(total_cx), float(total_duration))


def native_risk(state: RoutingState, context: HardwareContext, compute_c2: bool = False,
                pair_block: int = 128):
    if not logical_ft(state.labels):
        raise ValueError('compiler state does not preserve logical single-fault FT')
    return _risk_from_plan(build_plan(state, context), context, pair_block=pair_block, compute_c2=compute_c2)


def passed_native_risk(risk) -> bool:
    return bool(risk.c1 == 0.0 and risk.decoder.single_fault_conflicts == 0
                and risk.decoder.single_fault_failures == 0 and risk.decoder.incoming_failures == 0)


def context_fingerprint(context: HardwareContext) -> str:
    h = hashlib.sha1()
    for name in ('logical', 'edge_error', 'edge_duration', 'prep_scale', 'meas_scale', 'idle_rate'):
        a = np.asarray(getattr(context, name))
        h.update(name.encode()); h.update(str(a.shape).encode()); h.update(a.astype(np.float64, copy=False).tobytes())
    return h.hexdigest()


def route_proxy(state: RoutingState, context: HardwareContext) -> float:
    """Cheap physical ranking cost; never used as a safety decision."""
    plan = build_plan(state, context)
    gate = 0.0
    for cp in plan.checks:
        for route in cp.routes:
            for cx in route.cxs:
                gate += float(context.edge_error[cx.edge_id])
    mean_idle = float(np.mean(context.idle_rate[list(DATA_NODES)]))
    return float(gate + plan.duration_ns * mean_idle * len(DATA_NODES) + 1e-9 * plan.native_cx)


def changed_checks(a: RoutingState, b: RoutingState) -> tuple[int, ...]:
    out = set()
    for c in range(6):
        if a.labels[c] != b.labels[c] or a.hubs[c] != b.hubs[c]:
            out.add(c)
    ma = a.override_map; mb = b.override_map
    for key in set(ma) | set(mb):
        if ma.get(key) != mb.get(key):
            out.add(int(key[0]))
    return tuple(sorted(out))


def edit_atoms(base: RoutingState, state: RoutingState) -> tuple[tuple, ...]:
    atoms = []
    for c in range(6):
        if base.labels[c] != state.labels[c] or base.hubs[c] != state.hubs[c]:
            atoms.append(('check', c, state.labels[c], state.hubs[c]))
    ma = base.override_map; mb = state.override_map
    for key in sorted(set(ma) | set(mb)):
        if ma.get(key) != mb.get(key):
            atoms.append(('path', key[0], key[1], mb.get(key)))
    return tuple(atoms)

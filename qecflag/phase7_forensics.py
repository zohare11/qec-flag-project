"""Phase-7 forensic analysis of first-order failures."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import numpy as np

from .physics import code_tables
from .phase4_physics import CHECK_NAMES, logical_class, verification_summary
from .phase6_native import NativeRisk, build_native_plan, explicit_native_risk
from .phase7_routing import bridge_native_risk

_PAULI = {0: 'I', 1: 'X', 2: 'Z', 3: 'Y'}


def _swap_stage(path: tuple[int, ...], gate_index: int) -> str:
    d = len(path) - 1
    forward = 3 * max(0, d - 1)
    if gate_index < forward:
        return 'forward_swap'
    if gate_index == forward:
        return 'logical_cx'
    return 'reverse_swap'


def failing_single_fault_rows(risk: NativeRisk, primitive: str) -> list[dict]:
    canon, _, _, _ = code_tables()
    correction = risk.decoder.corrections_for(risk.records.observation)
    residual = risk.records.data ^ correction
    failed = canon[residual] != 0
    rows: list[dict] = []
    for idx in np.flatnonzero(failed):
        desc = risk.records.descriptors[int(idx)]
        row = {
            'fault_index': int(idx),
            'kind': desc.kind,
            'check_index': int(desc.check),
            'check_name': CHECK_NAMES[int(desc.check)],
            'location': int(desc.location),
            'weight': float(risk.records.weight[idx]),
            'observation': int(risk.records.observation[idx]),
            'data_error': int(risk.records.data[idx]),
            'decoder_correction': int(correction[idx]),
            'residual': int(residual[idx]),
            'logical_class': logical_class(int(residual[idx])),
            'route_index': int(desc.route),
            'gate_index': int(desc.gate),
            'qubit': int(desc.qubit),
            'pauli_a': _PAULI[int(desc.pauli_a)],
            'pauli_b': _PAULI[int(desc.pauli_b)],
            'primitive': str(primitive),
        }
        if desc.kind == 'cx':
            cp = risk.plan.checks[int(desc.check)]
            route = cp.routes[int(desc.route)]
            gate = route.cxs[int(desc.gate)]
            row.update({
                'token': int(route.token),
                'path': '-'.join(str(x) for x in route.path),
                'path_hops': len(route.path) - 1,
                'edge': f'{min(gate.control, gate.target)}-{max(gate.control, gate.target)}',
                'control': int(gate.control),
                'target': int(gate.target),
                'stage': _swap_stage(route.path, int(desc.gate)) if primitive == 'swap_restore' else 'bridge_cx',
            })
        else:
            row.update({
                'token': -1, 'path': '', 'path_hops': 0, 'edge': '',
                'control': -1, 'target': -1, 'stage': desc.kind,
            })
        rows.append(row)
    return rows


def summarize_failure_rows(rows: list[dict]) -> dict:
    kind = Counter(r['kind'] for r in rows)
    stage = Counter(r['stage'] for r in rows)
    check = Counter(r['check_name'] for r in rows)
    logical = Counter(r['logical_class'] for r in rows)
    route = Counter((r['check_name'], r['token'], r['path'], r['stage']) for r in rows if r['kind'] == 'cx')
    return {
        'failure_count': len(rows),
        'by_kind': dict(sorted(kind.items())),
        'by_stage': dict(sorted(stage.items())),
        'by_check': dict(sorted(check.items())),
        'by_logical_class': dict(sorted(logical.items())),
        'top_routes': [
            {'check': k[0], 'token': int(k[1]), 'path': k[2], 'stage': k[3], 'count': int(v)}
            for k, v in route.most_common(12)
        ],
    }


def forensic_comparison(labels, hubs, context, pair_block: int = 128,
                        example_limit: int = 20) -> dict:
    labels = tuple(labels); hubs = tuple(hubs)
    logical = verification_summary(labels)
    swap = explicit_native_risk(labels, hubs, context, pair_block=pair_block)
    bridge = bridge_native_risk(labels, hubs, context, pair_block=pair_block)
    swap_rows = failing_single_fault_rows(swap, 'swap_restore')
    bridge_rows = failing_single_fault_rows(bridge, 'bridge')
    return {
        'labels': list(labels),
        'hubs': list(hubs),
        'logical_unrouted_control': logical,
        'swap_restore': {
            'native_cx': swap.plan.native_cx,
            'duration_ns': swap.plan.duration_ns,
            'c1': swap.c1,
            'c2': swap.c2,
            'conflicts': swap.decoder.single_fault_conflicts,
            'single_fault_failures': swap.decoder.single_fault_failures,
            'incoming_failures': swap.decoder.incoming_failures,
            'single_fault_ft_pass': swap.fault_tolerant_single_fault,
            'failure_summary': summarize_failure_rows(swap_rows),
            'failures': swap_rows,
            'examples': swap_rows[:int(example_limit)],
        },
        'bridge_same_logical_schedule': {
            'native_cx': bridge.plan.native_cx,
            'duration_ns': bridge.plan.duration_ns,
            'c1': bridge.c1,
            'c2': bridge.c2,
            'conflicts': bridge.decoder.single_fault_conflicts,
            'single_fault_failures': bridge.decoder.single_fault_failures,
            'incoming_failures': bridge.decoder.incoming_failures,
            'single_fault_ft_pass': bridge.fault_tolerant_single_fault,
            'failure_summary': summarize_failure_rows(bridge_rows),
            'failures': bridge_rows,
            'examples': bridge_rows[:int(example_limit)],
        },
    }

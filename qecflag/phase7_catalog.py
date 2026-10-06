"""Build a small catalog of physically single-fault-certified bridge rounds."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np

from .phase5_actions import ensure_hardware_action_table, actions_to_round
from .phase5_noise import sample_hardware_contexts
from .phase7_routing import certify_bridge_round

SCHEMA = 1
NOMINAL_SEED = 7101
MIXED_TOP_K = 8


@dataclass
class CertifiedBridgeCatalog:
    entries: list[dict]
    metadata: dict

    def __len__(self):
        return len(self.entries)

    def actions(self, i: int) -> tuple[int, ...]:
        return tuple(int(x) for x in self.entries[int(i)]['actions'])

    def labels_hubs(self, i: int):
        e = self.entries[int(i)]
        return tuple(e['labels']), tuple(int(x) for x in e['hubs'])


def _entry(actions, labels, hubs, cert, source: str) -> dict:
    return {
        'actions': [int(x) for x in actions],
        'labels': list(labels),
        'hubs': [int(x) for x in hubs],
        'source': str(source),
        'native_cx': int(cert.native_cx),
        'nominal_duration_ns': float(cert.duration_ns),
        'fault_outcomes': int(cert.fault_outcomes),
        'physical_fault_locations': int(cert.physical_fault_locations),
        'c1': float(cert.c1),
        'single_fault_conflicts': int(cert.conflicts),
        'single_fault_failures': int(cert.single_fault_failures),
        'incoming_failures': int(cert.incoming_failures),
    }


def build_catalog(project_root: Path, progress: bool = False) -> CertifiedBridgeCatalog:
    project_root = Path(project_root)
    table = ensure_hardware_action_table(project_root)
    nominal = sample_hardware_contexts(1, NOMINAL_SEED, 'hw_id').context(0)

    homogeneous: list[dict] = []
    for action in range(table.n_actions):
        actions = (action,) * 6
        labels, hubs = actions_to_round(actions, table)
        cert = certify_bridge_round(labels, hubs, nominal)
        if cert.passed:
            homogeneous.append(_entry(actions, labels, hubs, cert, 'homogeneous'))
        if progress and (action + 1) % 16 == 0:
            print(f'P7 CERT homogeneous {action + 1}/{table.n_actions}: safe={len(homogeneous)}')
    if not homogeneous:
        raise RuntimeError('No single-fault-certified bridge rounds were found')

    homogeneous.sort(key=lambda e: (
        e['native_cx'], e['nominal_duration_ns'], e['labels'][0], e['hubs'][0]
    ))
    base = homogeneous[0]
    top_actions = []
    for e in homogeneous:
        a = int(e['actions'][0])
        if a not in top_actions:
            top_actions.append(a)
        if len(top_actions) >= MIXED_TOP_K:
            break

    entries_by_actions = {tuple(e['actions']): e for e in homogeneous}
    base_actions = list(base['actions'])
    for check in range(6):
        for action in top_actions:
            actions = list(base_actions)
            actions[check] = int(action)
            key = tuple(actions)
            if key in entries_by_actions:
                continue
            labels, hubs = actions_to_round(key, table)
            cert = certify_bridge_round(labels, hubs, nominal)
            if cert.passed:
                entries_by_actions[key] = _entry(key, labels, hubs, cert, 'single_check_variant')
        if progress:
            print(f'P7 CERT mixed check {check + 1}/6: total_safe={len(entries_by_actions)}')

    entries = list(entries_by_actions.values())
    entries.sort(key=lambda e: (
        e['native_cx'], e['nominal_duration_ns'], e['source'],
        tuple(e['labels']), tuple(e['hubs'])
    ))
    kinds = {'A_only': 0, 'B_only': 0, 'A_and_B': 0, 'mixed_kind': 0}
    for e in entries:
        local = []
        for label in e['labels']:
            has_a = 'A' in label; has_b = 'B' in label
            local.append('A_and_B' if has_a and has_b else ('A_only' if has_a else 'B_only'))
        if len(set(local)) == 1:
            kinds[local[0]] += 1
        else:
            kinds['mixed_kind'] += 1

    meta = {
        'schema': SCHEMA,
        'nominal_seed': NOMINAL_SEED,
        'route_primitive': 'nearest-neighbour bridge CNOT with deterministic ancilla-interior path preference',
        'certification': 'exhaustive single native fault + incoming single data errors; C1 must equal zero',
        'hardware_actions_checked_homogeneous': int(table.n_actions),
        'certified_homogeneous': int(len(homogeneous)),
        'mixed_top_k': MIXED_TOP_K,
        'catalog_size': int(len(entries)),
        'counts_by_round_kind': kinds,
        'base_actions': list(base['actions']),
        'base_labels': list(base['labels']),
        'base_hubs': list(base['hubs']),
    }
    return CertifiedBridgeCatalog(entries, meta)


def save_catalog(catalog: CertifiedBridgeCatalog, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'metadata': catalog.metadata, 'entries': catalog.entries}, indent=2) + '\n')


def load_catalog(path: Path) -> CertifiedBridgeCatalog:
    payload = json.loads(Path(path).read_text())
    if payload['metadata'].get('schema') != SCHEMA:
        raise ValueError('Phase-7 catalog schema mismatch')
    return CertifiedBridgeCatalog(list(payload['entries']), dict(payload['metadata']))


def ensure_catalog(project_root: Path, path: Path | None = None, progress: bool = False) -> CertifiedBridgeCatalog:
    project_root = Path(project_root)
    path = project_root / 'cache' / 'phase7_certified_bridge_catalog.json' if path is None else Path(path)
    if path.exists():
        return load_catalog(path)
    cat = build_catalog(project_root, progress=progress)
    save_catalog(cat, path)
    return cat

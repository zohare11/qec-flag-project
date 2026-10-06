"""Deterministic local-template action table for Phase 4.

The full Phase-3 expanded catalog contains 4,896 certified local templates.  A
48-template action table (16 A-only, 16 B-only, 16 A+B) is selected once using
only a fixed synthetic *design bank*.  This is offline action-space pruning,
not test-set tuning.  Phase 4 then synthesizes a six-check round by choosing one
local template per check, giving 48**6 > 12 billion possible full rounds.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np

from .phase3_catalog import ensure_catalog
from .phase3_noise import sample_contexts
from .phase3_physics import schedule_from_label, schedule_kind, FLAG_A, FLAG_B

ACTION_TABLE_SCHEMA = 1
DEFAULT_PER_KIND = 16
DESIGN_BANK_SIZE = 384
DESIGN_BANK_SEED = 4041


@dataclass
class ActionTable:
    labels: list[str]
    kinds: np.ndarray
    catalog_indices: np.ndarray
    structural: np.ndarray
    metadata: dict

    def __post_init__(self):
        self._index = {label: i for i, label in enumerate(self.labels)}

    @property
    def n_actions(self) -> int:
        return len(self.labels)

    def index(self, label: str) -> int | None:
        return self._index.get(label)


def template_structural_features(label: str) -> np.ndarray:
    schedule = schedule_from_label(label)
    kind = schedule_kind(schedule)
    kind_vec = np.array([kind == 'A_only', kind == 'B_only', kind == 'A_and_B'], dtype=np.float64)
    length = max(1, len(schedule) - 1)
    data_pos = np.array([schedule.index(q) / length for q in range(4)], dtype=np.float64)
    extras = []
    for flag in (FLAG_A, FLAG_B):
        pos = [i / length for i, token in enumerate(schedule) if token == flag]
        extras.extend(pos if pos else [-1.0, -1.0])
    return np.concatenate([kind_vec, data_pos, np.asarray(extras, dtype=np.float64)])


def _build_action_table(project_root: Path, per_kind: int = DEFAULT_PER_KIND) -> ActionTable:
    catalog = ensure_catalog(project_root / 'cache' / 'phase3_expanded_catalog.npz', 'expanded', progress=False)
    design = sample_contexts(DESIGN_BANK_SIZE, DESIGN_BANK_SEED, 'synthesis_train')
    costs = catalog.all_costs(design)
    # Normalize per calibration so a few high-scale contexts do not dominate.
    denom = np.maximum(costs.min(axis=1, keepdims=True), 1e-12)
    score = np.mean(costs / denom, axis=0)

    selected = []
    for kind in ('A_only', 'B_only', 'A_and_B'):
        idx = catalog.subset(kind)
        ranked = idx[np.argsort(score[idx], kind='stable')]
        selected.extend(ranked[:per_kind].tolist())

    # Keep the Phase-3 reference if it was pruned, replacing the worst A-only
    # selected entry.  This gives all phases a common reference schedule.
    ref_idx = catalog.index('0A12A3')
    if ref_idx is not None and ref_idx not in selected:
        a_positions = [i for i, cidx in enumerate(selected) if catalog.kinds[cidx] == 'A_only']
        worst_pos = max(a_positions, key=lambda pos: score[selected[pos]])
        selected[worst_pos] = ref_idx

    # Stable ordering by kind, then design score, then label.
    selected = sorted(set(selected), key=lambda i: (
        {'A_only': 0, 'B_only': 1, 'A_and_B': 2}[str(catalog.kinds[i])],
        float(score[i]), catalog.labels[i]
    ))
    labels = [catalog.labels[i] for i in selected]
    kinds = np.asarray([catalog.kinds[i] for i in selected], dtype='U8')
    structural = np.stack([template_structural_features(label) for label in labels])
    metadata = {
        'schema': ACTION_TABLE_SCHEMA,
        'per_kind': per_kind,
        'design_bank_size': DESIGN_BANK_SIZE,
        'design_bank_seed': DESIGN_BANK_SEED,
        'source_catalog_fingerprint': catalog.fingerprint,
        'reference_label': '0A12A3',
        'full_round_space_size': int(len(labels) ** 6),
    }
    return ActionTable(labels, kinds, np.asarray(selected, dtype=np.int32), structural, metadata)


def save_action_table(table: ActionTable, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(table.metadata)
    payload['labels'] = table.labels
    payload['kinds'] = table.kinds.tolist()
    payload['catalog_indices'] = table.catalog_indices.tolist()
    payload['structural'] = table.structural.tolist()
    path.write_text(json.dumps(payload, indent=2) + '\n')


def load_action_table(path: Path) -> ActionTable:
    payload = json.loads(path.read_text())
    if payload.get('schema') != ACTION_TABLE_SCHEMA:
        raise ValueError('Phase-4 action-table schema mismatch')
    return ActionTable(
        list(payload['labels']),
        np.asarray(payload['kinds'], dtype='U8'),
        np.asarray(payload['catalog_indices'], dtype=np.int32),
        np.asarray(payload['structural'], dtype=np.float64),
        {k: v for k, v in payload.items() if k not in ('labels', 'kinds', 'catalog_indices', 'structural')},
    )


def ensure_action_table(project_root: Path, path: Path | None = None) -> ActionTable:
    path = project_root / 'cache' / 'phase4_action_table.json' if path is None else path
    if path.exists():
        return load_action_table(path)
    table = _build_action_table(project_root)
    save_action_table(table, path)
    return table

"""Phase-5 hardware actions = Phase-4 local template x syndrome-hub choice."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import numpy as np

from .phase4_templates import ActionTable, ensure_action_table


@dataclass
class HardwareActionTable:
    labels: list[str]
    template_indices: np.ndarray
    hubs: np.ndarray
    kinds: np.ndarray
    structural: np.ndarray
    phase4: ActionTable

    def __post_init__(self):
        self._index = {label: i for i, label in enumerate(self.labels)}

    @property
    def n_actions(self) -> int:
        return len(self.labels)

    def index(self, label: str) -> int | None:
        return self._index.get(label)

    def template_label(self, action: int) -> str:
        return self.phase4.labels[int(self.template_indices[int(action)])]

    def hub(self, action: int) -> int:
        return int(self.hubs[int(action)])


def ensure_hardware_action_table(project_root: Path) -> HardwareActionTable:
    base = ensure_action_table(project_root)
    labels, templates, hubs, kinds, structural = [], [], [], [], []
    for hub in (0, 1):
        for ti, (label, kind) in enumerate(zip(base.labels, base.kinds)):
            labels.append(f'H{hub}|{label}')
            templates.append(ti); hubs.append(hub); kinds.append(str(kind))
            structural.append(np.concatenate([base.structural[ti], np.array([hub == 0, hub == 1], dtype=np.float64)]))
    return HardwareActionTable(
        labels, np.asarray(templates, dtype=np.int32), np.asarray(hubs, dtype=np.int8),
        np.asarray(kinds, dtype='U8'), np.stack(structural), base,
    )


def actions_to_round(actions, table: HardwareActionTable) -> tuple[tuple[str, ...], tuple[int, ...]]:
    a = tuple(int(x) for x in actions)
    if len(a) != 6:
        raise ValueError('Expected six hardware actions')
    labels = tuple(table.template_label(x) for x in a)
    hubs = tuple(table.hub(x) for x in a)
    return labels, hubs

"""Six-decision full-round synthesis state/feature encoding for Phase 4."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

from .phase4_physics import CHECKS, CHECK_NAMES
from .phase4_templates import ActionTable


@dataclass(frozen=True)
class RoundSynthState:
    choices: tuple[int, ...] = ()

    @property
    def step(self) -> int:
        return len(self.choices)

    @property
    def done(self) -> bool:
        return len(self.choices) == 6


def apply_action(state: RoundSynthState, action: int, n_actions: int) -> RoundSynthState:
    if state.done:
        raise ValueError('Cannot act after all six checks are assigned')
    if action < 0 or action >= n_actions:
        raise ValueError(f'Invalid action {action}')
    return RoundSynthState(state.choices + (int(action),))


class RoundFeatureEncoder:
    """Context + check identity + compact structural history.

    The policy sees the current check's 96 calibration features, a global mean
    of the six local calibrations, the check identity/type/support, and the
    structural embedding of previously selected local templates.
    """
    def __init__(self, table: ActionTable):
        self.table = table
        self.local_mean = np.zeros(96, dtype=np.float64)
        self.local_scale = np.ones(96, dtype=np.float64)
        self.struct_dim = table.structural.shape[1]

    @property
    def n_features(self) -> int:
        # current local 96 + global mean 96 + check one-hot 6 + type 1 +
        # support bits 7 + history 6*struct_dim + normalized step 1
        return 96 + 96 + 6 + 1 + 7 + 6 * self.struct_dim + 1

    def fit(self, contexts: np.ndarray) -> None:
        x = np.asarray(contexts, dtype=np.float64)
        if x.ndim != 3 or x.shape[1:] != (6, 96):
            raise ValueError('Expected contexts (n,6,96)')
        flat = np.log1p(10 * x.reshape(-1, 96))
        self.local_mean = flat.mean(axis=0)
        self.local_scale = flat.std(axis=0).clip(1e-4)

    def _norm(self, x: np.ndarray) -> np.ndarray:
        return (np.log1p(10 * np.asarray(x, dtype=np.float64)) - self.local_mean) / self.local_scale

    def encode(self, context: np.ndarray, state: RoundSynthState) -> np.ndarray:
        if state.done:
            raise ValueError('Terminal state has no next-check encoding')
        context = np.asarray(context, dtype=np.float64)
        if context.shape != (6, 96):
            raise ValueError('Expected one context with shape (6,96)')
        step = state.step
        current = self._norm(context[step])
        global_mean = self._norm(context.mean(axis=0))
        check_onehot = np.zeros(6, dtype=np.float64)
        check_onehot[step] = 1.0
        check_type, support = CHECKS[step]
        type_bit = np.array([1.0 if check_type == 'X' else 0.0])
        support_bits = np.zeros(7, dtype=np.float64)
        support_bits[list(support)] = 1.0
        history = np.zeros((6, self.struct_dim), dtype=np.float64)
        for i, action in enumerate(state.choices):
            history[i] = self.table.structural[action]
        return np.concatenate([
            current, global_mean, check_onehot, type_bit, support_bits,
            history.ravel(), np.array([step / 6.0]),
        ])

    def encode_batch(self, contexts: np.ndarray, states: list[RoundSynthState]) -> np.ndarray:
        return np.stack([self.encode(c, s) for c, s in zip(contexts, states)])

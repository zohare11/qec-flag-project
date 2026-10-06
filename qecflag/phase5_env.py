"""Feature encoding for six-step hardware-aware synthesis."""
from __future__ import annotations
import numpy as np

from .phase4_env import RoundSynthState
from .phase4_physics import CHECKS
from .phase5_actions import HardwareActionTable
from .phase5_hardware import HardwareContext


class HardwareFeatureEncoder:
    def __init__(self, table: HardwareActionTable):
        self.table = table
        self.mean = None
        self.scale = None
        self.struct_dim = table.structural.shape[1]

    @property
    def context_dim(self) -> int:
        # current logical + global logical + edge error/duration + prep/meas/idle
        return 96 + 96 + 17 + 17 + 12 + 12 + 12

    @property
    def n_features(self) -> int:
        # normalized context + check onehot + type + support + six-action history + step
        return self.context_dim + 6 + 1 + 7 + 6 * self.struct_dim + 1

    def _raw_context(self, context: HardwareContext, step: int) -> np.ndarray:
        duration = np.asarray(context.edge_duration) / 250.0
        idle = np.asarray(context.idle_rate) * 1e5
        return np.concatenate([
            np.log1p(10 * context.logical[step]),
            np.log1p(10 * context.logical.mean(axis=0)),
            np.log1p(context.edge_error),
            np.log1p(duration),
            np.log1p(context.prep_scale),
            np.log1p(context.meas_scale),
            np.log1p(idle),
        ])

    def fit(self, batch) -> None:
        rows = []
        for i in range(len(batch)):
            c = batch.context(i)
            for step in range(6):
                rows.append(self._raw_context(c, step))
        x = np.stack(rows)
        self.mean = x.mean(axis=0)
        self.scale = x.std(axis=0).clip(1e-4)

    def encode(self, context: HardwareContext, state: RoundSynthState) -> np.ndarray:
        if state.done:
            raise ValueError('Terminal state has no next-check feature')
        if self.mean is None:
            raise ValueError('Encoder must be fit first')
        step = state.step
        base = (self._raw_context(context, step) - self.mean) / self.scale
        check_onehot = np.zeros(6); check_onehot[step] = 1.0
        check_type, support = CHECKS[step]
        type_bit = np.array([1.0 if check_type == 'X' else 0.0])
        support_bits = np.zeros(7); support_bits[list(support)] = 1.0
        history = np.zeros((6, self.struct_dim))
        for i, action in enumerate(state.choices):
            history[i] = self.table.structural[action]
        return np.concatenate([base, check_onehot, type_bit, support_bits, history.ravel(), np.array([step / 6.0])])

    def encode_batch(self, batch, states: list[RoundSynthState]) -> np.ndarray:
        return np.stack([self.encode(batch.context(i), state) for i, state in enumerate(states)])

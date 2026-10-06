"""Sequential schedule-construction grammar for Phase 3."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .phase3_physics import FLAG_A, FLAG_B, STOP_ACTION, schedule_label


@dataclass(frozen=True)
class SynthState:
    prefix: tuple[int, ...] = ()
    done: bool = False


def valid_action_mask(prefix: tuple[int, ...], mode: str) -> np.ndarray:
    mask = np.zeros(7, dtype=bool)
    used_data = {q for q in prefix if 0 <= q <= 3}
    for q in range(4):
        mask[q] = q not in used_data
    a = prefix.count(FLAG_A)
    b = prefix.count(FLAG_B)

    if mode == 'single_A':
        mask[4] = a < 2
        mask[5] = False
        mask[STOP_ACTION] = False
        # Exactly six operations; completion is automatic.
        if len(prefix) >= 6:
            mask[:] = False
        return mask

    if mode != 'expanded':
        raise ValueError("mode must be 'single_A' or 'expanded'")
    mask[4] = a < 2
    mask[5] = b < 2
    data_done = len(used_data) == 4
    valid_flags = (a, b) in ((2, 0), (0, 2), (2, 2))
    mask[STOP_ACTION] = data_done and valid_flags
    if len(prefix) >= 8:
        mask[:6] = False
        mask[STOP_ACTION] = data_done and valid_flags
    return mask


def apply_action(state: SynthState, action: int, mode: str) -> SynthState:
    if state.done:
        raise ValueError('Cannot act on a completed state')
    mask = valid_action_mask(state.prefix, mode)
    if action < 0 or action >= len(mask) or not mask[action]:
        raise ValueError(f'Invalid action {action} for prefix {schedule_label(state.prefix)}')
    if action == STOP_ACTION:
        return SynthState(state.prefix, True)
    token = FLAG_A if action == 4 else FLAG_B if action == 5 else action
    prefix = state.prefix + (token,)
    if mode == 'single_A' and len(prefix) == 6:
        return SynthState(prefix, True)
    return SynthState(prefix, False)


def grammar_complete(prefix: tuple[int, ...], mode: str) -> bool:
    if sorted(q for q in prefix if q < 4) != [0, 1, 2, 3]:
        return False
    a, b = prefix.count(FLAG_A), prefix.count(FLAG_B)
    if mode == 'single_A':
        return len(prefix) == 6 and (a, b) == (2, 0)
    return (a, b) in ((2, 0), (0, 2), (2, 2)) and len(prefix) in (6, 8)


class FeatureEncoder:
    """Noise context + ordered partial-circuit encoding."""
    def __init__(self, context_dim: int = 96, max_slots: int = 8):
        self.context_dim = context_dim
        self.max_slots = max_slots
        self.mean = np.zeros(context_dim)
        self.scale = np.ones(context_dim)

    @property
    def n_features(self) -> int:
        # standardized noise + 8x6 token one-hots + 4 data-used bits + A/B counts + length
        return self.context_dim + self.max_slots * 6 + 7

    def fit(self, contexts: np.ndarray) -> None:
        x = np.log1p(10 * np.asarray(contexts, dtype=np.float64))
        self.mean = x.mean(axis=0)
        self.scale = x.std(axis=0).clip(1e-4)

    def encode(self, context: np.ndarray, prefix: tuple[int, ...]) -> np.ndarray:
        context = np.asarray(context, dtype=np.float64)
        x = (np.log1p(10 * context) - self.mean) / self.scale
        seq = np.zeros((self.max_slots, 6), dtype=np.float64)
        for pos, token in enumerate(prefix[:self.max_slots]):
            col = token if token < 4 else 4 if token == FLAG_A else 5
            seq[pos, col] = 1.0
        used = np.array([float(q in prefix) for q in range(4)], dtype=np.float64)
        extras = np.concatenate([used, [prefix.count(FLAG_A) / 2, prefix.count(FLAG_B) / 2,
                                        len(prefix) / self.max_slots]])
        return np.concatenate([x, seq.ravel(), extras])

    def encode_batch(self, contexts: np.ndarray, prefixes: list[tuple[int, ...]]) -> np.ndarray:
        return np.stack([self.encode(c, p) for c, p in zip(contexts, prefixes)])

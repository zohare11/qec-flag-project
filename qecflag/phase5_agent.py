"""Actor-critic rollout helpers for Phase-5 hardware actions."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

from .phase4_agent import RoundActorCritic
from .phase4_env import RoundSynthState, apply_action
from .phase5_env import HardwareFeatureEncoder


@dataclass
class HardwareRollout:
    choices: np.ndarray
    features: np.ndarray
    actions: np.ndarray
    episode_index: np.ndarray


def rollout_batch(model: RoundActorCritic, encoder: HardwareFeatureEncoder, batch,
                  rng: np.random.Generator, deterministic: bool = False) -> HardwareRollout:
    n = len(batch)
    states = [RoundSynthState() for _ in range(n)]
    rows_x, rows_a, rows_ep = [], [], []
    for _ in range(6):
        x = encoder.encode_batch(batch, states)
        _, probs, _ = model.forward(x)
        actions = np.argmax(probs, axis=1) if deterministic else np.asarray([
            rng.choice(probs.shape[1], p=row) for row in probs
        ], dtype=np.int64)
        for ep, action in enumerate(actions):
            rows_x.append(x[ep]); rows_a.append(int(action)); rows_ep.append(ep)
            states[ep] = apply_action(states[ep], int(action), probs.shape[1])
    return HardwareRollout(
        np.asarray([s.choices for s in states], dtype=np.int64), np.asarray(rows_x),
        np.asarray(rows_a, dtype=np.int64), np.asarray(rows_ep, dtype=np.int64),
    )


def greedy_choices(model: RoundActorCritic, encoder: HardwareFeatureEncoder, batch) -> np.ndarray:
    return rollout_batch(model, encoder, batch, np.random.default_rng(0), deterministic=True).choices


def beam_candidates(model: RoundActorCritic, encoder: HardwareFeatureEncoder,
                    context, beam_width: int) -> list[tuple[int, ...]]:
    if beam_width < 1:
        raise ValueError('beam_width must be positive')
    beams = [(RoundSynthState(), 0.0)]
    n_actions = model.params['ba'].shape[0]
    for _ in range(6):
        expanded = []
        for state, score in beams:
            x = encoder.encode(context, state)[None, :]
            _, probs, _ = model.forward(x)
            top = np.argsort(probs[0])[-min(beam_width, n_actions):][::-1]
            for action in top:
                nxt = apply_action(state, int(action), n_actions)
                expanded.append((nxt, score + float(np.log(max(probs[0, action], 1e-300)))))
        expanded.sort(key=lambda item: item[1], reverse=True)
        beams = expanded[:beam_width]
    return [tuple(state.choices) for state, _ in beams]

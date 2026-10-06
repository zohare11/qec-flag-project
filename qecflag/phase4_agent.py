"""Actor-critic proposal policy for full-round flagged Steane synthesis."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np

from .agent import Adam
from .phase4_env import RoundSynthState, RoundFeatureEncoder, apply_action
from .phase4_templates import ActionTable


def softmax(logits: np.ndarray) -> np.ndarray:
    logits = np.asarray(logits, dtype=np.float64)
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)


class RoundActorCritic:
    def __init__(self, n_features: int, n_actions: int, hidden: int = 128, seed: int = 0):
        rng = np.random.default_rng(seed)
        self.params = {
            'w1': rng.normal(scale=1 / np.sqrt(n_features), size=(n_features, hidden)),
            'b1': np.zeros(hidden),
            'wa': rng.normal(scale=0.02, size=(hidden, n_actions)),
            'ba': np.zeros(n_actions),
            'wv': rng.normal(scale=0.02, size=hidden),
            'bv': np.zeros(1),
        }

    def forward(self, x: np.ndarray):
        x = np.atleast_2d(np.asarray(x, dtype=np.float64))
        h = np.tanh(x @ self.params['w1'] + self.params['b1'])
        logits = h @ self.params['wa'] + self.params['ba']
        probs = softmax(logits)
        value = h @ self.params['wv'] + self.params['bv'][0]
        return h, probs, value

    def gradient(self, x: np.ndarray, actions: np.ndarray, returns: np.ndarray,
                 entropy_coefficient: float = 0.01, value_coefficient: float = 0.5):
        x = np.asarray(x, dtype=np.float64)
        actions = np.asarray(actions, dtype=np.int64)
        returns = np.asarray(returns, dtype=np.float64)
        h, probs, value = self.forward(x)
        advantage = returns - value
        policy_adv = (advantage - advantage.mean()) / max(advantage.std(), 1e-6)
        logp = np.log(probs.clip(1e-300))
        entropy = -(probs * logp).sum(axis=1)
        n = len(actions)

        delta = policy_adv[:, None] * probs
        delta[np.arange(n), actions] -= policy_adv
        delta += entropy_coefficient * probs * (logp + entropy[:, None])
        delta /= n
        value_delta = value_coefficient * 2 * (value - returns) / n
        hidden_delta = (delta @ self.params['wa'].T + value_delta[:, None] * self.params['wv'][None, :]) * (1 - h * h)
        grads = {
            'wa': h.T @ delta,
            'ba': delta.sum(axis=0),
            'wv': h.T @ value_delta,
            'bv': np.array([value_delta.sum()]),
            'w1': x.T @ hidden_delta,
            'b1': hidden_delta.sum(axis=0),
        }
        policy_loss = -float(np.mean(policy_adv * logp[np.arange(n), actions]))
        value_loss = float(np.mean((value - returns) ** 2))
        total = policy_loss + value_coefficient * value_loss - entropy_coefficient * float(entropy.mean())
        return total, grads, float(entropy.mean()), value_loss

    def save(self, path: Path, encoder: RoundFeatureEncoder, metadata: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path, **self.params, local_mean=encoder.local_mean, local_scale=encoder.local_scale,
            metadata=np.asarray(json.dumps(metadata)),
        )

    @classmethod
    def load(cls, path: Path, table: ActionTable):
        with np.load(path, allow_pickle=False) as saved:
            model = cls(saved['w1'].shape[0], saved['wa'].shape[1], saved['w1'].shape[1])
            for key in model.params:
                model.params[key] = saved[key].copy()
            encoder = RoundFeatureEncoder(table)
            encoder.local_mean = saved['local_mean'].copy()
            encoder.local_scale = saved['local_scale'].copy()
            metadata = json.loads(str(saved['metadata']))
        return model, encoder, metadata


@dataclass
class Rollout:
    choices: np.ndarray  # episodes x 6
    features: np.ndarray
    actions: np.ndarray
    episode_index: np.ndarray


def rollout_batch(model: RoundActorCritic, encoder: RoundFeatureEncoder, contexts: np.ndarray,
                  rng: np.random.Generator, deterministic: bool = False) -> Rollout:
    contexts = np.asarray(contexts, dtype=np.float64)
    n = len(contexts)
    states = [RoundSynthState() for _ in range(n)]
    rows_x, rows_a, rows_ep = [], [], []
    for _ in range(6):
        x = encoder.encode_batch(contexts, states)
        _, probs, _ = model.forward(x)
        actions = np.argmax(probs, axis=1) if deterministic else np.asarray([
            rng.choice(probs.shape[1], p=row) for row in probs
        ], dtype=np.int64)
        for ep, action in enumerate(actions):
            rows_x.append(x[ep])
            rows_a.append(int(action))
            rows_ep.append(ep)
            states[ep] = apply_action(states[ep], int(action), probs.shape[1])
    choices = np.asarray([state.choices for state in states], dtype=np.int64)
    return Rollout(choices, np.asarray(rows_x), np.asarray(rows_a, dtype=np.int64),
                   np.asarray(rows_ep, dtype=np.int64))


def greedy_choices(model: RoundActorCritic, encoder: RoundFeatureEncoder, contexts: np.ndarray) -> np.ndarray:
    return rollout_batch(model, encoder, contexts, np.random.default_rng(0), deterministic=True).choices


def beam_candidates(model: RoundActorCritic, encoder: RoundFeatureEncoder, context: np.ndarray,
                    beam_width: int) -> list[tuple[int, ...]]:
    """Top terminal schedules by policy probability; no round C2 queried here."""
    if beam_width < 1:
        raise ValueError('beam_width must be positive')
    beams: list[tuple[RoundSynthState, float]] = [(RoundSynthState(), 0.0)]
    n_actions = model.params['ba'].shape[0]
    for _ in range(6):
        expanded: list[tuple[RoundSynthState, float]] = []
        for state, score in beams:
            x = encoder.encode(context, state)[None, :]
            _, probs, _ = model.forward(x)
            # Keeping more than beam_width outgoing actions from one parent can
            # never survive the global top-beam truncation.
            top = np.argsort(probs[0])[-min(beam_width, n_actions):][::-1]
            for action in top:
                nxt = apply_action(state, int(action), n_actions)
                expanded.append((nxt, score + float(np.log(max(probs[0, action], 1e-300)))))
        expanded.sort(key=lambda item: item[1], reverse=True)
        beams = expanded[:beam_width]
    return [tuple(state.choices) for state, _ in beams]

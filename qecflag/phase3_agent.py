"""Masked actor-critic for sequential flagged-circuit schedule synthesis."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np
from .agent import Adam
from .phase3_env import SynthState, valid_action_mask, apply_action, FeatureEncoder
from .phase3_physics import schedule_label


def masked_softmax(logits: np.ndarray, masks: np.ndarray) -> np.ndarray:
    logits = np.asarray(logits, dtype=np.float64)
    masks = np.asarray(masks, dtype=bool)
    if logits.shape != masks.shape:
        raise ValueError('logits/mask shape mismatch')
    if np.any(~masks.any(axis=1)):
        raise ValueError('Every nonterminal state must have at least one valid action')
    safe = np.where(masks, logits, -1e30)
    shifted = safe - safe.max(axis=1, keepdims=True)
    exp = np.where(masks, np.exp(shifted), 0.0)
    return exp / exp.sum(axis=1, keepdims=True)


class ActorCritic:
    def __init__(self, n_features: int, hidden: int = 96, n_actions: int = 7, seed: int = 0):
        rng = np.random.default_rng(seed)
        self.params = {
            'w1': rng.normal(scale=1 / np.sqrt(n_features), size=(n_features, hidden)),
            'b1': np.zeros(hidden),
            'wa': rng.normal(scale=0.02, size=(hidden, n_actions)),
            'ba': np.zeros(n_actions),
            'wv': rng.normal(scale=0.02, size=hidden),
            'bv': np.zeros(1),
        }

    def forward_features(self, features: np.ndarray, masks: np.ndarray):
        x = np.atleast_2d(np.asarray(features, dtype=np.float64))
        h = np.tanh(x @ self.params['w1'] + self.params['b1'])
        logits = h @ self.params['wa'] + self.params['ba']
        probs = masked_softmax(logits, masks)
        value = h @ self.params['wv'] + self.params['bv'][0]
        return h, probs, value

    def gradient(self, features: np.ndarray, masks: np.ndarray, actions: np.ndarray,
                 returns: np.ndarray, entropy_coefficient: float = 0.01,
                 value_coefficient: float = 0.5):
        x = np.asarray(features, dtype=np.float64)
        actions = np.asarray(actions, dtype=np.int64)
        returns = np.asarray(returns, dtype=np.float64)
        h, probs, value = self.forward_features(x, masks)
        advantage = returns - value
        # Standardize policy advantages without changing value targets.
        policy_adv = (advantage - advantage.mean()) / max(advantage.std(), 1e-6)
        logp = np.log(probs.clip(1e-300))
        entropy = -(probs * logp).sum(axis=1)
        n = len(actions)

        delta = policy_adv[:, None] * probs
        delta[np.arange(n), actions] -= policy_adv
        # Entropy gradient, matching the Phase-1 implementation; invalid actions have p=0.
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
        return total, grads, float(entropy.mean()), float(value_loss)

    def save(self, path: Path, encoder: FeatureEncoder, metadata: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, **self.params, encoder_mean=encoder.mean, encoder_scale=encoder.scale,
                            metadata=np.asarray(json.dumps(metadata)))

    @classmethod
    def load(cls, path: Path):
        with np.load(path, allow_pickle=False) as saved:
            model = cls(saved['w1'].shape[0], saved['w1'].shape[1], saved['wa'].shape[1])
            for key in model.params:
                model.params[key] = saved[key].copy()
            encoder = FeatureEncoder(context_dim=len(saved['encoder_mean']))
            encoder.mean = saved['encoder_mean'].copy()
            encoder.scale = saved['encoder_scale'].copy()
            metadata = json.loads(str(saved['metadata']))
        return model, encoder, metadata


@dataclass
class Rollout:
    labels: list[str]
    valid: np.ndarray
    features: np.ndarray
    masks: np.ndarray
    actions: np.ndarray
    episode_index: np.ndarray


def rollout_batch(model: ActorCritic, encoder: FeatureEncoder, contexts: np.ndarray,
                  mode: str, rng: np.random.Generator, deterministic: bool = False) -> Rollout:
    contexts = np.asarray(contexts, dtype=np.float64)
    n = len(contexts)
    states = [SynthState() for _ in range(n)]
    rows_x, rows_mask, rows_action, rows_episode = [], [], [], []
    max_decisions = 6 if mode == 'single_A' else 9

    for _ in range(max_decisions):
        active = [i for i, state in enumerate(states) if not state.done]
        if not active:
            break
        prefixes = [states[i].prefix for i in active]
        x = encoder.encode_batch(contexts[active], prefixes)
        masks = np.stack([valid_action_mask(p, mode) for p in prefixes])
        _, probs, _ = model.forward_features(x, masks)
        actions = []
        for row in probs:
            if deterministic:
                actions.append(int(np.argmax(row)))
            else:
                actions.append(int(rng.choice(len(row), p=row)))
        for local, episode in enumerate(active):
            rows_x.append(x[local])
            rows_mask.append(masks[local])
            rows_action.append(actions[local])
            rows_episode.append(episode)
            states[episode] = apply_action(states[episode], actions[local], mode)
    labels = [schedule_label(state.prefix) for state in states]
    valid = np.asarray([state.done for state in states], dtype=bool)
    return Rollout(labels, valid, np.asarray(rows_x), np.asarray(rows_mask),
                   np.asarray(rows_action, dtype=np.int64), np.asarray(rows_episode, dtype=np.int64))


def greedy_labels(model: ActorCritic, encoder: FeatureEncoder, contexts: np.ndarray, mode: str) -> list[str]:
    rng = np.random.default_rng(0)
    return rollout_batch(model, encoder, contexts, mode, rng, deterministic=True).labels


def beam_candidates(model: ActorCritic, encoder: FeatureEncoder, context: np.ndarray,
                    mode: str, beam_width: int) -> list[str]:
    """Top policy-probability terminal schedules; no C2 is queried during expansion."""
    if beam_width < 1:
        raise ValueError('beam_width must be positive')
    beams: list[tuple[SynthState, float]] = [(SynthState(), 0.0)]
    terminals: dict[str, float] = {}
    max_decisions = 6 if mode == 'single_A' else 9
    for _ in range(max_decisions):
        expanded: list[tuple[SynthState, float]] = []
        for state, score in beams:
            if state.done:
                label = schedule_label(state.prefix)
                terminals[label] = max(terminals.get(label, -np.inf), score)
                continue
            x = encoder.encode(context, state.prefix)[None, :]
            mask = valid_action_mask(state.prefix, mode)[None, :]
            _, probs, _ = model.forward_features(x, mask)
            for action in np.flatnonzero(mask[0]):
                nxt = apply_action(state, int(action), mode)
                value = score + float(np.log(max(probs[0, action], 1e-300)))
                if nxt.done:
                    label = schedule_label(nxt.prefix)
                    terminals[label] = max(terminals.get(label, -np.inf), value)
                else:
                    expanded.append((nxt, value))
        expanded.sort(key=lambda item: item[1], reverse=True)
        beams = expanded[:beam_width]
        if not beams:
            break
    ranked = sorted(terminals.items(), key=lambda kv: kv[1], reverse=True)
    return [label for label, _ in ranked[:beam_width]]

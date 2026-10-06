"""Small NumPy REINFORCE policy for a one-step contextual bandit.

It receives calibration weights, selects one certified circuit, and receives
only that action's reward plus a fixed-reference control variate. It never
trains on argmin labels. This is NOT PPO and NOT unrestricted gate synthesis.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np


def softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)


class Policy:
    def __init__(self, n_features: int, n_actions: int, hidden: int = 64, seed: int = 0):
        rng = np.random.default_rng(seed)
        self.params = {
            'w1': rng.normal(scale=1 / np.sqrt(n_features), size=(n_features, hidden)),
            'b1': np.zeros(hidden),
            'w2': rng.normal(scale=0.02, size=(hidden, n_actions)),
            'b2': np.zeros(n_actions),
        }
        self.mean = np.zeros(n_features)
        self.scale = np.ones(n_features)

    def fit_scaler(self, contexts: np.ndarray) -> None:
        features = np.log1p(10 * contexts)
        self.mean = features.mean(axis=0)
        self.scale = features.std(axis=0).clip(1e-4)

    def features(self, contexts: np.ndarray) -> np.ndarray:
        return (np.log1p(10 * np.atleast_2d(contexts)) - self.mean) / self.scale

    def forward(self, contexts: np.ndarray):
        x = self.features(contexts)
        h = np.tanh(x @ self.params['w1'] + self.params['b1'])
        probs = softmax(h @ self.params['w2'] + self.params['b2'])
        return x, h, probs

    def predict(self, contexts: np.ndarray) -> np.ndarray:
        return self.forward(contexts)[2].argmax(axis=1)

    def loss_gradient(self, contexts, actions, advantage, entropy_coefficient=0.01):
        x, h, probs = self.forward(contexts)
        logp = np.log(probs.clip(1e-300))
        batch = len(actions)
        entropy = -(probs * logp).sum(axis=1)
        loss = -(advantage * logp[np.arange(batch), actions]).mean() - entropy_coefficient * entropy.mean()
        delta = advantage[:, None] * probs
        delta[np.arange(batch), actions] -= advantage
        delta += entropy_coefficient * probs * (logp + entropy[:, None])
        delta /= batch
        hidden_delta = (delta @ self.params['w2'].T) * (1 - h * h)
        gradients = {'w2': h.T @ delta, 'b2': delta.sum(axis=0),
                     'w1': x.T @ hidden_delta, 'b1': hidden_delta.sum(axis=0)}
        return float(loss), gradients, float(entropy.mean())

    def save(self, path: Path, metadata: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, **self.params, mean=self.mean, scale=self.scale,
                            metadata=np.array(json.dumps(metadata)))

    @classmethod
    def load(cls, path: Path):
        with np.load(path, allow_pickle=False) as saved:
            model = cls(saved['w1'].shape[0], saved['w2'].shape[1], saved['w1'].shape[1])
            for name in model.params:
                model.params[name] = saved[name].copy()
            model.mean, model.scale = saved['mean'].copy(), saved['scale'].copy()
            metadata = json.loads(str(saved['metadata']))
        return model, metadata


class Adam:
    def __init__(self, params, learning_rate=0.003):
        self.m = {k: np.zeros_like(v) for k, v in params.items()}
        self.v = {k: np.zeros_like(v) for k, v in params.items()}
        self.t = 0
        self.learning_rate = learning_rate

    def step(self, params, gradients):
        self.t += 1
        norm = np.sqrt(sum((g * g).sum() for g in gradients.values()))
        factor = min(1.0, 5.0 / max(norm, 1e-12))
        for key in params:
            g = gradients[key] * factor
            self.m[key] = 0.9 * self.m[key] + 0.1 * g
            self.v[key] = 0.999 * self.v[key] + 0.001 * g * g
            m = self.m[key] / (1 - 0.9 ** self.t)
            v = self.v[key] / (1 - 0.999 ** self.t)
            params[key] -= self.learning_rate * m / (np.sqrt(v) + 1e-8)

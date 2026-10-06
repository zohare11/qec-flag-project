"""NumPy models used in Phase 2: REINFORCE, oracle classifier, cost regressor."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from .agent import Adam, softmax


class FeatureMLP:
    def __init__(self, n_features: int, n_outputs: int, hidden: int = 64, seed: int = 0, output_scale: float = 0.02):
        rng = np.random.default_rng(seed)
        self.params = {
            'w1': rng.normal(scale=1 / np.sqrt(n_features), size=(n_features, hidden)),
            'b1': np.zeros(hidden),
            'w2': rng.normal(scale=output_scale, size=(hidden, n_outputs)),
            'b2': np.zeros(n_outputs),
        }
        self.mean = np.zeros(n_features)
        self.scale = np.ones(n_features)

    def fit_scaler(self, contexts: np.ndarray) -> None:
        features = np.log1p(10 * np.asarray(contexts, dtype=np.float64))
        self.mean = features.mean(axis=0)
        self.scale = features.std(axis=0).clip(1e-4)

    def features(self, contexts: np.ndarray) -> np.ndarray:
        x = np.log1p(10 * np.atleast_2d(contexts).astype(np.float64))
        return (x - self.mean) / self.scale

    def hidden(self, contexts: np.ndarray):
        x = self.features(contexts)
        h = np.tanh(x @ self.params['w1'] + self.params['b1'])
        return x, h

    def raw(self, contexts: np.ndarray):
        x, h = self.hidden(contexts)
        y = h @ self.params['w2'] + self.params['b2']
        return x, h, y

    def save(self, path: Path, metadata: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, **self.params, mean=self.mean, scale=self.scale,
                            metadata=np.array(json.dumps(metadata)))

    @classmethod
    def _load_base(cls, path: Path):
        with np.load(path, allow_pickle=False) as saved:
            model = cls(saved['w1'].shape[0], saved['w2'].shape[1], saved['w1'].shape[1])
            for name in model.params:
                model.params[name] = saved[name].copy()
            model.mean = saved['mean'].copy()
            model.scale = saved['scale'].copy()
            metadata = json.loads(str(saved['metadata']))
        return model, metadata


class Classifier(FeatureMLP):
    def probabilities(self, contexts: np.ndarray) -> np.ndarray:
        return softmax(self.raw(contexts)[2])

    def predict(self, contexts: np.ndarray) -> np.ndarray:
        return self.probabilities(contexts).argmax(axis=1)

    def loss_gradient(self, contexts: np.ndarray, targets: np.ndarray, label_smoothing: float = 0.0):
        x, h, logits = self.raw(contexts)
        probs = softmax(logits)
        targets = np.asarray(targets, dtype=np.float64)
        if label_smoothing:
            targets = (1 - label_smoothing) * targets + label_smoothing / targets.shape[1]
        batch = len(targets)
        loss = -float(np.sum(targets * np.log(probs.clip(1e-300))) / batch)
        delta = (probs - targets) / batch
        hidden_delta = (delta @ self.params['w2'].T) * (1 - h * h)
        gradients = {'w2': h.T @ delta, 'b2': delta.sum(axis=0),
                     'w1': x.T @ hidden_delta, 'b1': hidden_delta.sum(axis=0)}
        accuracy = float(np.mean(targets[np.arange(batch), probs.argmax(axis=1)] > 0))
        return loss, gradients, accuracy

    @classmethod
    def load(cls, path: Path):
        base, metadata = FeatureMLP._load_base(path)
        model = cls(base.params['w1'].shape[0], base.params['w2'].shape[1], base.params['w1'].shape[1])
        model.params, model.mean, model.scale = base.params, base.mean, base.scale
        return model, metadata


class CostRegressor(FeatureMLP):
    """Predict log(C2 / reference_C2) for every certified schedule."""
    def predict_scores(self, contexts: np.ndarray) -> np.ndarray:
        return self.raw(contexts)[2]

    def predict(self, contexts: np.ndarray) -> np.ndarray:
        return self.predict_scores(contexts).argmin(axis=1)

    def loss_gradient(self, contexts: np.ndarray, targets: np.ndarray):
        x, h, prediction = self.raw(contexts)
        targets = np.asarray(targets, dtype=np.float64)
        error = prediction - targets
        loss = float(np.mean(error * error))
        delta = 2 * error / error.size
        hidden_delta = (delta @ self.params['w2'].T) * (1 - h * h)
        gradients = {'w2': h.T @ delta, 'b2': delta.sum(axis=0),
                     'w1': x.T @ hidden_delta, 'b1': hidden_delta.sum(axis=0)}
        return loss, gradients

    @classmethod
    def load(cls, path: Path):
        base, metadata = FeatureMLP._load_base(path)
        model = cls(base.params['w1'].shape[0], base.params['w2'].shape[1], base.params['w1'].shape[1])
        model.params, model.mean, model.scale = base.params, base.mean, base.scale
        return model, metadata


def oracle_soft_targets(costs: np.ndarray, atol: float = 1e-10, rtol: float = 1e-9) -> np.ndarray:
    costs = np.asarray(costs, dtype=np.float64)
    minima = costs.min(axis=1, keepdims=True)
    winners = np.isclose(costs, minima, atol=atol, rtol=rtol)
    return winners / winners.sum(axis=1, keepdims=True)


def relative_log_cost_targets(costs: np.ndarray, reference_index: int) -> np.ndarray:
    costs = np.asarray(costs, dtype=np.float64)
    reference = costs[:, reference_index:reference_index + 1]
    return np.log(np.maximum(costs, 1e-12) / np.maximum(reference, 1e-12))

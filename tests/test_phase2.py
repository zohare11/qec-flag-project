import numpy as np
import pytest
from qecflag.agent import Adam
from qecflag.phase2_models import (Classifier, CostRegressor, oracle_soft_targets,
                                   relative_log_cost_targets)
from qecflag.phase2_noise import FAMILIES, sample_family, validate_batch
from qecflag.phase2_experiment import stable_seed, make_datasets, test_sets as make_test_sets


def test_phase2_families_are_reproducible_nonnegative_and_distinct():
    signatures = []
    for family in FAMILIES:
        a = sample_family(12, 54321, family)
        b = sample_family(12, 54321, family)
        np.testing.assert_array_equal(a, b)
        assert a.shape == (12, 79)
        assert np.isfinite(a).all() and np.all(a >= 0)
        signatures.append(a.tobytes())
    assert len(set(signatures)) == len(FAMILIES)


def test_phase2_batch_validator_rejects_bad_inputs():
    with pytest.raises(ValueError):
        validate_batch(np.zeros((2, 78)))
    bad = np.ones((2, 79)); bad[0, 0] = -1
    with pytest.raises(ValueError):
        validate_batch(bad)


def test_stable_seed_is_deterministic_and_tag_sensitive():
    assert stable_seed(1, 'abc') == stable_seed(1, 'abc')
    assert stable_seed(1, 'abc') != stable_seed(1, 'abd')


def test_oracle_soft_targets_handle_ties():
    costs = np.array([[1., 1., 3.], [3., 2., 1.]])
    t = oracle_soft_targets(costs)
    np.testing.assert_allclose(t[0], [0.5, 0.5, 0])
    np.testing.assert_allclose(t[1], [0, 0, 1])
    np.testing.assert_allclose(t.sum(axis=1), 1)


def test_relative_log_cost_targets_preserve_order():
    costs = np.array([[4., 2., 8.], [3., 9., 1.]])
    t = relative_log_cost_targets(costs, 0)
    np.testing.assert_array_equal(t.argmin(axis=1), costs.argmin(axis=1))
    np.testing.assert_allclose(t[:, 0], 0)


def finite_difference(model, loss_fn, grads, name, position, epsilon=1e-6):
    original = model.params[name][position]
    model.params[name][position] = original + epsilon
    hi = loss_fn()
    model.params[name][position] = original - epsilon
    lo = loss_fn()
    model.params[name][position] = original
    assert grads[name][position] == pytest.approx((hi - lo) / (2 * epsilon), abs=2e-7)


def test_classifier_gradient_finite_difference():
    x = np.array([[0.2, 0.5, 1.2, 0.1], [0.8, 0.3, 0.2, 1.1], [0.4, 0.9, 0.5, 0.7]])
    targets = np.array([[1., 0., 0.], [0., .5, .5], [0., 1., 0.]])
    model = Classifier(4, 3, hidden=5, seed=9)
    model.fit_scaler(x)
    loss, grads, _ = model.loss_gradient(x, targets, 0.02)
    def fn(): return model.loss_gradient(x, targets, 0.02)[0]
    for name, position in [('w1', (0, 0)), ('w1', (3, 4)), ('b1', (2,)),
                           ('w2', (1, 2)), ('b2', (1,))]:
        finite_difference(model, fn, grads, name, position)


def test_regressor_gradient_finite_difference():
    x = np.array([[0.2, 0.5, 1.2], [0.8, 0.3, 0.2]])
    targets = np.array([[.2, -.3], [.4, .7]])
    model = CostRegressor(3, 2, hidden=4, seed=11)
    model.fit_scaler(x)
    loss, grads = model.loss_gradient(x, targets)
    def fn(): return model.loss_gradient(x, targets)[0]
    for name, position in [('w1', (0, 0)), ('b1', (1,)), ('w2', (2, 1)), ('b2', (0,))]:
        finite_difference(model, fn, grads, name, position)


def test_classifier_can_learn_small_separable_problem():
    rng = np.random.default_rng(3)
    x = rng.uniform(0, 1, size=(256, 3))
    labels = (x[:, 0] + x[:, 1] > 1).astype(int)
    targets = np.eye(2)[labels]
    model = Classifier(3, 2, hidden=12, seed=2)
    model.fit_scaler(x)
    opt = Adam(model.params, learning_rate=0.01)
    for _ in range(250):
        loss, grads, _ = model.loss_gradient(x, targets)
        opt.step(model.params, grads)
    assert np.mean(model.predict(x) == labels) > 0.95


def test_regressor_can_learn_small_argmin_problem():
    rng = np.random.default_rng(4)
    x = rng.uniform(0.05, 1, size=(256, 2))
    targets = np.column_stack([x[:, 0], x[:, 1]])
    model = CostRegressor(2, 2, hidden=12, seed=5)
    model.fit_scaler(x)
    opt = Adam(model.params, learning_rate=0.01)
    for _ in range(300):
        loss, grads = model.loss_gradient(x, targets)
        opt.step(model.params, grads)
    assert np.mean(model.predict(x) == targets.argmin(axis=1)) > 0.9


def test_phase2_model_roundtrips(tmp_path):
    x = sample_family(6, 99, 'narrow')
    for cls in (Classifier, CostRegressor):
        model = cls(79, 7, hidden=8, seed=1)
        model.fit_scaler(x)
        path = tmp_path / f'{cls.__name__}.npz'
        model.save(path, {'phase': 2})
        loaded, meta = cls.load(path)
        np.testing.assert_array_equal(model.predict(x), loaded.predict(x))
        assert meta == {'phase': 2}


def test_phase2_training_and_test_sets_are_disjoint():
    config = {
        'train_contexts': 12, 'validation_contexts': 10, 'test_contexts': 11,
        'data_seed_base': 1234,
        'test_families': ['narrow', 'broad_shift', 'ood_edge_hotspot', 'ood_flag_hotspot',
                          'ood_readout_hotspot', 'ood_pauli_sparse']
    }
    arrays = []
    for regime in ('narrow', 'domain_randomized'):
        data = make_datasets(config, regime)
        arrays += [data['train'], data['validation']]
    arrays += list(make_test_sets(config).values())
    sets = [set(row.tobytes() for row in arr) for arr in arrays]
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            assert not sets[i].intersection(sets[j])


def test_context_dependent_oracles_exist_in_phase2_families(catalog):
    for family in ('narrow', 'broad_shift', 'ood_edge_hotspot', 'ood_flag_hotspot', 'ood_pauli_sparse'):
        costs = catalog.costs(sample_family(64, 888, family))
        assert len(set(costs.argmin(axis=1))) > 1

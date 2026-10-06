import numpy as np
import pytest
from qecflag.agent import Policy, Adam, softmax
from qecflag.noise import sample_contexts, validate_context
from qecflag.catalog import greedy_choice
from qecflag.experiment import best_fixed_choice, splits


def test_softmax_stable_and_normalized():
    p = softmax(np.array([[10000., 9999., -10000.], [-10000., -10000., -10000.]]))
    assert np.isfinite(p).all()
    np.testing.assert_allclose(p.sum(axis=1), 1)


def test_reinforce_gradient_finite_difference():
    model = Policy(4, 3, hidden=5, seed=42)
    contexts = np.array([[.2, .3, .5, 1.], [.5, .1, 2., .9]])
    model.fit_scaler(contexts)
    actions = np.array([0, 2])
    advantage = np.array([.7, -.3])
    loss, grads, _ = model.loss_gradient(contexts, actions, advantage, 0.03)
    epsilon = 1e-6
    for name, positions in {'w1': [(0,0), (2,3)], 'b1': [(0,), (3,)],
                            'w2': [(0,0), (4,2)], 'b2': [(0,), (2,)]}.items():
        for position in positions:
            original = model.params[name][position]
            model.params[name][position] = original + epsilon
            hi = model.loss_gradient(contexts, actions, advantage, 0.03)[0]
            model.params[name][position] = original - epsilon
            lo = model.loss_gradient(contexts, actions, advantage, 0.03)[0]
            model.params[name][position] = original
            assert grads[name][position] == pytest.approx((hi-lo)/(2*epsilon), abs=1e-7)


def test_positive_advantage_increases_selected_action_probability():
    model = Policy(4, 3, hidden=5, seed=42)
    w = np.ones((1,4))
    before = model.forward(w)[2][0,1]
    _, gradients, _ = model.loss_gradient(w, np.array([1]), np.array([1.0]), 0.0)
    optimizer = Adam(model.params, learning_rate=0.01)
    optimizer.step(model.params, gradients)
    assert model.forward(w)[2][0,1] > before


def test_policy_checkpoint_roundtrip_without_pickle(tmp_path):
    model = Policy(79, 96, seed=4)
    w = sample_contexts(7, 813)
    model.fit_scaler(w)
    path = tmp_path / 'model.npz'
    model.save(path, {'seed': 4})
    loaded, metadata = Policy.load(path)
    np.testing.assert_array_equal(model.predict(w), loaded.predict(w))
    np.testing.assert_allclose(model.forward(w)[2], loaded.forward(w)[2])
    assert metadata == {'seed': 4}


def test_calibration_generation_reproducible_and_positive():
    a, b = sample_contexts(5, 12), sample_contexts(5, 12)
    np.testing.assert_array_equal(a, b)
    assert np.all(a >= 0)
    assert not np.array_equal(a, sample_contexts(5, 13))


def test_probability_validation_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        validate_context(np.zeros(78))
    with pytest.raises(ValueError):
        validate_context(-np.ones(79))
    with pytest.raises(ValueError):
        validate_context(np.ones(79), p=0.5)


def test_cost_selection_matches_full_matrix(catalog):
    w = sample_contexts(9, 314)
    choices = np.arange(9)
    np.testing.assert_allclose(catalog.chosen_costs(w, choices), catalog.costs(w)[np.arange(9), choices])


def test_oracle_is_lower_bound_and_greedy_obeys_budget(catalog):
    for values in catalog.costs(sample_contexts(12, 589)):
        chosen, used = greedy_choice(catalog, values, budget=16)
        assert used <= 16
        assert values[chosen] >= values.min() - 1e-12
        assert values[chosen] <= values[catalog.reference] + 1e-12


def test_calibration_context_changes_the_best_choice(catalog):
    values = catalog.costs(sample_contexts(32, 441))
    assert len(set(values.argmin(axis=1))) > 1
    best_constant = values.mean(axis=0).argmin()
    assert (values[:, best_constant] - values.min(axis=1)).mean() > 1e-3


def test_train_validation_test_seeds_disjoint():
    config = {'train_contexts': 5, 'validation_contexts': 5, 'test_contexts': 5,
              'data_seeds': {'train': 10, 'validation': 20, 'test': 30, 'shift': 40}}
    data = splits(config)
    observed = [set(row.tobytes() for row in arr) for arr in data.values()]
    for i in range(len(observed)):
        for j in range(i+1,len(observed)):
            assert not observed[i].intersection(observed[j])

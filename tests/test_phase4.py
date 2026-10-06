from pathlib import Path
import numpy as np

from qecflag.phase4_agent import RoundActorCritic, rollout_batch, beam_candidates
from qecflag.phase4_env import RoundFeatureEncoder
from qecflag.phase4_experiment import ProxyEvaluator
from qecflag.phase4_noise import sample_round_contexts, FAMILIES
from qecflag.phase4_physics import (
    CHECKS, simulate_round, verification_summary, round_c2, round_risk,
)
from qecflag.phase4_simulation import simulate
from qecflag.phase4_templates import ensure_action_table
from qecflag.physics import code_tables

ROOT = Path(__file__).resolve().parents[1]


def _table():
    return ensure_action_table(ROOT)


def test_action_table_balanced_and_large_round_space():
    table = _table()
    assert table.n_actions == 48
    assert table.index('0A12A3') is not None
    assert {k: int(np.count_nonzero(table.kinds == k)) for k in set(table.kinds)} == {
        'A_only': 16, 'B_only': 16, 'A_and_B': 16
    }
    assert table.n_actions ** 6 > 10_000_000_000


def test_full_round_no_fault_is_zero_record():
    data, obs = simulate_round(('0A12A3',) * 6)
    assert data == 0
    assert obs == 0


def test_full_round_final_boundary_syndrome_matches_code_table_for_single_incoming_errors():
    _, _, syndromes, _ = code_tables()
    for q in range(7):
        for code in (1, 2, 3):
            error = ((code & 1) << q) | (((code >> 1) & 1) << (7 + q))
            data, obs = simulate_round(('0A12A3',) * 6, incoming_data=error)
            assert data == error
            assert ((obs >> 18) & 63) == int(syndromes[error])


def test_reference_round_has_no_single_fault_or_incoming_failures():
    report = verification_summary(('0A12A3',) * 6)
    assert report['single_fault_conflicts'] == 0
    assert report['single_fault_logical_failures'] == 0
    assert report['single_incoming_error_failures'] == 0
    assert report['malignant_pair_count'] > 0


def test_mixed_certified_round_is_single_fault_correctable():
    table = _table()
    # Deliberately mix all three local architecture kinds.
    a = int(np.flatnonzero(table.kinds == 'A_only')[0])
    b = int(np.flatnonzero(table.kinds == 'B_only')[0])
    ab = int(np.flatnonzero(table.kinds == 'A_and_B')[0])
    labels = (table.labels[a], table.labels[b], table.labels[ab], table.labels[a], table.labels[b], table.labels[ab])
    report = verification_summary(labels)
    assert report['single_fault_conflicts'] == 0
    assert report['single_fault_logical_failures'] == 0


def test_round_c2_scales_quadratically_with_context():
    context = sample_round_contexts(1, 7, 'round_id')[0]
    labels = ('0A12A3',) * 6
    c = round_c2(labels, context)
    c2 = round_c2(labels, 2 * context)
    assert c > 0
    assert np.isclose(c2, 4 * c, rtol=1e-10, atol=1e-10)


def test_all_noise_families_have_valid_shape():
    for i, family in enumerate(FAMILIES):
        x = sample_round_contexts(3, 100 + i, family)
        assert x.shape == (3, 6, 96)
        assert np.isfinite(x).all()
        assert np.all(x >= 0)


def test_flag_ood_families_push_expected_flag_channel():
    a_bad = sample_round_contexts(128, 101, 'ood_flagA_bad')
    b_bad = sample_round_contexts(128, 102, 'ood_flagB_bad')
    # Use preparation weights as a stable summary of the two flag channels.
    assert a_bad[:, :, 1].mean() > a_bad[:, :, 2].mean()
    assert b_bad[:, :, 2].mean() > b_bad[:, :, 1].mean()


def test_feature_encoder_and_rollout_shapes():
    table = _table()
    contexts = sample_round_contexts(5, 123, 'round_train')
    encoder = RoundFeatureEncoder(table)
    encoder.fit(contexts)
    model = RoundActorCritic(encoder.n_features, table.n_actions, hidden=32, seed=1)
    rollout = rollout_batch(model, encoder, contexts, np.random.default_rng(2))
    assert rollout.choices.shape == (5, 6)
    assert rollout.features.shape[0] == 30
    assert rollout.features.shape[1] == encoder.n_features
    assert rollout.actions.shape == (30,)


def test_actor_gradient_is_finite():
    table = _table()
    contexts = sample_round_contexts(4, 124, 'round_train')
    encoder = RoundFeatureEncoder(table); encoder.fit(contexts)
    model = RoundActorCritic(encoder.n_features, table.n_actions, hidden=24, seed=4)
    rollout = rollout_batch(model, encoder, contexts, np.random.default_rng(5))
    returns = np.linspace(-1, 1, len(rollout.actions))
    loss, grads, entropy, value_loss = model.gradient(rollout.features, rollout.actions, returns)
    assert np.isfinite(loss) and np.isfinite(entropy) and np.isfinite(value_loss)
    assert all(np.isfinite(g).all() for g in grads.values())


def test_beam_candidates_are_complete_and_unique():
    table = _table()
    contexts = sample_round_contexts(8, 125, 'round_train')
    encoder = RoundFeatureEncoder(table); encoder.fit(contexts)
    model = RoundActorCritic(encoder.n_features, table.n_actions, hidden=24, seed=5)
    rows = beam_candidates(model, encoder, contexts[0], beam_width=5)
    assert len(rows) == 5
    assert len(set(rows)) == 5
    assert all(len(row) == 6 for row in rows)
    assert all(0 <= a < table.n_actions for row in rows for a in row)


def test_proxy_evaluator_reward_and_greedy_shapes():
    table = _table()
    proxy = ProxyEvaluator.build(ROOT, table)
    contexts = sample_round_contexts(6, 126, 'round_train')
    choices = proxy.local_greedy(contexts)
    rewards = proxy.rewards(contexts, choices)
    assert choices.shape == (6, 6)
    assert rewards.shape == (6,)
    assert np.isfinite(rewards).all()


def test_zero_p_monte_carlo_has_zero_failures():
    context = sample_round_contexts(1, 127, 'round_id')[0]
    result = simulate(('0A12A3',) * 6, context, p=0.0, shots=200, seed=1)
    assert result['failures'] == 0
    assert result['logical_failure_rate'] == 0.0


def test_round_risk_cache_returns_same_object():
    labels = ('0A12A3',) * 6
    assert round_risk(labels) is round_risk(labels)

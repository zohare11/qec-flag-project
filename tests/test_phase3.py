import numpy as np
import pytest

from qecflag.catalog import build_catalog as build_phase1
from qecflag.noise import sample_contexts as sample_phase1_contexts
from qecflag.phase3_physics import (
    FLAG_A, FLAG_B, F3, candidate_schedules, decoder_and_certificate,
    ideal_dense_error, quadratic_features, quadratic_risk_upper_counts,
    schedule_from_label, schedule_label,
)
from qecflag.phase3_catalog import build_catalog
from qecflag.phase3_env import SynthState, valid_action_mask, apply_action, grammar_complete, FeatureEncoder
from qecflag.phase3_agent import ActorCritic, masked_softmax, rollout_batch
from qecflag.phase3_noise import sample_contexts


def test_candidate_counts_and_certified_counts():
    single = build_catalog('single_A')
    assert single.candidate_count == 360
    assert single.certified_count == 96
    expanded = build_catalog('expanded')
    assert expanded.candidate_count == 10800
    assert expanded.certified_count == 4896
    assert np.count_nonzero(expanded.kinds == 'A_only') == 96
    assert np.count_nonzero(expanded.kinds == 'B_only') == 96
    assert np.count_nonzero(expanded.kinds == 'A_and_B') == 4704


def test_phase3_one_flag_matches_phase1_exact_costs():
    old = build_phase1()
    new = build_catalog('single_A')
    assert len(old.labels) == len(new.labels) == 96
    mapping = {label.replace('F', 'A'): i for i, label in enumerate(old.labels)}
    contexts_old = sample_phase1_contexts(8, 1234, 'train')
    contexts_new = np.zeros((8, F3))
    # prep syndrome / flag A
    contexts_new[:, 0] = contexts_old[:, 0]
    contexts_new[:, 1] = contexts_old[:, 1]
    # data edges 0..3
    contexts_new[:, 3:63] = contexts_old[:, 2:62]
    # flag-A edge
    contexts_new[:, 63:78] = contexts_old[:, 62:77]
    # measurements
    contexts_new[:, 93] = contexts_old[:, 77]
    contexts_new[:, 94] = contexts_old[:, 78]
    old_cost = old.costs(contexts_old)
    new_cost = new.all_costs(contexts_new)
    for j, label in enumerate(new.labels):
        i = mapping[label]
        np.testing.assert_allclose(new_cost[:, j], old_cost[:, i], rtol=2e-6, atol=2e-6)


@pytest.mark.parametrize('label', ['0A12A3', 'AB01AB23', 'A0123A', 'B3210B'])
def test_representative_ideal_dense_checks(label):
    schedule = schedule_from_label(label)
    assert ideal_dense_error(schedule) < 1e-12


def test_certification_negative_controls():
    # No flag pair is outside the Phase-3 grammar and known to fail this component certificate.
    from qecflag.physics import decoder_and_certificate as old_certificate
    decoder, report = old_certificate((0, 1, 2, 3))
    assert not report['certified']
    # Odd flag use is rejected at parsing level.
    with pytest.raises(ValueError):
        schedule_from_label('0A123')


def test_grammar_masks_and_completion():
    s = SynthState()
    mask = valid_action_mask(s.prefix, 'expanded')
    assert mask[:6].all() and not mask[6]
    for action in [0, 4, 1, 2, 4, 3]:
        s = apply_action(s, action, 'expanded')
    assert grammar_complete(s.prefix, 'expanded')
    assert valid_action_mask(s.prefix, 'expanded')[6]
    s = apply_action(s, 6, 'expanded')
    assert s.done


def test_masked_softmax_zeroes_invalid_actions():
    logits = np.array([[1., 2., 3.]])
    mask = np.array([[True, False, True]])
    p = masked_softmax(logits, mask)
    assert p[0, 1] == 0
    np.testing.assert_allclose(p.sum(axis=1), 1)


def test_policy_rollout_obeys_grammar():
    contexts = sample_contexts(32, 7, 'synthesis_train')
    encoder = FeatureEncoder(); encoder.fit(contexts)
    model = ActorCritic(encoder.n_features, hidden=24, seed=4)
    rollout = rollout_batch(model, encoder, contexts, 'expanded', np.random.default_rng(5))
    assert rollout.valid.all()
    for label in rollout.labels:
        assert grammar_complete(schedule_from_label(label), 'expanded')


def test_actor_critic_gradient_is_finite():
    contexts = sample_contexts(8, 9, 'single_narrow')
    encoder = FeatureEncoder(); encoder.fit(contexts)
    model = ActorCritic(encoder.n_features, hidden=16, seed=0)
    rollout = rollout_batch(model, encoder, contexts, 'single_A', np.random.default_rng(1))
    returns = np.linspace(0.2, 1.4, len(contexts))[rollout.episode_index]
    loss, grads, entropy, value_loss = model.gradient(rollout.features, rollout.masks, rollout.actions, returns)
    assert np.isfinite(loss) and np.isfinite(entropy) and np.isfinite(value_loss)
    assert all(np.isfinite(g).all() for g in grads.values())


def test_expanded_catalog_has_contexts_where_each_flag_choice_can_be_optimal():
    catalog = build_catalog('expanded')
    observed = set()
    for family in ('ood_flagA_bad', 'ood_flagB_bad', 'ood_both_flags_clean', 'synthesis_id'):
        contexts = sample_contexts(32, 100 + len(family), family)
        costs = catalog.all_costs(contexts)
        observed.update(catalog.kinds[costs.argmin(axis=1)].tolist())
    assert 'A_only' in observed
    assert 'B_only' in observed
    assert 'A_and_B' in observed

import numpy as np
import pytest

from occupancy.households.crest_tpm import (
    MAX_CALIBRATED_SIZE,
    compose_hourly_transition_matrix,
    load_crest_tpm,
    resolve_markov_chain_crest_params,
)


def test_compose_hourly_transition_matrix_on_toy_chain() -> None:
    """Hand-computed toy 2-state chain: each 10-minute period has a fixed
    transition matrix P. Composing six identical P's should equal P**6."""
    p = np.array([[0.9, 0.1], [0.2, 0.8]])
    ten_min = np.tile(p, (144, 1, 1))
    hourly = compose_hourly_transition_matrix(ten_min)

    assert hourly.shape == (24, 2, 2)
    expected_hour = np.linalg.matrix_power(p, 6)
    for h in range(24):
        np.testing.assert_allclose(hourly[h], expected_hour, atol=1e-10)


def test_compose_hourly_transition_matrix_preserves_row_stochastic() -> None:
    rng = np.random.default_rng(0)
    raw = rng.dirichlet(
        np.ones(3), size=(144, 3)
    )  # (144, 3, 3) row-stochastic
    hourly = compose_hourly_transition_matrix(raw)
    assert hourly.shape == (24, 3, 3)
    np.testing.assert_allclose(hourly.sum(axis=-1), 1.0, atol=1e-10)


def test_compose_hourly_transition_matrix_rejects_wrong_period_count() -> None:
    with pytest.raises(ValueError, match="144"):
        compose_hourly_transition_matrix(np.zeros((100, 2, 2)))


@pytest.mark.parametrize("num_persons", [1, 2, 3, 4, 5])
def test_load_crest_tpm_shapes_and_row_sums(num_persons: int) -> None:
    table = load_crest_tpm(num_persons)
    n = num_persons + 1
    assert table.weekday.shape == (24, n, n)
    assert table.weekend.shape == (24, n, n)
    np.testing.assert_allclose(table.weekday.sum(axis=-1), 1.0, atol=1e-6)
    np.testing.assert_allclose(table.weekend.sum(axis=-1), 1.0, atol=1e-6)
    assert (table.weekday >= 0).all()
    assert (table.weekend >= 0).all()


def test_load_crest_tpm_rejects_out_of_range_size() -> None:
    with pytest.raises(ValueError, match="1-5|MAX_CALIBRATED_SIZE|CREST"):
        load_crest_tpm(0)
    with pytest.raises(ValueError, match="1-5|MAX_CALIBRATED_SIZE|CREST"):
        load_crest_tpm(MAX_CALIBRATED_SIZE + 1)


def test_resolve_markov_chain_crest_params_populates_tpms() -> None:
    params = resolve_markov_chain_crest_params(2, {"some_other_key": 1})
    assert params["some_other_key"] == 1
    assert params["tpm_weekday"].shape == (24, 3, 3)
    assert params["tpm_weekend"].shape == (24, 3, 3)


def test_resolve_markov_chain_crest_params_defaults_none_params() -> None:
    params = resolve_markov_chain_crest_params(1, None)
    assert params["tpm_weekday"].shape == (24, 2, 2)

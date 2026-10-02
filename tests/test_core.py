import numpy as np
import pandas as pd
import pytest

from occupancy.core.equipment import (
    EquipmentContext,
    EquipmentSpec,
    _event_probability,
    flat_always_on,
    linear_in_occupants,
    probabilistic_event,
    sessions_per_week,
)
from occupancy.core.occupancy_engine import (
    OccupancyGenerationContext,
    binomial_independent,
    fixed_schedule,
    hourly_occupancy_curve,
    markov_chain,
    markov_chain_crest,
)
from occupancy.households.crest_tpm import resolve_markov_chain_crest_params


def _index(hours: int = 72) -> pd.DatetimeIndex:
    return pd.date_range("2026-01-01", periods=hours, freq="h")


def test_binomial_independent_matches_manual_reimplementation() -> None:
    """Regression guard: the extracted strategy function must reproduce the
    exact same draw sequence as a straightforward reimplementation of the
    original per-row algorithm, under the same seed."""
    index = _index(24 * 3)
    home_probabilities = np.full((24, 2), 0.6)
    active_probabilities = np.full((24, 2), 0.4)
    size = 3

    rng_a = np.random.default_rng(123)
    ctx = OccupancyGenerationContext(
        size=size,
        index=index,
        rng=rng_a,
        home_probabilities=home_probabilities,
        active_probabilities=active_probabilities,
    )
    actual = binomial_independent(ctx)

    rng_b = np.random.default_rng(123)
    expected_present = []
    expected_active = []
    for ts in index:
        weekend_index = 1 if ts.weekday() >= 5 else 0
        p_home = home_probabilities[ts.hour][weekend_index]
        p_active = active_probabilities[ts.hour][weekend_index]
        present = int(rng_b.binomial(size, p_home))
        active = int(rng_b.binomial(present, p_active)) if present else 0
        expected_present.append(present)
        expected_active.append(active)

    assert list(actual["n_present"]) == expected_present
    assert list(actual["n_active"]) == expected_active
    assert (actual["n_active"] <= actual["n_present"]).all()
    assert (
        actual["n_asleep"] <= actual["n_present"] - actual["n_active"]
    ).all()
    assert (
        actual["n_asleep"] == 0
    ).all()  # asleep_probabilities defaults to zero


def test_markov_chain_produces_valid_states_and_persists() -> None:
    index = _index(24 * 7)
    size = 4
    home_probabilities = np.full((24, 2), 0.7)
    active_probabilities = np.full((24, 2), 0.5)

    ctx = OccupancyGenerationContext(
        size=size,
        index=index,
        rng=np.random.default_rng(1),
        home_probabilities=home_probabilities,
        active_probabilities=active_probabilities,
        params={"persistence": 0.95},
    )
    frame = markov_chain(ctx)

    assert (frame["n_active"] >= 0).all()
    assert (frame["n_active"] <= size).all()
    assert (frame["n_present"] >= frame["n_active"]).all()
    assert (frame["n_present"] <= size).all()

    # High persistence -> state should change on a minority of timesteps.
    changes = (frame["n_active"].diff().fillna(0) != 0).mean()
    assert changes < 0.5


def test_markov_chain_crest_produces_valid_states() -> None:
    index = _index(24 * 7)
    size = 3
    home_probabilities = np.full((24, 2), 0.9)
    active_probabilities = np.full((24, 2), 0.5)
    params = resolve_markov_chain_crest_params(size, {})

    ctx = OccupancyGenerationContext(
        size=size,
        index=index,
        rng=np.random.default_rng(1),
        home_probabilities=home_probabilities,
        active_probabilities=active_probabilities,
        params=params,
    )
    frame = markov_chain_crest(ctx)

    assert (frame["n_active"] >= 0).all()
    assert (frame["n_active"] <= size).all()
    assert (frame["n_present"] >= frame["n_active"]).all()
    assert (frame["n_present"] <= size).all()


def test_markov_chain_crest_requires_tpm_params() -> None:
    ctx = OccupancyGenerationContext(
        size=2, index=_index(24), rng=np.random.default_rng(1)
    )
    with pytest.raises(ValueError, match="tpm_weekday"):
        markov_chain_crest(ctx)


def test_markov_chain_crest_rejects_mismatched_tpm_shape() -> None:
    bad_params = {
        "tpm_weekday": np.zeros((24, 5, 5)),  # wrong size for size=2
        "tpm_weekend": np.zeros((24, 5, 5)),
    }
    ctx = OccupancyGenerationContext(
        size=2,
        index=_index(24),
        rng=np.random.default_rng(1),
        params=bad_params,
    )
    with pytest.raises(ValueError, match="shape"):
        markov_chain_crest(ctx)


def test_asleep_probabilities_drive_n_asleep_in_binomial_and_markov() -> None:
    """n_asleep must be drawn from the present-but-inactive share and never
    exceed it, and a near-certain asleep_probabilities should make n_asleep
    track (n_present - n_active) closely."""
    index = _index(24 * 5)
    size = 6
    home_probabilities = np.full((24, 2), 0.95)
    active_probabilities = np.full((24, 2), 0.05)
    asleep_probabilities = np.full((24, 2), 0.99)

    for generator, kwargs in (
        (binomial_independent, {}),
        (markov_chain, {"params": {"persistence": 0.0}}),
    ):
        ctx = OccupancyGenerationContext(
            size=size,
            index=index,
            rng=np.random.default_rng(7),
            home_probabilities=home_probabilities,
            active_probabilities=active_probabilities,
            asleep_probabilities=asleep_probabilities,
            **kwargs,
        )
        frame = generator(ctx)
        inactive_present = frame["n_present"] - frame["n_active"]
        assert (frame["n_asleep"] <= inactive_present).all()
        # asleep_probabilities ~1 -> almost all inactive-present occupants
        # asleep
        nonzero = inactive_present > 0
        if nonzero.any():
            assert (
                frame.loc[nonzero, "n_asleep"] / inactive_present[nonzero]
            ).mean() > 0.9


def test_fixed_schedule_respects_hours_weekends_and_closed_months() -> None:
    index = _index(24 * 40)  # spans into February
    ctx = OccupancyGenerationContext(
        size=10,
        index=index,
        rng=np.random.default_rng(2),
        params={
            "open_hour": 9,
            "close_hour": 17,
            "closed_weekends": True,
            "closed_months": [1],
            "noise": 0.0,
        },
    )
    frame = fixed_schedule(ctx)

    is_weekend = index.weekday >= 5
    is_january = index.month == 1
    closed = is_weekend | is_january
    assert (frame.loc[closed, "n_present"] == 0).all()

    outside_hours = (index.hour < 9) | (index.hour >= 17)
    assert (frame.loc[outside_hours, "n_present"] == 0).all()

    # asleep_probabilities defaults to zero on this ctx -- no sleeping here
    assert (frame["n_asleep"] == 0).all()


def test_hourly_occupancy_curve_follows_explicit_table() -> None:
    index = _index(24 * 3)
    curve = np.zeros((24, 2))
    curve[10] = [1.0, 1.0]  # 10:00 fully occupied, every other hour empty
    ctx = OccupancyGenerationContext(
        size=8,
        index=index,
        rng=np.random.default_rng(3),
        params={"occupancy_fraction": curve, "noise": 0.0},
    )
    frame = hourly_occupancy_curve(ctx)

    at_ten = index.hour == 10
    assert (frame.loc[at_ten, "n_present"] == 8).all()
    assert (frame.loc[~at_ten, "n_present"] == 0).all()


def test_hourly_occupancy_curve_requires_occupancy_fraction_param() -> None:
    ctx = OccupancyGenerationContext(
        size=8, index=_index(24), rng=np.random.default_rng(3)
    )
    with pytest.raises(ValueError, match="occupancy_fraction"):
        hourly_occupancy_curve(ctx)


def test_hourly_occupancy_curve_rejects_wrong_shape() -> None:
    ctx = OccupancyGenerationContext(
        size=8,
        index=_index(24),
        rng=np.random.default_rng(3),
        params={"occupancy_fraction": np.zeros((12, 2))},
    )
    with pytest.raises(ValueError, match="shape"):
        hourly_occupancy_curve(ctx)


def test_hourly_occupancy_curve_asleep_probabilities_drive_n_asleep() -> None:
    """Same contract as the other three generators: n_asleep is drawn from
    the present-but-inactive share via asleep_probabilities -- this is what
    lets a building type like a hotel (which uses this generator) get
    genuine overnight sleeping occupants."""
    index = _index(24 * 5)
    curve = np.full((24, 2), 0.9)
    asleep_probabilities = np.full((24, 2), 0.99)
    ctx = OccupancyGenerationContext(
        size=10,
        index=index,
        rng=np.random.default_rng(11),
        asleep_probabilities=asleep_probabilities,
        params={
            "occupancy_fraction": curve,
            "active_fraction": 0.05,
            "noise": 0.0,
        },
    )
    frame = hourly_occupancy_curve(ctx)
    inactive_present = frame["n_present"] - frame["n_active"]
    assert (frame["n_asleep"] <= inactive_present).all()
    nonzero = inactive_present > 0
    assert (
        frame.loc[nonzero, "n_asleep"] / inactive_present[nonzero]
    ).mean() > 0.9


def test_hourly_occupancy_curve_respects_closed_months() -> None:
    index = _index(24 * 40)  # spans into February
    curve = np.full((24, 2), 0.8)
    ctx = OccupancyGenerationContext(
        size=10,
        index=index,
        rng=np.random.default_rng(4),
        params={
            "occupancy_fraction": curve,
            "closed_months": [1],
            "noise": 0.0,
        },
    )
    frame = hourly_occupancy_curve(ctx)
    is_january = index.month == 1
    assert (frame.loc[is_january, "n_present"] == 0).all()
    assert (frame.loc[~is_january, "n_present"] > 0).any()


def _equipment_context(profile: pd.DataFrame) -> EquipmentContext:
    return EquipmentContext(
        profile=profile,
        rng=np.random.default_rng(0),
        hours=profile.index.hour.to_numpy(),
        is_weekend=profile.index.weekday >= 5,
        weekday_index=profile.index.weekday.to_numpy(),
    )


def _profile(n_present: list[int], n_active: list[int]) -> pd.DataFrame:
    index = _index(len(n_present))
    return pd.DataFrame(
        {"n_present": n_present, "n_active": n_active}, index=index
    )


def test_flat_always_on_is_constant() -> None:
    spec = EquipmentSpec(
        name="fridge", rated_power_kw=0.04, strategy="flat_always_on"
    )
    profile = _profile([0, 1, 2], [0, 0, 1])
    power = flat_always_on(spec, _equipment_context(profile))
    assert (power == 0.04).all()


def test_linear_in_occupants_scales_with_presence_and_weekend_multiplier() -> (
    None
):
    spec = EquipmentSpec(
        name="other",
        rated_power_kw=0.05,
        strategy="linear_in_occupants",
        strategy_params={"weekend_multiplier": 1.2},
    )
    n_present = [2, 3, 0]
    profile = _profile(n_present, [0, 0, 0])
    power = linear_in_occupants(spec, _equipment_context(profile))
    is_weekend = profile.index.weekday >= 5
    expected = np.array(n_present, dtype=float) * 0.05
    expected = np.where(is_weekend, expected * 1.2, expected)
    np.testing.assert_allclose(power, expected)


def test_sessions_per_week_fires_expected_number_of_times() -> None:
    spec = EquipmentSpec(
        name="ironing",
        rated_power_kw=1.0,
        strategy="sessions_per_week",
        strategy_params={"sessions_per_week": 1},
    )
    n = 24 * 7 * 2  # two weeks
    profile = _profile([1] * n, [1] * n)
    power = sessions_per_week(spec, _equipment_context(profile))
    n_sessions = int((power > 0).sum())
    assert n_sessions == 2


def test_probabilistic_event_zero_outside_gate() -> None:
    spec = EquipmentSpec(
        name="cooking",
        rated_power_kw=1.5,
        weekday=np.full(24, 1.0),
        weekend=np.full(24, 1.0),
        strategy="probabilistic_event",
        strategy_params={"gate": "active", "intercept": 1.0},
    )
    profile = _profile([1, 1, 0], [0, 1, 0])
    power = probabilistic_event(spec, _equipment_context(profile))
    assert power[0] == 0.0  # present but inactive -> gated out
    assert power[2] == 0.0  # not present -> gated out


def test_occupant_scaling_defaults_to_no_change() -> None:
    """A spec without ``occupant_scaling`` must behave exactly as it did
    before the parameter existed — same seed, same draws, same power."""
    common = {
        "name": "cooking",
        "rated_power_kw": 1.5,
        "weekday": np.full(24, 1.0),
        "weekend": np.full(24, 1.0),
        "strategy": "probabilistic_event",
    }
    profile = _profile([3, 3, 3], [3, 2, 1])
    without = EquipmentSpec(
        **common, strategy_params={"gate": "active", "intercept": 0.3}
    )
    explicit_zero = EquipmentSpec(
        **common,
        strategy_params={
            "gate": "active",
            "intercept": 0.3,
            "occupant_scaling": 0.0,
        },
    )
    np.testing.assert_allclose(
        probabilistic_event(without, _equipment_context(profile)),
        probabilistic_event(explicit_zero, _equipment_context(profile)),
    )


def test_occupant_scaling_raises_probability_with_headcount() -> None:
    """The whole point of ``occupant_scaling``: firing probability must
    respond to *how many* occupants are active, not only to what share of
    those present are active. ``percent_active`` is 1.0 in every row
    below, so without this parameter all three would be identical."""
    spec = EquipmentSpec(
        name="washing_machine",
        rated_power_kw=0.4,
        weekday=np.full(24, 1.0),
        weekend=np.full(24, 1.0),
        strategy="probabilistic_event",
        strategy_params={
            "gate": "active",
            "intercept": 0.2,
            "occupant_scaling": 1.0,
        },
    )
    profile = _profile([1, 2, 4], [1, 2, 4])
    probability, _ = _event_probability(spec, _equipment_context(profile))
    np.testing.assert_allclose(probability, [0.2, 0.4, 0.8])


def test_occupant_scaling_is_sublinear_below_exponent_one() -> None:
    spec = EquipmentSpec(
        name="hob",
        rated_power_kw=2.4,
        weekday=np.full(24, 1.0),
        weekend=np.full(24, 1.0),
        strategy="probabilistic_event",
        strategy_params={
            "gate": "active",
            "intercept": 0.1,
            "occupant_scaling": 0.5,
        },
    )
    profile = _profile([1, 4, 9], [1, 4, 9])
    probability, _ = _event_probability(spec, _equipment_context(profile))
    np.testing.assert_allclose(probability, [0.1, 0.2, 0.3])


def test_occupant_scaling_leaves_empty_timesteps_gated_out() -> None:
    """The gate mask, not the multiplier, is what zeroes unoccupied hours —
    ``max(count, 1)`` must not resurrect a gated-out timestep."""
    spec = EquipmentSpec(
        name="kettle",
        rated_power_kw=2.0,
        weekday=np.full(24, 1.0),
        weekend=np.full(24, 1.0),
        strategy="probabilistic_event",
        strategy_params={
            "gate": "active",
            "intercept": 1.0,
            "occupant_scaling": 1.0,
        },
    )
    profile = _profile([2, 0, 2], [2, 0, 0])
    power = probabilistic_event(spec, _equipment_context(profile))
    assert power[1] == 0.0  # nobody home
    assert power[2] == 0.0  # present, but nobody active


def test_occupant_scaling_raises_session_count_not_rated_power() -> None:
    spec = EquipmentSpec(
        name="ironing",
        rated_power_kw=1.0,
        strategy="sessions_per_week",
        strategy_params={"sessions_per_week": 1, "occupant_scaling": 1.0},
    )
    n = 24 * 7 * 2  # two weeks
    profile = _profile([4] * n, [4] * n)
    power = sessions_per_week(spec, _equipment_context(profile))
    assert int((power > 0).sum()) == 8  # 2 weeks x 1 session x 4 occupants
    assert set(np.unique(power)) == {0.0, 1.0}  # power itself unchanged

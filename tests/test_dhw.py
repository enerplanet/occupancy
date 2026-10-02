import numpy as np
import pandas as pd
import pytest

from occupancy.households import HouseholdProfile
from occupancy.households.dhw import (
    _cooking_envelope,
    _washing_and_dressing_envelope,
    generate_dhw_draws,
    load_tapping_categories,
    register_timing_envelope,
)


def _hourly_profile(
    hours: int = 24 * 7, n_active: float = 1.0, year: int = 2025
) -> pd.DataFrame:
    index = pd.date_range(f"{year}-01-06", periods=hours, freq="h")  # a Monday
    return pd.DataFrame({"n_active": np.full(hours, n_active)}, index=index)


def _custom_table(**overrides: list) -> pd.DataFrame:
    """A single-row, otherwise-valid tapping-category table for testing
    generate_dhw_draws()'s validation and mechanics in isolation from the
    bundled CSV's real numbers."""
    base = {
        "fixture_label": ["widget"],
        "activity_link": ["cooking"],
        "ownership_probability": [1.0],
        "flow_rate_l_per_min": [1.0],
        "duration_min": [1.0],
        "events_per_day_reference": [1.0],
        "reference_num_persons": [1],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_load_tapping_categories_derives_volume_from_flow_and_duration() -> (
    None
):
    table = load_tapping_categories()
    assert set(table["fixture_label"]) == {
        "basin",
        "kitchen_sink",
        "shower",
        "bath",
    }
    expected_volume = table["flow_rate_l_per_min"] * table["duration_min"]
    np.testing.assert_allclose(
        table["volume_per_event_l"].to_numpy(), expected_volume.to_numpy()
    )


def test_load_tapping_categories_returns_a_fresh_copy() -> None:
    first = load_tapping_categories()
    first.loc[0, "flow_rate_l_per_min"] = -999.0
    second = load_tapping_categories()
    assert second.loc[0, "flow_rate_l_per_min"] != -999.0


def test_generate_dhw_draws_rejects_missing_columns() -> None:
    profile = _hourly_profile()
    with pytest.raises(ValueError, match="missing required column"):
        generate_dhw_draws(
            profile,
            num_persons=1,
            seed=1,
            tapping_categories=pd.DataFrame({"fixture_label": ["a"]}),
        )


def test_generate_dhw_draws_rejects_inconsistent_reference_num_persons() -> (
    None
):
    profile = _hourly_profile()
    bad_table = _custom_table(
        fixture_label=["a", "b"],
        activity_link=["cooking", "cooking"],
        ownership_probability=[1.0, 1.0],
        flow_rate_l_per_min=[1.0, 1.0],
        duration_min=[1.0, 1.0],
        events_per_day_reference=[1.0, 1.0],
        reference_num_persons=[1, 4],
    )
    with pytest.raises(ValueError, match="reference_num_persons"):
        generate_dhw_draws(
            profile, num_persons=1, seed=1, tapping_categories=bad_table
        )


def test_generate_dhw_draws_rejects_out_of_range_ownership() -> None:
    profile = _hourly_profile()
    bad_table = _custom_table(ownership_probability=[1.5])
    with pytest.raises(ValueError, match="ownership_probability"):
        generate_dhw_draws(
            profile, num_persons=1, seed=1, tapping_categories=bad_table
        )


def test_generate_dhw_draws_rejects_non_positive_flow_or_duration() -> None:
    profile = _hourly_profile()
    bad_table = _custom_table(duration_min=[0.0])
    with pytest.raises(
        ValueError, match="flow_rate_l_per_min and duration_min"
    ):
        generate_dhw_draws(
            profile, num_persons=1, seed=1, tapping_categories=bad_table
        )


def test_generate_dhw_draws_columns_and_non_negativity() -> None:
    profile = _hourly_profile()
    result = generate_dhw_draws(profile, num_persons=4, seed=1)

    table = load_tapping_categories()
    expected_columns = {
        f"dhw_liters_{label}" for label in table["fixture_label"]
    } | {"dhw_liters_total"}
    assert set(result.columns) == expected_columns
    assert result.index.equals(profile.index)
    assert (result >= 0).all().all()
    fixture_columns = [c for c in result.columns if c != "dhw_liters_total"]
    np.testing.assert_allclose(
        result[fixture_columns].sum(axis=1).to_numpy(),
        result["dhw_liters_total"].to_numpy(),
    )


def test_generate_dhw_draws_accepts_an_int_seed_or_an_equivalent_generator() -> (
    None
):
    """The two documented explicit forms -- seed=<int> and
    seed=np.random.default_rng(<same int>) -- must produce identical
    output, since both resolve to the same fresh bit-generator state."""
    profile = _hourly_profile()
    from_int = generate_dhw_draws(profile, num_persons=3, seed=42)
    from_generator = generate_dhw_draws(
        profile, num_persons=3, seed=np.random.default_rng(42)
    )
    pd.testing.assert_frame_equal(from_int, from_generator)


def test_generate_dhw_draws_is_deterministic_under_the_same_int_seed() -> None:
    profile = _hourly_profile()
    a = generate_dhw_draws(profile, num_persons=3, seed=42)
    b = generate_dhw_draws(profile, num_persons=3, seed=42)
    pd.testing.assert_frame_equal(a, b)


def test_generate_dhw_draws_default_seed_is_deterministic_but_not_flat() -> (
    None
):
    """seed=None (the default) must reproduce the same result for the same
    inputs, and a different result when an input it hashes (num_persons)
    changes -- exercising derive_default_seed's own contract end to end."""
    profile = _hourly_profile()
    a = generate_dhw_draws(profile, num_persons=2)
    b = generate_dhw_draws(profile, num_persons=2)
    pd.testing.assert_frame_equal(a, b)

    c = generate_dhw_draws(profile, num_persons=5)
    assert not a["dhw_liters_total"].equals(c["dhw_liters_total"])


def test_generate_dhw_draws_respects_ownership_probability() -> None:
    """A category with ownership_probability=0 must never draw, no matter
    how large its reference event rate is."""
    profile = _hourly_profile(hours=24 * 30)
    table = _custom_table(
        ownership_probability=[0.0], events_per_day_reference=[100.0]
    )
    result = generate_dhw_draws(
        profile, num_persons=4, seed=1, tapping_categories=table
    )
    assert (result["dhw_liters_widget"] == 0).all()


def test_generate_dhw_draws_scales_with_num_persons() -> None:
    """Expected volume should scale roughly linearly with num_persons
    relative to the table's own reference_num_persons -- checked over many
    stochastic draws (event count, ownership, and per-event volume are all
    randomized) to average out the noise."""
    profile = _hourly_profile(hours=24 * 30)
    reference_num_persons = int(
        load_tapping_categories()["reference_num_persons"].iloc[0]
    )
    rng = np.random.default_rng(7)

    def mean_total(num_persons: int, trials: int = 80) -> float:
        totals = [
            generate_dhw_draws(profile, num_persons=num_persons, seed=rng)[
                "dhw_liters_total"
            ].sum()
            for _ in range(trials)
        ]
        return float(np.mean(totals))

    one_ref = mean_total(reference_num_persons)
    two_ref = mean_total(reference_num_persons * 2)
    assert two_ref == pytest.approx(2 * one_ref, rel=0.2)


def test_cooking_linked_category_follows_cooking_active_timing() -> None:
    """kitchen_sink's activity_link is "cooking" and it's always owned
    (ownership_probability=1.0 in the bundled table) -- with cooking_active
    True at exactly one hour, every kitchen-sink draw must land there."""
    profile = _hourly_profile(hours=24 * 14)
    cooking_active = pd.Series(False, index=profile.index)
    cooking_active.iloc[10] = True

    result = generate_dhw_draws(
        profile, num_persons=6, cooking_active=cooking_active, seed=3
    )

    kitchen_sink = result["dhw_liters_kitchen_sink"]
    assert kitchen_sink.sum() > 0  # some draws actually happened
    assert (kitchen_sink[kitchen_sink.index != profile.index[10]] == 0).all()


def test_cooking_envelope_prefers_the_supplied_cooking_active_signal() -> None:
    n_active = np.array([1.0, 1.0])
    cooking = np.array([0.0, 5.0])
    np.testing.assert_array_equal(
        _cooking_envelope(n_active, cooking), cooking
    )
    np.testing.assert_array_equal(_cooking_envelope(n_active, None), n_active)


def test_washing_and_dressing_envelope_favors_the_wake_transition() -> None:
    """The hour a household transitions into active occupancy should
    outweigh both a flat sustained-active hour and the hour occupancy
    drops back to zero -- not a uniform n_active average."""
    n_active = np.array([0.0, 0.0, 0.0, 3.0, 3.0, 3.0, 3.0, 0.0, 0.0, 0.0])
    weights = _washing_and_dressing_envelope(n_active, None)

    wake_hour = 3
    sustained_hour = 5
    assert weights[wake_hour] == weights.max()
    assert weights[wake_hour] > weights[sustained_hour]
    # every weight is at least the plain n_active baseline
    assert (weights >= n_active).all()


def test_register_timing_envelope_is_used_for_a_custom_activity_link() -> None:
    profile = _hourly_profile(hours=24 * 7)
    invoked = []

    def spy_envelope(
        n_active: np.ndarray, cooking_signal: object
    ) -> np.ndarray:
        invoked.append(True)
        return np.ones_like(n_active)

    register_timing_envelope("test_custom_activity", spy_envelope)
    table = _custom_table(
        activity_link=["test_custom_activity"], events_per_day_reference=[5.0]
    )
    generate_dhw_draws(
        profile, num_persons=1, seed=1, tapping_categories=table
    )
    assert invoked


def test_generate_dhw_draws_accepts_a_custom_tapping_table() -> None:
    profile = _hourly_profile()
    custom = _custom_table(
        fixture_label=["outdoor_tap"],
        activity_link=["washing_and_dressing"],
        flow_rate_l_per_min=[10.0],
        duration_min=[2.0],
    )
    result = generate_dhw_draws(
        profile, num_persons=1, seed=1, tapping_categories=custom
    )
    assert set(result.columns) == {
        "dhw_liters_outdoor_tap",
        "dhw_liters_total",
    }


def test_generate_dhw_draws_rejects_bad_num_persons_or_profile_length() -> (
    None
):
    profile = _hourly_profile()

    with pytest.raises(ValueError, match="num_persons"):
        generate_dhw_draws(profile, num_persons=0, seed=1)

    with pytest.raises(ValueError, match="whole number of days"):
        generate_dhw_draws(profile.iloc[:-1], num_persons=3, seed=1)


def test_generate_dhw_draws_works_against_a_real_household_profile() -> None:
    """End-to-end smoke test against HouseholdProfile.get_profile()'s real
    n_active output. Deliberately does *not* touch the private
    household._rng attribute -- passing the household's own public
    .seed is the documented, supported way to tie a household to its DHW
    draws (see generate_dhw_draws()'s own seed= docstring)."""
    household = HouseholdProfile(num_persons=3, year=2025, seed=1)
    profile = household.get_profile()
    result = generate_dhw_draws(
        profile, num_persons=household.num_persons, seed=household.seed
    )
    assert len(result) == len(profile)
    assert result["dhw_liters_total"].sum() > 0

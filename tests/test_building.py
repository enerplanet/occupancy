import pytest

from occupancy.households.building import (
    DEFAULT_DWELLING_CAP,
    MultiDwellingProfile,
    _dwelling_household_sizes,
)


def test_dwelling_household_sizes_bracket_the_mean() -> None:
    sizes = _dwelling_household_sizes(10, 2.3)
    assert set(sizes) <= {2, 3}
    assert sizes.count(3) == 3
    assert sizes.count(2) == 7


def test_dwelling_household_sizes_integer_mean_is_uniform() -> None:
    sizes = _dwelling_household_sizes(5, 3.0)
    assert sizes == [3, 3, 3, 3, 3]


def test_rejects_non_positive_inputs() -> None:
    with pytest.raises(ValueError):
        MultiDwellingProfile(dwellings=0, mean_num_persons=2, year=2018)
    with pytest.raises(ValueError):
        MultiDwellingProfile(dwellings=5, mean_num_persons=0, year=2018)
    with pytest.raises(ValueError):
        MultiDwellingProfile(dwellings=5, mean_num_persons=2, year=2018, cap=0)


def test_dwelling_count_is_capped() -> None:
    building = MultiDwellingProfile(
        dwellings=200, mean_num_persons=2, year=2018, cap=20
    )
    assert building.n_households == 20
    assert building.scale == 10.0


def test_single_dwelling_scale_is_one() -> None:
    building = MultiDwellingProfile(dwellings=1, mean_num_persons=2, year=2018)
    assert building.n_households == 1
    assert building.scale == 1.0


def test_households_are_distinct_and_seeded_from_building_seed() -> None:
    building = MultiDwellingProfile(
        dwellings=5, mean_num_persons=2.5, year=2018, seed=42
    )
    households = building.get_households()
    assert len(households) == 5
    seeds = {hh.seed for hh in households}
    assert len(seeds) == 5  # every dwelling gets its own seed


def test_same_seed_is_deterministic() -> None:
    a = MultiDwellingProfile(
        dwellings=10, mean_num_persons=2.3, year=2018, seed=7
    )
    b = MultiDwellingProfile(
        dwellings=10, mean_num_persons=2.3, year=2018, seed=7
    )
    pa, pb = a.get_profile(), b.get_profile()
    assert pa["total_power_kwh"].equals(pb["total_power_kwh"])


def test_summed_households_diversify_peak_more_than_scaled_single() -> None:
    """The whole point of issue #14: summing N distinct households peaks
    lower relative to its mean than copying one household N times."""
    scaled_single = MultiDwellingProfile(
        dwellings=20, mean_num_persons=2.3, year=2018, seed=1, cap=1
    )
    diversified = MultiDwellingProfile(
        dwellings=20, mean_num_persons=2.3, year=2018, seed=1, cap=20
    )

    single_power = scaled_single.get_profile()["total_power_kwh"]
    diversified_power = diversified.get_profile()["total_power_kwh"]

    single_ratio = single_power.max() / single_power.mean()
    diversified_ratio = diversified_power.max() / diversified_power.mean()

    assert diversified_ratio < single_ratio


def test_profile_has_expected_columns() -> None:
    building = MultiDwellingProfile(
        dwellings=5, mean_num_persons=2, year=2018, seed=1
    )
    profile = building.get_profile()
    for column in (
        "n_present",
        "n_active",
        "n_asleep",
        "total_power_kwh",
        "cooking_active",
    ):
        assert column in profile.columns
    assert "dhw_liters_total" not in profile.columns


def test_include_dhw_adds_dhw_column() -> None:
    building = MultiDwellingProfile(
        dwellings=5, mean_num_persons=2, year=2018, seed=1, include_dhw=True
    )
    profile = building.get_profile()
    assert "dhw_liters_total" in profile.columns
    assert (profile["dhw_liters_total"] >= 0).all()


def test_to_result_num_persons_is_building_total() -> None:
    building = MultiDwellingProfile(
        dwellings=10, mean_num_persons=2.5, year=2018, seed=1
    )
    result = building.to_result()
    assert result.num_persons == 25
    assert result.building_type == "household"


def test_default_cap_is_twenty() -> None:
    assert DEFAULT_DWELLING_CAP == 20

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from occupancy.core.buem_adapter import to_buem_profiles
from occupancy.households import (
    ElectricityConsumptionProfile,
    HouseholdProfile,
)
from occupancy.services_buildings import ServiceBuildingProfile

_EXPECTED_KEYS = {"Q_ig", "elecLoad", "occ_nothome", "occ_sleeping"}
# `cooking_active` is included whenever `result.profile` carries the
# column -- i.e. whenever equipment was generated at all (any building/
# household without a "kitchen"-category item still gets an all-False
# column, not an absent one -- see ElectricityConsumptionProfile.generate/
# ServiceBuildingProfile.generate).
_EXPECTED_KEYS_WITH_EQUIPMENT = _EXPECTED_KEYS | {"cooking_active"}


def test_service_building_result_converts_directly() -> None:
    result = ServiceBuildingProfile(
        building_type="office", year=2025, seed=1
    ).to_result()
    buem_profiles = to_buem_profiles(result)

    assert set(buem_profiles) == _EXPECTED_KEYS_WITH_EQUIPMENT
    for series in buem_profiles.values():
        assert len(series) == len(result.profile)
        assert series.index.equals(result.profile.index)

    assert (buem_profiles["Q_ig"] >= 0).all()
    assert (buem_profiles["elecLoad"] >= 0).all()
    assert (buem_profiles["occ_nothome"] >= 0).all()
    assert (buem_profiles["occ_nothome"] <= 1).all()
    # office never sets asleep_probabilities -- unlike hotel (see
    # test_hotel_result_produces_genuine_occ_sleeping below), so no
    # sleeping occupants here regardless of hour
    assert (buem_profiles["occ_sleeping"] == 0).all()


def test_hotel_result_produces_genuine_occ_sleeping() -> None:
    """A service-building type CAN sleep -- occ_sleeping must reflect real
    n_asleep output for any building_type, not just households."""
    result = ServiceBuildingProfile(
        building_type="hotel", year=2025, seed=1
    ).to_result()
    buem_profiles = to_buem_profiles(result)

    assert (buem_profiles["occ_sleeping"] > 0).any()
    expected_sleeping = result.profile["n_asleep"] / result.num_persons
    np.testing.assert_allclose(
        buem_profiles["occ_sleeping"].to_numpy(), expected_sleeping.to_numpy()
    )


def test_household_result_needs_equipment_wrapper() -> None:
    bare = HouseholdProfile(num_persons=3, year=2025, seed=1).to_result()
    with pytest.raises(ValueError, match="total_power_kwh"):
        to_buem_profiles(bare)

    household = HouseholdProfile(num_persons=3, year=2025, seed=1)
    with_equipment = ElectricityConsumptionProfile(
        occupancy_profile=household, seed=1
    ).to_result()
    buem_profiles = to_buem_profiles(with_equipment)

    assert set(buem_profiles) == _EXPECTED_KEYS_WITH_EQUIPMENT
    # occ_sleeping is real generator output (n_asleep / num_persons), not a
    # heuristic, whenever the profile carries an n_asleep column.
    expected_sleeping = (
        with_equipment.profile["n_asleep"] / with_equipment.num_persons
    )
    np.testing.assert_allclose(
        buem_profiles["occ_sleeping"].to_numpy(), expected_sleeping.to_numpy()
    )
    assert (buem_profiles["occ_sleeping"] >= 0).all()
    assert (buem_profiles["occ_sleeping"] <= 1).all()


def test_sleep_window_only_applies_as_fallback_without_n_asleep_column() -> (
    None
):
    household = HouseholdProfile(num_persons=2, year=2025, seed=2)
    result = ElectricityConsumptionProfile(
        occupancy_profile=household, seed=2
    ).to_result()

    # n_asleep present -> real model output used, sleep_window is ignored.
    with_column = to_buem_profiles(result, sleep_window=None)
    default_window = to_buem_profiles(result)
    np.testing.assert_allclose(
        with_column["occ_sleeping"].to_numpy(),
        default_window["occ_sleeping"].to_numpy(),
    )

    # Simulate an older/hand-built profile lacking n_asleep -> heuristic
    # fallback kicks in, and sleep_window now actually controls the output.
    legacy_profile = result.profile.drop(columns=["n_asleep"])
    legacy_result = replace(result, profile=legacy_profile)

    heuristic_on = to_buem_profiles(legacy_result)
    hours = legacy_profile.index.hour
    is_night = (hours >= 23) | (hours < 7)
    assert (heuristic_on["occ_sleeping"][~is_night] == 0).all()

    heuristic_off = to_buem_profiles(legacy_result, sleep_window=None)
    assert (heuristic_off["occ_sleeping"] == 0).all()


def test_heat_gain_scales_with_active_vs_inactive_occupants() -> None:
    result = ServiceBuildingProfile(
        building_type="supermarket", year=2025, seed=3
    ).to_result()
    buem_profiles = to_buem_profiles(result)

    n_present = result.profile["n_present"].to_numpy(dtype=float)
    n_active = result.profile["n_active"].to_numpy(dtype=float)
    expected_q_ig = (
        n_present - n_active
    ) * result.heat_gain_present_kw + n_active * result.heat_gain_active_kw
    np.testing.assert_allclose(buem_profiles["Q_ig"].to_numpy(), expected_q_ig)


def test_explicit_gain_kwargs_override_per_type_value() -> None:
    result = ServiceBuildingProfile(
        building_type="supermarket", year=2025, seed=3
    ).to_result()
    buem_profiles = to_buem_profiles(
        result, gain_present_kw=0.5, gain_active_kw=0.5
    )

    n_present = result.profile["n_present"].to_numpy(dtype=float)
    np.testing.assert_allclose(
        buem_profiles["Q_ig"].to_numpy(), n_present * 0.5
    )


def test_floor_area_blends_with_not_replaces_occupant_gains() -> None:
    result = ServiceBuildingProfile(
        building_type="office", year=2025, seed=3
    ).to_result()
    baseline = to_buem_profiles(result)
    with_area = to_buem_profiles(result, floor_area_m2=500.0)

    n_present = result.profile["n_present"].to_numpy(dtype=float)
    presence_fraction = np.clip(n_present / result.num_persons, 0.0, 1.0)
    expected_area_gain = (
        result.gain_w_per_m2 * 500.0 / 1000.0
    ) * presence_fraction

    np.testing.assert_allclose(
        with_area["Q_ig"].to_numpy(),
        baseline["Q_ig"].to_numpy() + expected_area_gain,
    )
    # Never empty of an occupant-driven term -- area component is additive.
    assert (with_area["Q_ig"] >= baseline["Q_ig"]).all()
    # Zero occupant presence -> zero area contribution too (scaled by
    # presence_fraction, not a flat 24/7 term).
    closed_hours = n_present == 0
    if closed_hours.any():
        np.testing.assert_allclose(
            with_area["Q_ig"].to_numpy()[closed_hours],
            baseline["Q_ig"].to_numpy()[closed_hours],
        )


def test_gain_w_per_m2_kwarg_overrides_per_type_value() -> None:
    result = ServiceBuildingProfile(
        building_type="office", year=2025, seed=3
    ).to_result()
    overridden = to_buem_profiles(
        result, floor_area_m2=200.0, gain_w_per_m2=100.0
    )
    default = to_buem_profiles(result, floor_area_m2=200.0)
    assert (overridden["Q_ig"] >= default["Q_ig"]).all()
    assert (overridden["Q_ig"] > default["Q_ig"]).any()


def test_floor_area_without_gain_w_per_m2_raises() -> None:
    household = HouseholdProfile(num_persons=2, year=2025, seed=1)
    result = ElectricityConsumptionProfile(
        occupancy_profile=household, seed=1
    ).to_result()
    assert result.gain_w_per_m2 is None  # households leave it unset today
    with pytest.raises(ValueError, match="gain_w_per_m2"):
        to_buem_profiles(result, floor_area_m2=100.0)


def test_elec_load_kwarg_bypasses_total_power_kwh_requirement() -> None:
    household = HouseholdProfile(num_persons=3, year=2025, seed=1)
    bare = household.to_result()  # no total_power_kwh column
    assert "total_power_kwh" not in bare.profile.columns

    external_load = pd.Series(0.42, index=bare.profile.index)
    buem_profiles = to_buem_profiles(bare, elec_load=external_load)

    assert set(buem_profiles) == _EXPECTED_KEYS
    np.testing.assert_allclose(
        buem_profiles["elecLoad"].to_numpy(), external_load.to_numpy()
    )
    # Q_ig/occ_nothome/occ_sleeping still come from occupancy's own
    # generated presence pattern, unaffected by the external elecLoad.
    n_present = bare.profile["n_present"].to_numpy(dtype=float)
    expected_occ_nothome = 1.0 - np.clip(
        n_present / bare.num_persons, 0.0, 1.0
    )
    np.testing.assert_allclose(
        buem_profiles["occ_nothome"].to_numpy(), expected_occ_nothome
    )


def test_elec_load_misaligned_index_raises() -> None:
    household = HouseholdProfile(num_persons=2, year=2025, seed=1)
    bare = household.to_result()
    short_load = pd.Series(0.1, index=bare.profile.index[:10])
    with pytest.raises(ValueError, match="elec_load"):
        to_buem_profiles(bare, elec_load=short_load)


def test_rejects_zero_num_persons() -> None:
    household = HouseholdProfile(num_persons=1, year=2025, seed=1)
    result = ElectricityConsumptionProfile(
        occupancy_profile=household, seed=1
    ).to_result()
    result.num_persons = 0
    with pytest.raises(ValueError, match="num_persons"):
        to_buem_profiles(result)

import numpy as np
import pandas as pd
import pytest

from occupancy.core.disaggregation import estimate_equipment_usage
from occupancy.core.equipment import (
    EquipmentContext,
    EquipmentSpec,
    expected_probabilistic_event,
    expected_sessions_per_week,
    generate_equipment_power,
    probabilistic_event,
    sessions_per_week,
)
from occupancy.households.electricity import ElectricityConsumptionProfile
from occupancy.households.household_profile import HouseholdProfile


def _index(hours: int) -> pd.DatetimeIndex:
    return pd.date_range("2026-01-01", periods=hours, freq="h")


def _profile(n_present: list[int], n_active: list[int]) -> pd.DataFrame:
    index = _index(len(n_present))
    return pd.DataFrame(
        {"n_present": n_present, "n_active": n_active}, index=index
    )


def _equipment_context(
    profile: pd.DataFrame, seed: int = 0
) -> EquipmentContext:
    return EquipmentContext(
        profile=profile,
        rng=np.random.default_rng(seed),
        hours=profile.index.hour.to_numpy(),
        is_weekend=profile.index.weekday >= 5,
        weekday_index=profile.index.weekday.to_numpy(),
    )


def test_expected_probabilistic_event_matches_monte_carlo_mean() -> None:
    spec = EquipmentSpec(
        name="cooking",
        rated_power_kw=1.5,
        standby_power_kw=0.01,
        weekday=np.full(24, 1.0),
        weekend=np.full(24, 1.0),
        strategy="probabilistic_event",
        strategy_params={"gate": "active", "intercept": 0.3},
    )
    profile = _profile([1] * 48, [1] * 48)
    expected = expected_probabilistic_event(spec, _equipment_context(profile))

    draws = np.stack(
        [
            probabilistic_event(spec, _equipment_context(profile, seed=s))
            for s in range(2000)
        ]
    )
    monte_carlo_mean = draws.mean(axis=0)
    np.testing.assert_allclose(monte_carlo_mean, expected, atol=0.05)


def test_expected_sessions_per_week_matches_monte_carlo_mean() -> None:
    spec = EquipmentSpec(
        name="ironing",
        rated_power_kw=1.0,
        strategy="sessions_per_week",
        strategy_params={"sessions_per_week": 2},
    )
    n = 24 * 7 * 2  # two weeks
    profile = _profile([1] * n, [1] * n)
    expected = expected_sessions_per_week(spec, _equipment_context(profile))

    draws = np.stack(
        [
            sessions_per_week(spec, _equipment_context(profile, seed=s))
            for s in range(500)
        ]
    )
    monte_carlo_mean = draws.mean(axis=0)
    np.testing.assert_allclose(monte_carlo_mean, expected, atol=0.05)


def test_estimate_equipment_usage_recovers_known_coefficients() -> None:
    """Deterministic-strategy-only ground truth (no RNG involved on either
    side), so recovery should be near-exact."""
    n_present = [0, 1, 2, 3, 1, 0, 2, 3] * 20
    profile = _profile(n_present, n_present)

    ground_truth = {
        "fridge": EquipmentSpec(
            name="fridge", rated_power_kw=0.5, strategy="flat_always_on"
        ),
        "plug_loads": EquipmentSpec(
            name="plug_loads",
            rated_power_kw=0.2,
            strategy="linear_in_occupants",
        ),
    }
    elec_load = generate_equipment_power(
        list(ground_truth.values()), profile, np.random.default_rng(0)
    ).rename("elecLoad")

    unit_table = {
        "fridge": EquipmentSpec(
            name="fridge", rated_power_kw=1.0, strategy="flat_always_on"
        ),
        "plug_loads": EquipmentSpec(
            name="plug_loads",
            rated_power_kw=1.0,
            strategy="linear_in_occupants",
        ),
        "unused_item": EquipmentSpec(
            name="unused_item", rated_power_kw=1.0, strategy="flat_always_on"
        ),
    }

    fitted = estimate_equipment_usage(elec_load, profile, unit_table)

    assert fitted["fridge"].rated_power_kw == pytest.approx(0.5, abs=1e-6)
    assert fitted["plug_loads"].rated_power_kw == pytest.approx(0.2, abs=1e-6)
    assert fitted["fridge"].ownership_probability == 1.0
    # unused_item's fitted coefficient must land at/near zero and be dropped.
    assert "unused_item" not in fitted


def test_estimate_equipment_usage_rejects_misaligned_elec_load() -> None:
    profile = _profile([1, 1, 1], [1, 1, 1])
    misaligned = pd.Series(
        [1.0, 1.0, 1.0], index=_index(3) + pd.Timedelta(days=5)
    )
    table = {
        "fridge": EquipmentSpec(
            name="fridge", rated_power_kw=1.0, strategy="flat_always_on"
        )
    }
    with pytest.raises(ValueError, match="does not cover"):
        estimate_equipment_usage(misaligned, profile, table)


def test_estimate_equipment_usage_collinear_items_sum_correctly() -> None:
    """Two items with identical templates can't be individually identified
    -- only their coefficient sum should be reliable."""
    n = 100
    profile = _profile([1] * n, [1] * n)
    true_total = 0.6
    elec_load = pd.Series(
        np.full(n, true_total), index=profile.index, name="elecLoad"
    )
    table = {
        "dup1": EquipmentSpec(
            name="dup1", rated_power_kw=1.0, strategy="flat_always_on"
        ),
        "dup2": EquipmentSpec(
            name="dup2", rated_power_kw=1.0, strategy="flat_always_on"
        ),
    }
    fitted = estimate_equipment_usage(elec_load, profile, table)
    total = sum(spec.rated_power_kw for spec in fitted.values())
    assert total == pytest.approx(true_total, abs=1e-6)


def test_estimate_equipment_usage_regularization_pulls_toward_priors() -> None:
    n = 100
    profile = _profile([1] * n, [1] * n)
    elec_load = pd.Series(
        np.full(n, 0.5), index=profile.index, name="elecLoad"
    )
    table = {
        "dup1": EquipmentSpec(
            name="dup1",
            rated_power_kw=1.0,
            strategy="flat_always_on",
            ownership_probability=0.9,
        ),
        "dup2": EquipmentSpec(
            name="dup2",
            rated_power_kw=1.0,
            strategy="flat_always_on",
            ownership_probability=0.1,
        ),
    }
    fitted = estimate_equipment_usage(
        elec_load, profile, table, regularization=1e4
    )
    # With overwhelming regularization, the fit collapses onto the priors
    # themselves rather than an arbitrary split of the observed total.
    assert fitted["dup1"].rated_power_kw == pytest.approx(0.9, abs=1e-2)
    assert fitted["dup2"].rated_power_kw == pytest.approx(0.1, abs=1e-2)


def test_estimate_equipment_usage_feeds_back_into_electricity_profile() -> (
    None
):
    household = HouseholdProfile(num_persons=3, year=2025, seed=1)
    base_elec = ElectricityConsumptionProfile(household, seed=1)
    base_table = base_elec.get_equipment_table()
    profile = household.get_profile()

    fake_elec_load = base_elec.generate()["total_power_kwh"].rename("elecLoad")

    fitted = estimate_equipment_usage(
        fake_elec_load, profile, base_table, regularization=0.01
    )
    assert fitted  # at least some items survive

    result_profile = ElectricityConsumptionProfile(
        household, equipment=fitted, seed=1
    ).generate()
    assert (result_profile["total_power_kwh"] >= 0).all()

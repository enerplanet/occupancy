"""equipment_table applies a {equipment_id: bool} selector to a
household's archetype-adjusted equipment table."""

import numpy as np
import pytest

from occupancy import (
    EQUIPMENT_TYPES,
    ElectricityConsumptionProfile,
    HouseholdProfile,
)
from occupancy.demand import equipment_table

_IDS = frozenset(EQUIPMENT_TYPES)


def _household(archetype="generic", seed=42):
    return HouseholdProfile(
        num_persons=4, year=2018, seed=seed, archetype=archetype
    )


def _specs_equal(a, b) -> bool:
    """Value equality for EquipmentSpec: its array fields break plain
    dataclass equality, and archetype overrides rebuild fresh objects so
    identity does not hold even when the values do."""
    if a is b:
        return True
    return (
        a.name == b.name
        and a.category == b.category
        and a.rated_power_kw == b.rated_power_kw
        and a.standby_power_kw == b.standby_power_kw
        and a.ownership_probability == b.ownership_probability
        and a.strategy == b.strategy
        and a.strategy_params == b.strategy_params
        and a.enabled == b.enabled
        and np.array_equal(a.weekday, b.weekday)
        and np.array_equal(a.weekend, b.weekend)
    )


def test_none_when_no_selector() -> None:
    household = _household()
    assert equipment_table(household, 42, None) is None
    assert equipment_table(household, 42, {}) is None


def test_true_forces_full_ownership_probability() -> None:
    household = _household()
    table = equipment_table(household, 42, {"oven": True})
    assert table["oven"].ownership_probability == 1.0
    base = ElectricityConsumptionProfile(
        household, seed=42
    ).get_equipment_table()
    for key in _IDS - {"oven"}:
        assert _specs_equal(table[key], base[key])


def test_false_omits_item_entirely() -> None:
    household = _household()
    table = equipment_table(household, 42, {"oven": False})
    assert "oven" not in table
    base = ElectricityConsumptionProfile(
        household, seed=42
    ).get_equipment_table()
    for key in _IDS - {"oven"}:
        assert _specs_equal(table[key], base[key])


def test_preserves_archetype_overrides() -> None:
    household = _household(archetype="student_shared")
    table = equipment_table(household, 42, {"oven": True})
    base = ElectricityConsumptionProfile(
        household, seed=42
    ).get_equipment_table()
    for key in _IDS - {"oven"}:
        assert _specs_equal(table[key], base[key])


def test_unknown_id_raises() -> None:
    with pytest.raises(ValueError, match="unrecognized id"):
        equipment_table(_household(), 42, {"not_a_real_appliance": True})


def test_non_bool_value_raises() -> None:
    with pytest.raises(ValueError, match="must be true/false"):
        equipment_table(_household(), 42, {"oven": "yes"})


def test_non_dict_raises() -> None:
    with pytest.raises(ValueError, match="must be a dict"):
        equipment_table(_household(), 42, ["oven"])

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import numpy as np

from occupancy.core.equipment import EquipmentSpec, normalize_equipment_table

_DEFAULT_SCENARIO_PATH = files("occupancy.config").joinpath(
    "data/default_scenario.json"
)


def _normalize_probability_array(value: Any) -> np.ndarray | None:
    if value is None:
        return None
    array = np.asarray(value, dtype=float)
    if array.shape != (24, 2):
        raise ValueError("probability arrays must have shape (24, 2)")
    return array


@dataclass(frozen=True)
class ScenarioConfig:
    """CLI-facing scenario configuration.

    ``num_persons`` doubles as the household occupant count or the service-
    building capacity, depending on ``building_type``. Any field left at its
    default is resolved from the selected household archetype / service
    building type at profile-construction time -- this config only carries
    *overrides*, it doesn't duplicate their defaults.
    """

    year: int
    num_persons: int
    seed: int | None = None
    include_electricity: bool = False
    output: Path = Path("outputs/occupancy_profile.csv")
    building_type: str = "household"
    archetype: str = "generic"
    region: str = "NL"
    has_cooking: bool = True
    has_tv: bool = True
    has_laundry: bool = True
    has_cleaning: bool = True
    has_ironing: bool = True
    has_fridge: bool = True
    has_other: bool = True
    has_lighting: bool = True
    home_probabilities: np.ndarray | None = None
    active_probabilities: np.ndarray | None = None
    equipment: dict[str, EquipmentSpec] | None = None

    @classmethod
    def default(cls) -> ScenarioConfig:
        return load_scenario_config()

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> ScenarioConfig:
        if not mapping:
            return cls.default()

        scenario = mapping.get("scenario", mapping)
        occupancy = mapping.get("occupancy", {})
        electricity = mapping.get("electricity", {})

        equipment_data = electricity.get("equipment")
        equipment = (
            normalize_equipment_table(equipment_data)
            if equipment_data is not None
            else None
        )

        return cls(
            year=int(scenario["year"]),
            num_persons=int(scenario["num_persons"]),
            seed=scenario.get("seed"),
            include_electricity=bool(
                scenario.get("include_electricity", False)
            ),
            output=Path(
                scenario.get("output", "outputs/occupancy_profile.csv")
            ),
            building_type=scenario.get("building_type", "household"),
            archetype=scenario.get("archetype", "generic"),
            region=scenario.get("region", "NL"),
            has_cooking=bool(scenario.get("has_cooking", True)),
            has_tv=bool(scenario.get("has_tv", True)),
            has_laundry=bool(scenario.get("has_laundry", True)),
            has_cleaning=bool(scenario.get("has_cleaning", True)),
            has_ironing=bool(scenario.get("has_ironing", True)),
            has_fridge=bool(scenario.get("has_fridge", True)),
            has_other=bool(scenario.get("has_other", True)),
            has_lighting=bool(scenario.get("has_lighting", True)),
            home_probabilities=_normalize_probability_array(
                occupancy.get("home_probabilities"),
            ),
            active_probabilities=_normalize_probability_array(
                occupancy.get("active_probabilities"),
            ),
            equipment=equipment,
        )


def load_scenario_config(path: str | Path | None = None) -> ScenarioConfig:
    target = _DEFAULT_SCENARIO_PATH if path is None else Path(path)
    with target.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return ScenarioConfig.from_mapping(data)

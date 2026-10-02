"""Service-building type registry.

Each type is defined by two config files under ``data/<type_id>/``:
``schedule.json`` (occupancy generator + params) and ``equipment.json``
(the type's :class:`~occupancy.core.equipment.EquipmentSpec` rows). Loading
is triggered by each type's thin module (``supermarket.py``, ``office.py``,
...) calling :func:`load_building_type` — importing ``services_buildings``
loads every type in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from occupancy.core.equipment import EquipmentSpec, normalize_equipment_table
from occupancy.core.loader import load_json_resource

_PACKAGE = "occupancy.services_buildings"


@dataclass(frozen=True)
class ServiceBuildingTypeSpec:
    """One service-building activity type."""

    id: str
    description: str
    region: str
    capacity_default: int
    generator: str
    generator_params: dict[str, Any]
    equipment: dict[str, EquipmentSpec] = field(default_factory=dict)
    # Heat gain per occupant [kW], building-total (see
    # `core/buem_adapter.py` module docstring for units/rationale/sources).
    # Defaults match that module's own fallback constants.
    heat_gain_present_kw: float = 0.100
    heat_gain_active_kw: float = 0.150
    # Area-normalized equipment/lighting internal-gain density [W/m^2],
    # building-total -- ASHRAE 90.1 Table 9.5.1-style lighting power density
    # plus an illustrative equipment-load margin for types with heavy
    # equipment (kitchens, refrigeration). See each type's `schedule.json`
    # `_comment` for the specific reasoning. `None` means "no area-driven
    # component" (occupant-count-only gains, the pre-existing behavior).
    # Blended with, not a replacement for, `heat_gain_present_kw`/
    # `heat_gain_active_kw` -- see `core/buem_adapter.py`'s
    # `to_buem_profiles(floor_area_m2=..., gain_w_per_m2=...)` (buem's
    # `occupancy_gains_handoff.md` Gap 1).
    gain_w_per_m2: float | None = None
    # Conditional on being present-but-inactive: probability of being
    # asleep. Same mechanism as households (`ArchetypeSpec`) -- most
    # service-building types leave this all-zero (no overnight occupants),
    # but a type with genuine overnight presence (e.g. a hotel) sets real
    # data and gets real `n_asleep` output through
    # `core/occupancy_engine.py`'s generators.
    asleep_probabilities: np.ndarray = field(
        default_factory=lambda: np.zeros((24, 2))
    )


SERVICE_BUILDING_TYPES: dict[str, ServiceBuildingTypeSpec] = {}


def register_building_type(spec: ServiceBuildingTypeSpec) -> None:
    """Register a new service-building type (e.g. from a future reference
    occupancy module) under ``spec.id``."""
    SERVICE_BUILDING_TYPES[spec.id] = spec


def get_building_type(name: str) -> ServiceBuildingTypeSpec:
    try:
        return SERVICE_BUILDING_TYPES[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown service building type {name!r}. "
            f"Registered: {sorted(SERVICE_BUILDING_TYPES)}"
        ) from exc


def load_building_type(type_id: str) -> ServiceBuildingTypeSpec:
    """Load ``data/<type_id>/{schedule,equipment}.json`` and register it."""
    schedule = load_json_resource(_PACKAGE, f"data/{type_id}/schedule.json")
    equipment_data = load_json_resource(
        _PACKAGE, f"data/{type_id}/equipment.json"
    )
    asleep = schedule.get("asleep_probabilities")
    spec = ServiceBuildingTypeSpec(
        id=schedule["id"],
        description=schedule.get("description", ""),
        region=schedule.get("region", "NL"),
        capacity_default=int(schedule.get("capacity_default", 50)),
        generator=schedule.get("generator", "fixed_schedule"),
        generator_params=schedule.get("generator_params", {}),
        equipment=normalize_equipment_table(equipment_data),
        heat_gain_present_kw=float(
            schedule.get("heat_gain_present_kw", 0.100)
        ),
        heat_gain_active_kw=float(schedule.get("heat_gain_active_kw", 0.150)),
        gain_w_per_m2=(
            float(schedule["gain_w_per_m2"])
            if schedule.get("gain_w_per_m2") is not None
            else None
        ),
        asleep_probabilities=(
            np.asarray(asleep, dtype=float)
            if asleep is not None
            else np.zeros((24, 2))
        ),
    )
    register_building_type(spec)
    return spec

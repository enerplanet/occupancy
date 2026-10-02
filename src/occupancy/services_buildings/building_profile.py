from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from occupancy.core.equipment import EquipmentSpec, generate_equipment_power
from occupancy.core.occupancy_engine import (
    OccupancyGenerationContext,
    get_generator,
)
from occupancy.core.result import OccupancyResult
from occupancy.core.seed import derive_default_seed
from occupancy.services_buildings.building_types import get_building_type

# Same category-derived `cooking_active` convention as
# `households.electricity.ElectricityConsumptionProfile` -- several service
# building types (restaurant, bakery, school) also carry "kitchen"-category
# equipment. See that module's `_COOKING_CATEGORY` for the full rationale.
_COOKING_CATEGORY = "kitchen"


@dataclass
class ServiceBuildingProfile:
    """Stochastic hourly occupancy + electricity demand for one service
    (non-residential) building.

    ``building_type`` selects the default capacity, generator strategy
    (typically ``fixed_schedule``), and equipment set from
    :data:`occupancy.services_buildings.building_types.SERVICE_BUILDING_TYPES`.
    Unlike households, occupancy and equipment demand are combined in a
    single profile — there is no separate electricity-profile class.

    ``equipment`` mirrors
    :attr:`occupancy.households.electricity.ElectricityConsumptionProfile.equipment`:
    ``None`` (the default) uses the building type's full default table;
    passing a dict uses it as-is, so any item id absent from the dict is
    fully excluded (not merely zeroed) rather than falling back to the
    type's default for that item. ``include_equipment=False`` is a
    separate master switch that omits the ``total_power_kwh`` column
    entirely, regardless of ``equipment`` — passing ``equipment={}`` with
    ``include_equipment=True`` instead keeps the column present but
    all-zero. This is parameter parity with the household side (buem's
    `occupancy_module_activities.md` item 2), not a new occupancy-side
    concept.

    When ``include_equipment`` is on, the profile also carries a boolean
    ``cooking_active`` column, same convention and rationale as
    :class:`~occupancy.households.electricity.ElectricityConsumptionProfile`'s
    (buem's `dhw_cooking_heat_handoff.md` ask #2).
    """

    building_type: str
    year: int
    capacity: int | None = None
    # `None` (the default) resolves to a deterministic hash of this
    # profile's own construction inputs rather than OS entropy -- see
    # `HouseholdProfile.seed`'s matching field comment and
    # `core.seed.derive_default_seed` for the full rationale.
    seed: int | None = None
    region: str | None = None
    generator: str | None = None
    generator_params: dict[str, Any] | None = None
    include_equipment: bool = True
    equipment: dict[str, EquipmentSpec] | None = None

    def __post_init__(self) -> None:
        if self.year < 1900:
            raise ValueError("year must be >= 1900")

        self._type_spec = get_building_type(self.building_type)
        if self.capacity is None:
            self.capacity = self._type_spec.capacity_default
        if self.capacity <= 0:
            raise ValueError("capacity must be greater than 0")
        if self.region is None:
            self.region = self._type_spec.region

        self._generator_name = self.generator or self._type_spec.generator
        self._generator_params = (
            self.generator_params
            if self.generator_params is not None
            else self._type_spec.generator_params
        )

        if self.equipment is None:
            self.equipment = dict(self._type_spec.equipment)

        if self.seed is None:
            self.seed = derive_default_seed(
                kind=self.building_type,
                size=self.capacity,
                year=self.year,
                archetype="",
                region=self.region,
            )
        self._rng = np.random.default_rng(self.seed)
        self._index = pd.date_range(
            start=f"{self.year}-01-01",
            end=f"{self.year}-12-31 23:00",
            freq="h",
        )
        self._profile: pd.DataFrame | None = None

    def get_equipment_table(self) -> dict[str, EquipmentSpec]:
        """The resolved equipment table (the building type's default, or
        the caller-supplied override) — read this before building a
        filtered subset, the same way
        :meth:`~occupancy.households.electricity.ElectricityConsumptionProfile.get_equipment_table`
        is used on the household side, so per-type tuning for unmentioned
        items isn't silently lost."""
        assert self.equipment is not None
        return self.equipment

    def generate(self, seed: int | None = None) -> pd.DataFrame:
        """Generate and cache the yearly occupancy (+ equipment) profile."""
        assert self.capacity is not None
        rng = self._rng if seed is None else np.random.default_rng(seed)
        ctx = OccupancyGenerationContext(
            size=self.capacity,
            index=self._index,
            rng=rng,
            asleep_probabilities=self._type_spec.asleep_probabilities,
            params=self._generator_params or {},
        )
        strategy = get_generator(self._generator_name)
        profile = strategy(ctx)

        if self.include_equipment:
            assert self.equipment is not None
            specs = [spec for spec in self.equipment.values() if spec.enabled]
            category_totals: dict[str, np.ndarray] = {}
            profile["total_power_kwh"] = generate_equipment_power(
                specs, profile, rng, category_totals=category_totals
            )
            profile["cooking_active"] = (
                category_totals.get(_COOKING_CATEGORY, np.zeros(len(profile)))
                > 0
            )

        self._profile = profile
        return profile

    def get_profile(self) -> pd.DataFrame:
        """Return a generated profile, creating one lazily if needed."""
        if self._profile is None:
            return self.generate()
        return self._profile

    def to_result(self) -> OccupancyResult:
        assert self.region is not None
        return OccupancyResult(
            profile=self.get_profile(),
            year=self.year,
            num_persons=self.capacity or 0,
            building_type=self.building_type,
            region=self.region,
            heat_gain_present_kw=self._type_spec.heat_gain_present_kw,
            heat_gain_active_kw=self._type_spec.heat_gain_active_kw,
            gain_w_per_m2=self._type_spec.gain_w_per_m2,
        )

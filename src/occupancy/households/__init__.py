"""Household occupancy + electricity modeling.

Base linking module: importing this package loads every archetype JSON
under ``data/archetypes/`` into :data:`HOUSEHOLD_ARCHETYPES`.
"""

from occupancy.households.archetypes import (
    HOUSEHOLD_ARCHETYPES,
    ArchetypeSpec,
    get_archetype,
    register_archetype,
)
from occupancy.households.dhw import (
    generate_dhw_draws,
    load_tapping_categories,
    register_timing_envelope,
)
from occupancy.households.electricity import (
    EQUIPMENT_TYPES,
    ElectricityConsumptionProfile,
    default_equipment_table,
)
from occupancy.households.household_profile import HouseholdProfile

__all__ = [
    "EQUIPMENT_TYPES",
    "HOUSEHOLD_ARCHETYPES",
    "ArchetypeSpec",
    "ElectricityConsumptionProfile",
    "HouseholdProfile",
    "default_equipment_table",
    "generate_dhw_draws",
    "get_archetype",
    "load_tapping_categories",
    "register_archetype",
    "register_timing_envelope",
]

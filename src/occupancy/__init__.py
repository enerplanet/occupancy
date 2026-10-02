"""Occupancy modeling package for UU-BUEM: households and service buildings."""

from occupancy.core.buem_adapter import to_buem_profiles
from occupancy.core.disaggregation import estimate_equipment_usage
from occupancy.core.result import OccupancyResult
from occupancy.demand import (
    DEFAULT_ARCHETYPE_BY_BUILDING_TYPE,
    DEFAULT_NUM_PERSONS,
    RESIDENTIAL_BUILDING_TYPES,
    SERVICE_FLOOR_AREA_PER_OCCUPANT_M2,
    BuildingDemand,
    building_demand,
    derive_service_capacity,
    equipment_table,
    resolve_num_persons,
)
from occupancy.households import (
    EQUIPMENT_TYPES,
    HOUSEHOLD_ARCHETYPES,
    ElectricityConsumptionProfile,
    HouseholdProfile,
    generate_dhw_draws,
)
from occupancy.services_buildings import (
    SERVICE_BUILDING_TYPES,
    ServiceBuildingProfile,
)

# Back-compat alias: the pre-restructuring public API exposed a single
# generic `OccupancyProfile`. `HouseholdProfile` is its direct successor.
OccupancyProfile = HouseholdProfile

try:
    from importlib.metadata import version as _dist_version

    __version__ = _dist_version("occupancy")
except Exception:  # noqa: BLE001 -- not installed as a distribution
    __version__ = "unknown"

__all__ = [
    "DEFAULT_ARCHETYPE_BY_BUILDING_TYPE",
    "DEFAULT_NUM_PERSONS",
    "EQUIPMENT_TYPES",
    "HOUSEHOLD_ARCHETYPES",
    "RESIDENTIAL_BUILDING_TYPES",
    "SERVICE_BUILDING_TYPES",
    "SERVICE_FLOOR_AREA_PER_OCCUPANT_M2",
    "BuildingDemand",
    "ElectricityConsumptionProfile",
    "HouseholdProfile",
    "OccupancyProfile",
    "OccupancyResult",
    "ServiceBuildingProfile",
    "__version__",
    "building_demand",
    "derive_service_capacity",
    "equipment_table",
    "estimate_equipment_usage",
    "generate_dhw_draws",
    "resolve_num_persons",
    "to_buem_profiles",
]

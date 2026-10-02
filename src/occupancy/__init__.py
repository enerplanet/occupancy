"""Occupancy modeling package for UU-BUEM: households and service buildings."""

from occupancy.core.buem_adapter import to_buem_profiles
from occupancy.core.disaggregation import estimate_equipment_usage
from occupancy.core.result import OccupancyResult
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
    from occupancy._version import __version__
except ImportError:
    __version__ = "unknown"

__all__ = [
    "EQUIPMENT_TYPES",
    "HOUSEHOLD_ARCHETYPES",
    "SERVICE_BUILDING_TYPES",
    "ElectricityConsumptionProfile",
    "HouseholdProfile",
    "OccupancyProfile",
    "OccupancyResult",
    "ServiceBuildingProfile",
    "__version__",
    "estimate_equipment_usage",
    "generate_dhw_draws",
    "to_buem_profiles",
]

"""Shared engine abstractions used by both households/ and
services_buildings/."""

from occupancy.core.equipment import EquipmentSpec, register_strategy
from occupancy.core.occupancy_engine import (
    OccupancyGenerationContext,
    register_generator,
)
from occupancy.core.result import OccupancyResult
from occupancy.core.seed import building_seed

__all__ = [
    "EquipmentSpec",
    "OccupancyGenerationContext",
    "OccupancyResult",
    "building_seed",
    "register_generator",
    "register_strategy",
]

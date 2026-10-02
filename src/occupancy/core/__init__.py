"""Shared engine abstractions used by both households/ and
services_buildings/."""

from occupancy.core.equipment import EquipmentSpec, register_strategy
from occupancy.core.occupancy_engine import (
    OccupancyGenerationContext,
    register_generator,
)
from occupancy.core.result import OccupancyResult

__all__ = [
    "EquipmentSpec",
    "OccupancyGenerationContext",
    "OccupancyResult",
    "register_generator",
    "register_strategy",
]

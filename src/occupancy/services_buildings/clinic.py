"""Outpatient clinic service-building type. Loads and registers its
config on import."""

from occupancy.services_buildings.building_types import load_building_type

CLINIC = load_building_type("clinic")

"""Supermarket service-building type. Loads and registers its config on
import."""

from occupancy.services_buildings.building_types import load_building_type

SUPERMARKET = load_building_type("supermarket")

"""Service (non-residential) building occupancy + equipment modeling.

Base linking module: importing this package imports every building-type
module below, and each registers itself into ``SERVICE_BUILDING_TYPES`` as
a side effect of import. Add a new type by adding a
``data/<type>/{schedule,equipment}.json`` pair and a matching thin module
here that calls ``load_building_type("<type>")``.
"""

from occupancy.services_buildings import (
    bakery,
    clinic,
    hotel,
    office,
    restaurant,
    school,
    supermarket,
    warehouse,
)
from occupancy.services_buildings.building_profile import (
    ServiceBuildingProfile,
)
from occupancy.services_buildings.building_types import (
    SERVICE_BUILDING_TYPES,
    ServiceBuildingTypeSpec,
    get_building_type,
    register_building_type,
)

__all__ = [
    "SERVICE_BUILDING_TYPES",
    "ServiceBuildingProfile",
    "ServiceBuildingTypeSpec",
    "bakery",
    "clinic",
    "get_building_type",
    "hotel",
    "office",
    "register_building_type",
    "restaurant",
    "school",
    "supermarket",
    "warehouse",
]

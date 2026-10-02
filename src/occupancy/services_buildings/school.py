"""School service-building type. Loads and registers its config on import.

Term-time (weekday-only, closed July-August) is expressed entirely through
the generic ``fixed_schedule`` generator's ``closed_weekends``/
``closed_months`` params in ``data/school/schedule.json`` -- no bespoke
calendar code needed here.
"""

from occupancy.services_buildings.building_types import load_building_type

SCHOOL = load_building_type("school")

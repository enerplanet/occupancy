"""Per-building demand in one call.

Composes the household and service-building generators with the rules a
building model needs around them: household size by building type,
country and region; a default archetype per building type; service
capacity from floor area; the two-household blend that reproduces a
fractional mean household size; scaling to the dwellings in a building;
and the cooking-carrier balance between electricity and internal gains.
These rules lived in the buem thermal model until 6.1.0+enerplanet.1 and
moved here so that buem and the grid model size from the same function.

The electricity scalars need no weather and no envelope: a grid model
calls :func:`building_demand` with a building type, a country and the
number of dwellings and reads ``annual_electricity_kwh`` and
``peak_electricity_kw``.

This module is ``occupancy.demand``; the package exports the function
as ``occupancy.building_demand``.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Any

import pandas as pd

from occupancy.core.buem_adapter import to_buem_profiles
from occupancy.core.loader import load_csv_resource
from occupancy.households import (
    ElectricityConsumptionProfile,
    HouseholdProfile,
    generate_dhw_draws,
)
from occupancy.households.electricity import EQUIPMENT_TYPES
from occupancy.services_buildings import ServiceBuildingProfile

logger = logging.getLogger(__name__)

# TABULA residential size classes; anything else is looked up as a
# service-building type.
RESIDENTIAL_BUILDING_TYPES = frozenset({"SFH", "TH", "MFH", "AB"})

# Last resort when the household-size table has no row for a building
# type at any level.
DEFAULT_NUM_PERSONS = 4.0

DEFAULT_ARCHETYPE_BY_BUILDING_TYPE: dict[str, str] = {
    "SFH": "family_with_children",
    "TH": "working_couple",
    "MFH": "generic",
    "AB": "generic",
}

# Floor area per occupant used to size a service building's capacity
# from its floor area when the caller supplies no capacity.
SERVICE_FLOOR_AREA_PER_OCCUPANT_M2: dict[str, float] = {
    "office": 15.0,
    "school": 5.0,
    "restaurant": 3.0,
    "supermarket": 10.0,
    "hotel": 20.0,
    "warehouse": 100.0,
    "clinic": 15.0,
    "bakery": 10.0,
}

COOKING_CARRIERS = ("electric", "gas", "none")

# Share of cooking energy that reaches the room as heat; the rest leaves
# in the food and through the extraction hood. Same for both carriers.
DEFAULT_COOKING_HEAT_GAIN_FRACTION = 0.5

_ANY = "*"
_BLEND_TOLERANCE = 0.01
_COOKING_CATEGORY = "kitchen"
_NUM_PERSONS_RESOURCE = "data/num_persons_by_building_type.csv"
_BLENDED_KEYS = ("Q_ig", "elecLoad")


@lru_cache(maxsize=1)
def _num_persons_rows() -> tuple[tuple[str, str, str, float], ...]:
    """Rows of the household-size table as (country, region, type, n)."""
    table = load_csv_resource("occupancy.households", _NUM_PERSONS_RESOURCE)
    required = {"country", "region_code", "building_type", "num_persons"}
    missing = required - set(table.columns)
    if missing:
        raise ValueError(
            f"{_NUM_PERSONS_RESOURCE} is missing column(s) {sorted(missing)}"
        )
    rows = []
    for record in table.to_dict("records"):
        value = float(record["num_persons"])
        if value <= 0:
            raise ValueError(
                f"{_NUM_PERSONS_RESOURCE}: num_persons must be positive, "
                f"got {value} for {record['building_type']!r}"
            )
        rows.append(
            (
                str(record["country"] or _ANY).strip(),
                str(record["region_code"] or _ANY).strip(),
                str(record["building_type"]).strip(),
                value,
            )
        )
    return tuple(rows)


def resolve_num_persons(
    building_type: str | None,
    *,
    country: str | None = None,
    region_code: str | None = None,
    default: float | None = None,
) -> float | None:
    """Occupants per dwelling for a building type, most specific first.

    Lookup order, stopping at the first match: (country, region_code,
    type); (country, any, type); (any, any, type); ``default``.
    Returns ``default`` for an unknown or missing building type, which
    is the right answer for a service building.
    """
    wanted = (building_type or "").strip()
    if not wanted:
        return default
    candidates: list[tuple[str, str]] = []
    for want_country, want_region in (
        (country, region_code),
        (country, _ANY),
        (_ANY, _ANY),
    ):
        if want_country is None or want_region is None:
            continue
        key = (want_country.strip(), want_region.strip())
        if key not in candidates:
            candidates.append(key)
    for want_country, want_region in candidates:
        for row_country, row_region, row_type, value in _num_persons_rows():
            if (
                row_country == want_country
                and row_region == want_region
                and row_type == wanted
            ):
                return value
    return default


def resolve_archetype(building_type: str) -> str:
    """Default household archetype for a residential building type."""
    return DEFAULT_ARCHETYPE_BY_BUILDING_TYPE.get(building_type, "generic")


def derive_service_capacity(
    building_type: str, floor_area_m2: float | None
) -> int | None:
    """Occupant capacity of a service building from its floor area.

    ``None`` when the type has no density or the area is unusable, which
    lets :class:`ServiceBuildingProfile` apply its own type default. A
    building someone enters never has a capacity below one.
    """
    density = SERVICE_FLOOR_AREA_PER_OCCUPANT_M2.get(building_type)
    if density is None or not floor_area_m2 or floor_area_m2 <= 0:
        return None
    return max(1, round(float(floor_area_m2) / density))


def bracket_household_size(num_persons: float) -> tuple[int, int, float]:
    """Integer household sizes bracketing a mean, with the upper weight.

    A per-building-type household size is a population mean and usually
    fractional, while a generated household has a whole number of
    occupants. Blending the two neighbouring sizes reproduces the mean;
    rounding would collapse 2.4 and 2.6 onto 2 and 3. The weight is 0.0
    for a whole number, so the second generation is skipped.
    """
    lower = math.floor(num_persons)
    weight = num_persons - lower
    if weight < _BLEND_TOLERANCE:
        return max(1, lower), max(1, lower), 0.0
    if weight > 1.0 - _BLEND_TOLERANCE:
        return lower + 1, lower + 1, 0.0
    return max(1, lower), max(1, lower) + 1, weight


def _blend(lower: Any, upper: Any, upper_weight: float) -> Any:
    """Linear blend of two Series or DataFrames, keeping the lower's
    name and index."""
    blended = lower * (1.0 - upper_weight) + upper * upper_weight
    if isinstance(lower, pd.Series):
        return blended.rename(lower.name)
    return blended


def _scale_out_annual(series: pd.Series, remove_kwh: float) -> pd.Series:
    """Remove ``remove_kwh`` from a series' annual total by uniform
    scaling.

    The kitchen-only draws are an independent realization of the
    stochastic model, not a decomposition of the full run, so an hourly
    subtraction would clip and lose a large share of the energy. Scaling
    keeps the annual total exact.
    """
    total = float(series.sum())
    if total <= 0:
        return series
    factor = max(0.0, 1.0 - remove_kwh / total)
    return (series * factor).rename(series.name)


def _realign(
    series: pd.Series, target_index: pd.DatetimeIndex, name: str
) -> pd.Series:
    """Nearest-hour alignment onto ``target_index``; a timestamp more
    than half an hour from any target is an error, not a zero."""
    series_tz = (
        series.index.tz if isinstance(series.index, pd.DatetimeIndex) else None
    )
    if series_tz != target_index.tz:
        series = (
            series.tz_localize(target_index.tz)
            if series_tz is None
            else series.tz_convert(target_index.tz)
        )
    aligned = series.reindex(
        target_index, method="nearest", tolerance=pd.Timedelta(minutes=30)
    )
    if aligned.isna().any():
        raise ValueError(
            f"{name} does not cover the profile index at "
            f"{int(aligned.isna().sum())} of {len(target_index)} hours"
        )
    return aligned


def equipment_table(
    household: HouseholdProfile, seed: int | None, equipment: Any
) -> dict[str, Any] | None:
    """Apply a ``{equipment_id: bool}`` selector to the household's
    archetype-adjusted equipment table. ``True`` forces ownership,
    ``False`` removes the item, unmentioned items keep their default."""
    if not equipment:
        return None
    if not isinstance(equipment, dict):
        raise ValueError(  # noqa: TRY004
            "equipment must be a dict of {equipment_id: bool}, "
            f"got {type(equipment).__name__}."
        )
    unknown = sorted(set(equipment) - set(EQUIPMENT_TYPES))
    if unknown:
        raise ValueError(
            f"equipment contains unrecognized id(s) {unknown}; expected a "
            f"subset of {sorted(EQUIPMENT_TYPES)}."
        )
    non_bool = {k: v for k, v in equipment.items() if not isinstance(v, bool)}
    if non_bool:
        raise ValueError(
            f"equipment values must be true/false, got {non_bool!r}."
        )
    base = ElectricityConsumptionProfile(
        household, seed=seed
    ).get_equipment_table()
    table: dict[str, Any] = {}
    for key, spec in base.items():
        if key not in equipment:
            table[key] = spec
        elif equipment[key]:
            table[key] = replace(spec, ownership_probability=1.0)
    return table


def _cooking_energy(
    household: HouseholdProfile,
    elec_gen: ElectricityConsumptionProfile,
    seed: int | None,
) -> pd.Series | None:
    """Hourly cooking energy from a kitchen-only run of the appliance
    model; ``None`` when the household owns no cooking appliance."""
    kitchen = {
        name: spec
        for name, spec in elec_gen.get_equipment_table().items()
        if getattr(spec, "category", None) == _COOKING_CATEGORY
    }
    if not kitchen:
        return None
    profile = (
        ElectricityConsumptionProfile(household, equipment=kitchen, seed=seed)
        .to_result()
        .profile
    )
    return profile["total_power_kwh"].rename("cooking_kwh")


@dataclass(frozen=True)
class _Household:
    result: Any
    draws: pd.DataFrame
    cooking: pd.Series | None


def _generate_household(
    num_persons: int,
    archetype: str,
    year: int,
    seed: int | None,
    equipment: Any,
) -> _Household:
    """One integer-sized household: occupancy result, DHW draws and
    cooking energy. DHW draws take ``seed=None`` on purpose so the
    package derives its own deterministic seed, decorrelated from the
    electricity draws."""
    household = HouseholdProfile(
        num_persons=num_persons, year=year, seed=seed, archetype=archetype
    )
    table = equipment_table(household, seed, equipment)
    elec_gen = ElectricityConsumptionProfile(
        household, equipment=table, seed=seed
    )
    result = elec_gen.to_result()
    draws = generate_dhw_draws(
        result.profile,
        num_persons=num_persons,
        cooking_active=result.profile.get("cooking_active"),
        seed=None,
    )
    return _Household(
        result, draws, _cooking_energy(household, elec_gen, seed)
    )


@dataclass(frozen=True)
class BuildingDemand:
    """Result of :func:`building_demand`.

    ``electricity`` is kWh per hour (equal to kW at hourly resolution)
    on the profile's own on-the-hour index. ``dhw_draws`` holds litres
    per fixture plus ``dhw_liters_total`` for residential buildings and
    is ``None`` for services. ``cooking_kwh`` is ``None`` when nothing
    was cooked electrically. ``elec_load_as_gain`` is ``False`` for
    services, whose ``internal_gains`` already include equipment heat.
    """

    building_type: str
    num_persons: float | None
    archetype: str | None
    capacity: int | None
    residential_units: float
    electricity: pd.Series
    annual_electricity_kwh: float
    peak_electricity_kw: float
    internal_gains: pd.Series
    occ_nothome: pd.Series
    occ_sleeping: pd.Series
    cooking_active: pd.Series | None
    cooking_kwh: pd.Series | None
    dhw_draws: pd.DataFrame | None
    elec_load_as_gain: bool

    def buem_profiles(self) -> dict[str, pd.Series]:
        """The series under the names buem's cfg uses."""
        profiles = {
            "elecLoad": self.electricity,
            "Q_ig": self.internal_gains,
            "occ_nothome": self.occ_nothome,
            "occ_sleeping": self.occ_sleeping,
        }
        if self.cooking_active is not None:
            profiles["cooking_active"] = self.cooking_active
        return profiles


def building_demand(
    building_type: str,
    *,
    country: str | None = None,
    region_code: str | None = None,
    year: int = 2018,
    residential_units: float = 1.0,
    floor_area_m2: float | None = None,
    cooking_carrier: str = "electric",
    seed: int | None = None,
    num_persons: float | None = None,
    archetype: str | None = None,
    capacity: int | None = None,
    equipment: dict[str, bool] | None = None,
    elec_load: pd.Series | None = None,
    cooking_heat_gain_fraction: float = DEFAULT_COOKING_HEAT_GAIN_FRACTION,
) -> BuildingDemand:
    """Hourly demand and the scalars a grid model needs for one building.

    ``building_type`` is a TABULA residential class (SFH, TH, MFH, AB)
    or a registered service-building type. Residential buildings take
    their household size from the bundled table by ``country`` and
    ``region_code`` unless ``num_persons`` is given, their archetype
    from :data:`DEFAULT_ARCHETYPE_BY_BUILDING_TYPE` unless ``archetype``
    is given, and are scaled to ``residential_units`` dwellings. Service
    buildings need ``floor_area_m2`` and take ``capacity`` from it unless
    given. A measured ``elec_load`` replaces the generated electricity
    and is never rescaled. ``cooking_carrier`` moves cooking energy out
    of electricity for ``"gas"``, corrects internal gains for both
    ``"gas"`` and ``"electric"``, and does nothing for ``"none"``.
    """
    carrier = str(cooking_carrier).lower()
    if carrier not in COOKING_CARRIERS:
        raise ValueError(
            f"cooking_carrier must be one of {COOKING_CARRIERS}, "
            f"got {cooking_carrier!r}."
        )
    units = float(residential_units or 1.0)
    if building_type in RESIDENTIAL_BUILDING_TYPES:
        profiles, draws, cooking, mean, used_archetype = _residential(
            building_type,
            country,
            region_code,
            year,
            seed,
            num_persons,
            archetype,
            equipment,
            elec_load,
        )
        used_capacity: int | None = None
        elec_load_as_gain = True
    else:
        profiles, used_capacity = _service(
            building_type,
            year,
            seed,
            floor_area_m2,
            capacity,
            equipment,
            elec_load,
        )
        draws, cooking, mean, used_archetype = None, None, None, None
        elec_load_as_gain = False

    if units > 1.0:
        profiles["Q_ig"] = profiles["Q_ig"] * units
        if elec_load is None:
            profiles["elecLoad"] = profiles["elecLoad"] * units
        if draws is not None:
            draws = draws * units
        if cooking is not None:
            cooking = cooking * units

    if cooking is not None:
        _apply_cooking_balance(
            profiles,
            cooking,
            carrier,
            elec_load is not None,
            cooking_heat_gain_fraction,
        )

    electricity = profiles["elecLoad"]
    return BuildingDemand(
        building_type=building_type,
        num_persons=mean,
        archetype=used_archetype,
        capacity=used_capacity,
        residential_units=units,
        electricity=electricity,
        annual_electricity_kwh=float(electricity.sum()),
        peak_electricity_kw=float(electricity.max()),
        internal_gains=profiles["Q_ig"],
        occ_nothome=profiles["occ_nothome"],
        occ_sleeping=profiles["occ_sleeping"],
        cooking_active=profiles.get("cooking_active"),
        cooking_kwh=cooking,
        dhw_draws=draws,
        elec_load_as_gain=elec_load_as_gain,
    )


def _residential(
    building_type: str,
    country: str | None,
    region_code: str | None,
    year: int,
    seed: int | None,
    num_persons: float | None,
    archetype: str | None,
    equipment: Any,
    elec_load: pd.Series | None,
) -> tuple[dict[str, pd.Series], pd.DataFrame, pd.Series | None, float, str]:
    if num_persons is not None:
        mean = max(1.0, float(num_persons))
    else:
        resolved = resolve_num_persons(
            building_type,
            country=country,
            region_code=region_code,
            default=DEFAULT_NUM_PERSONS,
        )
        mean = max(
            1.0,
            float(resolved if resolved is not None else DEFAULT_NUM_PERSONS),
        )
    used_archetype = archetype or resolve_archetype(building_type)
    lower_n, upper_n, upper_weight = bracket_household_size(mean)
    lower = _generate_household(lower_n, used_archetype, year, seed, equipment)
    if elec_load is not None:
        elec_load = _realign(
            elec_load, lower.result.profile.index, "elec_load"
        )
    profiles = to_buem_profiles(lower.result, elec_load=elec_load)
    draws, cooking = lower.draws, lower.cooking
    if upper_weight > 0.0:
        upper = _generate_household(
            upper_n, used_archetype, year, seed, equipment
        )
        upper_profiles = to_buem_profiles(upper.result, elec_load=elec_load)
        for key in _BLENDED_KEYS:
            if key == "elecLoad" and elec_load is not None:
                continue
            profiles[key] = _blend(
                profiles[key], upper_profiles[key], upper_weight
            )
        draws = _blend(draws, upper.draws, upper_weight)
        if cooking is not None and upper.cooking is not None:
            cooking = _blend(cooking, upper.cooking, upper_weight)
    return profiles, draws, cooking, mean, used_archetype


def _service(
    building_type: str,
    year: int,
    seed: int | None,
    floor_area_m2: float | None,
    capacity: int | None,
    equipment: Any,
    elec_load: pd.Series | None,
) -> tuple[dict[str, pd.Series], int | None]:
    if equipment:
        logger.warning(
            "equipment selection was supplied for service building type "
            "%r, which has no per-item equipment selection; ignoring.",
            building_type,
        )
    if floor_area_m2 is None or floor_area_m2 <= 0:
        raise ValueError(
            f"floor_area_m2 is required for service building type "
            f"{building_type!r}."
        )
    used_capacity = (
        int(capacity)
        if capacity is not None
        else derive_service_capacity(building_type, floor_area_m2)
    )
    try:
        service = ServiceBuildingProfile(
            building_type=building_type,
            year=year,
            capacity=used_capacity,
            seed=seed,
        )
    except ValueError as exc:
        raise ValueError(
            f"building_type {building_type!r} is neither a residential "
            f"TABULA code ({sorted(RESIDENTIAL_BUILDING_TYPES)}) nor a "
            "registered service-building type."
        ) from exc
    result = service.to_result()
    if elec_load is not None:
        elec_load = _realign(elec_load, result.profile.index, "elec_load")
    profiles = to_buem_profiles(
        result, floor_area_m2=float(floor_area_m2), elec_load=elec_load
    )
    return profiles, used_capacity


def _apply_cooking_balance(
    profiles: dict[str, pd.Series],
    cooking: pd.Series,
    carrier: str,
    elec_load_supplied: bool,
    gain_fraction: float,
) -> None:
    """Split cooking energy into the carrier that pays for it and the
    share that heats the room.

    The appliance model counts every cooking appliance electrically, so
    a gas-cooking household has the energy taken back out of
    ``elecLoad`` before it is reported as gas, or it appears under both
    carriers. Room heat from cooking is ``gain_fraction`` of the input
    for both carriers: ``Q_ig`` goes down by the non-recovered share for
    electric cooking, already counted in full through ``elecLoad``, and
    up by the recovered share for gas cooking, not in ``elecLoad`` at
    all. A supplied ``elecLoad`` is never modified.
    """
    annual = float(cooking.sum())
    if carrier == "none" or annual <= 0:
        return
    if carrier == "gas" and not elec_load_supplied:
        profiles["elecLoad"] = _scale_out_annual(profiles["elecLoad"], annual)
    if carrier == "gas":
        profiles["Q_ig"] = (profiles["Q_ig"] + cooking * gain_fraction).rename(
            profiles["Q_ig"].name
        )
    else:
        profiles["Q_ig"] = _scale_out_annual(
            profiles["Q_ig"], annual * (1.0 - gain_fraction)
        )

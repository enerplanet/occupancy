"""Adapter from this package's :class:`~occupancy.core.result.OccupancyResult`
to the internal-gains/occupancy input contract required by
`UU-BUEM/buem <https://github.com/UU-BUEM/buem>`_'s 5R1C thermal model.

``buem.thermal.model_buem.ModelBUEM._addPara``/``_addConstraints_sequential``
raise ``ValueError`` unless ``cfg`` carries all four of ``Q_ig``, ``elecLoad``,
``occ_nothome``, ``occ_sleeping`` (each a ``pd.Series`` indexed like
``cfg["weather"]``), and forms internal air gains per timestep as::

    Q_ia = Q_ig + elecLoad

``occ_nothome``/``occ_sleeping`` are required and validated but do **not**
rescale ``Q_ia``: both terms arrive here already scaled by real-time
occupant presence (``Q_ig`` is built from present/active occupant *counts*
below, so it is zero when the building is empty), and buem previously
multiplied that through by a presence *fraction* a second time —
double-discounting an already presence-scaled quantity. buem removed that
step; this docstring documented the superseded formula until 2026-08-28.

The practical consequence for this module: ``num_persons`` reaches buem's
thermal model *only* through ``Q_ig`` and ``elecLoad``. Nothing downstream
re-introduces a headcount dependence, so both terms have to carry it
themselves — see ``core/equipment.py``'s ``_occupant_multiplier`` for the
``elecLoad`` half.

This module is the one place that knows how to turn occupant/equipment
counts into that shape — see ``to_buem_profiles``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from occupancy.core.result import OccupancyResult

# Heat gain per occupant [kW], building-total (sensible + latent combined --
# buem's Q_ia term does not distinguish them, see module docstring). Based on
# ISO 7730 / ASHRAE Fundamentals Ch. 18 typical adult heat output: ~100 W
# seated/resting, ~150 W light activity (walking, light office/retail/
# kitchen work). Fallback used only when `result` carries no per-type value
# of its own (see `heat_gain_present_kw`/`heat_gain_active_kw` on
# `ArchetypeSpec`/`ServiceBuildingTypeSpec`, threaded onto `OccupancyResult`
# by each `to_result()`). Illustrative first-pass values, not
# survey-calibrated -- see CHANGELOG and `.claude/services/open.md` /
# `.claude/residential/open.md`.
HEAT_GAIN_PRESENT_KW = 0.100
HEAT_GAIN_ACTIVE_KW = 0.150

# Households only, and only as a fallback. `core/occupancy_engine.py`'s
# generators emit a real `n_asleep` column for any building type whose
# spec sets `asleep_probabilities` (households; hotel-style service
# buildings) -- that real output is always used when present, regardless
# of building type. This window is only consulted for profiles generated
# before `n_asleep` existed (e.g. cached CSVs) or hand-built DataFrames
# lacking the column, and only for households -- applying a "night hours
# = asleep" heuristic to an arbitrary service building without real sleep
# data would be a much shakier assumption than for a household.
DEFAULT_SLEEP_WINDOW: tuple[int, int] = (
    23,
    7,
)  # [start_hour, end_hour), wraps midnight


def to_buem_profiles(
    result: OccupancyResult,
    *,
    gain_present_kw: float | None = None,
    gain_active_kw: float | None = None,
    sleep_window: tuple[int, int] | None = DEFAULT_SLEEP_WINDOW,
    floor_area_m2: float | None = None,
    gain_w_per_m2: float | None = None,
    elec_load: pd.Series | None = None,
) -> dict[str, pd.Series]:
    """Convert one ``OccupancyResult`` into buem's four required cfg series.

    Returns a dict with keys ``"Q_ig"``, ``"elecLoad"``, ``"occ_nothome"``,
    ``"occ_sleeping"`` -- assign directly into buem's ``cfg`` dict, e.g.
    ``cfg.update(to_buem_profiles(result))``. When ``result.profile`` carries
    a ``cooking_active`` column (households/service-building types whose
    equipment table includes a ``"kitchen"``-category item -- see
    ``ElectricityConsumptionProfile``/``ServiceBuildingProfile``), a fifth
    ``"cooking_active"`` boolean series is included too, for a future
    gas-cooking-energy term driven by real per-building cooking timing
    (buem's ``dhw_cooking_heat_handoff.md`` ask #2). Absent otherwise --
    buem's four required keys are unaffected either way.

    ``result.profile`` must already carry a ``total_power_kwh`` column (i.e.
    equipment power was generated) -- pass a ``ServiceBuildingProfile``
    result (equipment included by default) or a household result built via
    ``ElectricityConsumptionProfile.to_result()`` rather than a bare
    ``HouseholdProfile.to_result()`` -- *unless* ``elec_load`` is given (see
    below), in which case that requirement is skipped entirely.

    ``gain_present_kw``/``gain_active_kw``, if given, override everything
    else. Otherwise the per-occupant heat gain is taken from
    ``result.heat_gain_present_kw``/``result.heat_gain_active_kw`` (set by
    the originating archetype/building-type spec), falling back to this
    module's ``HEAT_GAIN_PRESENT_KW``/``HEAT_GAIN_ACTIVE_KW`` only if the
    result carries none.

    ``sleep_window`` is only consulted as a fallback when ``result.profile``
    has no ``n_asleep`` column (older/hand-built profiles), and only for
    households. When ``n_asleep`` is present, it's used directly for
    *any* building type (real generator output, see
    ``core/occupancy_engine.py``) -- most service-building types simply
    never set ``asleep_probabilities`` so ``n_asleep`` stays 0 for them,
    but a type that does (e.g. a hotel) gets genuine ``occ_sleeping``
    through the same mechanism as households.

    ``floor_area_m2``/``gain_w_per_m2`` add an area-normalized equipment/
    lighting gain component *blended with* (not replacing) the per-occupant
    ``Q_ig`` above -- buem's ``occupancy_gains_handoff.md`` Gap 1. Pass
    ``floor_area_m2`` (buem's ``A_ref``/``computed_A_ref()``, this module has
    no notion of it otherwise) to opt in; the area component is scaled by
    the same per-hour occupant-presence fraction used for ``occ_nothome``
    (``n_present / result.num_persons``), so it contributes nothing when the
    building is empty rather than adding a flat 24/7 term. ``gain_w_per_m2``,
    if given, overrides ``result.gain_w_per_m2`` (set by the originating
    archetype/building-type spec); if ``floor_area_m2`` is given but neither
    resolves to a value, raises ``ValueError`` rather than silently skipping
    the area component or guessing a density.

    ``elec_load``, if given, is used as ``elecLoad`` directly (reindexed
    onto ``result.profile``'s index) instead of requiring a
    ``total_power_kwh`` column -- for when elecLoad comes from somewhere
    other than occupancy's own equipment simulation (buem-supplied,
    real metering, ...) but ``Q_ig``/``occ_nothome``/``occ_sleeping`` should
    still be derived from occupancy's own generated presence pattern. See
    ``.claude/open.md`` "cross-repo" for the broader pylovo/multi-profile
    context this is scaffolding for.
    """
    profile = result.profile
    if elec_load is None and "total_power_kwh" not in profile.columns:
        raise ValueError(
            "OccupancyResult.profile has no 'total_power_kwh' column and no "
            "elec_load was given -- either generate equipment power first "
            "(ServiceBuildingProfile does this by default; for households "
            "use ElectricityConsumptionProfile(occupancy_profile=...)."
            "to_result() instead of HouseholdProfile.to_result()), or pass "
            "elec_load= explicitly with an externally-sourced series (e.g. "
            "from buem or real metering) to still get Q_ig/occ_nothome/"
            "occ_sleeping without occupancy generating its own elecLoad."
        )
    if result.num_persons <= 0:
        raise ValueError(
            "result.num_persons must be > 0 to normalize occupancy fractions"
        )

    gain_present = (
        gain_present_kw
        if gain_present_kw is not None
        else (
            result.heat_gain_present_kw
            if result.heat_gain_present_kw is not None
            else HEAT_GAIN_PRESENT_KW
        )
    )
    gain_active = (
        gain_active_kw
        if gain_active_kw is not None
        else (
            result.heat_gain_active_kw
            if result.heat_gain_active_kw is not None
            else HEAT_GAIN_ACTIVE_KW
        )
    )

    n_present = profile["n_present"].to_numpy(dtype=float)
    n_active = profile["n_active"].to_numpy(dtype=float)
    n_inactive_present = n_present - n_active
    num_persons = float(result.num_persons)

    occupant_gain_kw = (
        n_inactive_present * gain_present + n_active * gain_active
    )

    resolved_gain_w_per_m2 = (
        gain_w_per_m2 if gain_w_per_m2 is not None else result.gain_w_per_m2
    )
    if floor_area_m2 is not None:
        if resolved_gain_w_per_m2 is None:
            raise ValueError(
                "floor_area_m2 was given but no gain_w_per_m2 is available "
                "-- pass gain_w_per_m2 explicitly, or use a building_type/"
                "archetype whose spec defines one."
            )
        presence_fraction = np.clip(n_present / num_persons, 0.0, 1.0)
        area_gain_kw = (
            resolved_gain_w_per_m2 * floor_area_m2 / 1000.0
        ) * presence_fraction
    else:
        area_gain_kw = 0.0

    Q_ig = pd.Series(
        occupant_gain_kw + area_gain_kw,
        index=profile.index,
        name="Q_ig",
    )
    if elec_load is not None:
        elecLoad = elec_load.reindex(profile.index).rename("elecLoad")
        if elecLoad.isna().any():
            raise ValueError(
                "elec_load does not cover result.profile's index after "
                "reindexing -- pass a series aligned to result.profile.index."
            )
    else:
        elecLoad = profile["total_power_kwh"].rename("elecLoad")
    occ_nothome = pd.Series(
        1.0 - np.clip(n_present / num_persons, 0.0, 1.0),
        index=profile.index,
        name="occ_nothome",
    )

    is_household = result.building_type == "household"
    if "n_asleep" in profile.columns:
        n_asleep = profile["n_asleep"].to_numpy(dtype=float)
        occ_sleeping = pd.Series(
            np.clip(n_asleep / num_persons, 0.0, 1.0),
            index=profile.index,
            name="occ_sleeping",
        )
    elif sleep_window is not None and is_household:
        start, end = sleep_window
        hours = profile.index.hour.to_numpy()
        is_night = (
            (hours >= start) | (hours < end)
            if start > end
            else ((hours >= start) & (hours < end))
        )
        occ_sleeping = pd.Series(
            np.where(is_night, n_inactive_present / num_persons, 0.0),
            index=profile.index,
            name="occ_sleeping",
        )
    else:
        occ_sleeping = pd.Series(0.0, index=profile.index, name="occ_sleeping")

    result_profiles: dict[str, pd.Series] = {
        "Q_ig": Q_ig,
        "elecLoad": elecLoad,
        "occ_nothome": occ_nothome,
        "occ_sleeping": occ_sleeping,
    }
    if "cooking_active" in profile.columns:
        result_profiles["cooking_active"] = profile["cooking_active"].rename(
            "cooking_active"
        )
    return result_profiles

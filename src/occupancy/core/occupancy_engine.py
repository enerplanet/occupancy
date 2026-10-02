"""Pluggable occupancy-generation strategies shared by households and
service buildings.

Each strategy is a function ``(OccupancyGenerationContext) -> pd.DataFrame``
producing an ``n_present``/``n_active``/``n_asleep``/``activity`` frame
indexed by ``ctx.index``. New strategies (from future reference occupancy
modules) register via :func:`register_generator` — callers select one by
name, no code change required elsewhere.

``n_asleep`` is drawn from the present-but-inactive share of occupants
(``n_present - n_active``) via ``asleep_probabilities`` — a genuine model
output, not a post-hoc heuristic (see
:func:`occupancy.core.buem_adapter.to_buem_profiles`, which consumes it
directly as buem's ``occ_sleeping``, for any building type). It defaults
to an all-zero (24, 2) array, so any generator/building type that never
supplies it always has ``n_asleep == 0`` (most service-building types —
an office or supermarket has no sleeping occupants); a type that does
have overnight occupants (e.g. a hotel) sets real
``asleep_probabilities`` and gets genuine ``n_asleep`` output through the
exact same mechanism households use. One shared schema, one shared sleep
concept, for both.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class OccupancyGenerationContext:
    """Everything a generator strategy needs to produce one profile.

    ``home_probabilities``/``active_probabilities``/``asleep_probabilities``
    default to all-zero (24, 2) arrays. ``home_probabilities``/
    ``active_probabilities`` are only meaningful to the residential-style
    strategies (``binomial_independent``, ``markov_chain``);
    ``asleep_probabilities`` is meaningful to any strategy and any
    building type with overnight occupants (households; hotel-style
    service buildings via ``hourly_occupancy_curve``) — most service
    building types simply never supply it, so ``n_asleep`` stays 0.
    """

    size: int
    index: pd.DatetimeIndex
    rng: np.random.Generator
    home_probabilities: np.ndarray = field(
        default_factory=lambda: np.zeros((24, 2))
    )
    active_probabilities: np.ndarray = field(
        default_factory=lambda: np.zeros((24, 2))
    )
    asleep_probabilities: np.ndarray = field(
        default_factory=lambda: np.zeros((24, 2))
    )
    params: dict[str, Any] = field(default_factory=dict)


GeneratorFn = Callable[[OccupancyGenerationContext], pd.DataFrame]


def _activity_label(present: int, active: int) -> str:
    if present == 0:
        return "not_present"
    if active == 0:
        return "present_inactive"
    return "present_active"


def binomial_independent(ctx: OccupancyGenerationContext) -> pd.DataFrame:
    """Independent per-hour binomial draw:
    ``n_present ~ Binomial(size, p_home)``,
    ``n_active ~ Binomial(n_present, p_active)``. The original occupancy
    engine — kept as the default so existing behavior is reproducible bit
    for bit under the same seed.
    """
    n_present: list[int] = []
    n_active: list[int] = []
    n_asleep: list[int] = []
    activity: list[str] = []

    for ts in ctx.index:
        hour = ts.hour
        weekend_index = 1 if ts.weekday() >= 5 else 0

        p_home = ctx.home_probabilities[hour][weekend_index]
        p_active = ctx.active_probabilities[hour][weekend_index]
        p_asleep = ctx.asleep_probabilities[hour][weekend_index]

        present = int(ctx.rng.binomial(ctx.size, p_home))
        active = int(ctx.rng.binomial(present, p_active)) if present else 0
        inactive_present = present - active
        asleep = (
            int(ctx.rng.binomial(inactive_present, p_asleep))
            if inactive_present
            else 0
        )

        n_present.append(present)
        n_active.append(active)
        n_asleep.append(asleep)
        activity.append(_activity_label(present, active))

    return pd.DataFrame(
        {
            "n_present": n_present,
            "n_active": n_active,
            "n_asleep": n_asleep,
            "activity": activity,
        },
        index=ctx.index,
    )


def _binomial_pmf(n: int, p: float) -> np.ndarray:
    p = min(max(p, 0.0), 1.0)
    return np.array(
        [math.comb(n, k) * p**k * (1 - p) ** (n - k) for k in range(n + 1)],
        dtype=float,
    )


def markov_chain(ctx: OccupancyGenerationContext) -> pd.DataFrame:
    """Persistence-parameterized Markov chain over active-occupant count
    (0..size), inspired by the CREST/Richardson/tsorb transition-probability-
    matrix approach — but the transition matrix itself is **not** copied
    from any survey. It is synthesized at runtime from this repo's own
    validated ``active_probabilities``/``home_probabilities`` marginals,
    blended with a persistence term so occupancy state carries over between
    timesteps instead of independently re-randomizing every hour:

        row(state=i, hour=h) = persistence * onehot(i)
                              + (1 - persistence)
                                * Binomial_pmf(size, p_active[h])

    ``persistence`` (default 0.7) is read from ``ctx.params``. Present-but-
    inactive occupants are layered on top from the gap between
    ``home_probabilities`` and ``active_probabilities``.
    """
    persistence = float(ctx.params.get("persistence", 0.7))
    size = ctx.size
    n_states = size + 1
    states = np.arange(n_states)
    identity = np.eye(n_states)

    first = ctx.index[0]
    hour0, weekend0 = first.hour, 1 if first.weekday() >= 5 else 0
    current_state = int(
        ctx.rng.choice(
            states,
            p=_binomial_pmf(size, ctx.active_probabilities[hour0][weekend0]),
        )
    )

    n_present: list[int] = []
    n_active: list[int] = []
    n_asleep: list[int] = []
    activity: list[str] = []

    for ts in ctx.index:
        hour = ts.hour
        weekend_index = 1 if ts.weekday() >= 5 else 0
        p_active = ctx.active_probabilities[hour][weekend_index]
        p_home = ctx.home_probabilities[hour][weekend_index]
        p_asleep = ctx.asleep_probabilities[hour][weekend_index]

        target_pmf = _binomial_pmf(size, p_active)
        row_probs = (
            persistence * identity[current_state]
            + (1 - persistence) * target_pmf
        )
        row_probs = row_probs / row_probs.sum()
        current_state = int(ctx.rng.choice(states, p=row_probs))

        active = current_state
        extra_capacity = size - active
        p_extra_present = 0.0
        if extra_capacity > 0 and p_active < 1.0:
            p_extra_present = float(
                np.clip((p_home - p_active) / (1 - p_active), 0.0, 1.0)
            )
        extra_present = (
            int(ctx.rng.binomial(extra_capacity, p_extra_present))
            if extra_capacity > 0
            else 0
        )
        present = active + extra_present
        asleep = (
            int(ctx.rng.binomial(extra_present, p_asleep))
            if extra_present
            else 0
        )

        n_present.append(present)
        n_active.append(active)
        n_asleep.append(asleep)
        activity.append(_activity_label(present, active))

    return pd.DataFrame(
        {
            "n_present": n_present,
            "n_active": n_active,
            "n_asleep": n_asleep,
            "activity": activity,
        },
        index=ctx.index,
    )


def markov_chain_crest(ctx: OccupancyGenerationContext) -> pd.DataFrame:
    """Like :func:`markov_chain`, but the active-occupant-count transition
    is drawn from a real, precomposed hourly CREST transition-probability
    matrix instead of a synthesized persistence-blend formula.

    ``ctx.params`` must carry ``tpm_weekday``/``tpm_weekend``, each shaped
    ``(24, n, n)`` with ``n == ctx.size + 1`` (row-stochastic: row ``i`` is
    the distribution over next-hour active-occupant counts given ``i`` this
    hour) — see
    :func:`occupancy.households.crest_tpm.resolve_markov_chain_crest_params`,
    which builds these params from the real CREST workbook data. This
    function itself has no notion of "CREST" or "households" — it only
    consumes the params, exactly like :func:`hourly_occupancy_curve`
    consuming a generic ``occupancy_fraction`` param.

    Present-vs-active split and ``n_asleep`` are still derived from
    ``ctx.home_probabilities``/``active_probabilities``/
    ``asleep_probabilities`` exactly as in :func:`markov_chain` — CREST's
    tpm sheets model active-occupant-count transitions only, not the
    presence/sleep split, so this generator does not claim full CREST
    calibration of every output column, only the active-occupant
    transition dynamics.
    """
    tpm_weekday = ctx.params.get("tpm_weekday")
    tpm_weekend = ctx.params.get("tpm_weekend")
    if tpm_weekday is None or tpm_weekend is None:
        raise ValueError(
            "markov_chain_crest requires 'tpm_weekday' and 'tpm_weekend' "
            "in generator_params (see "
            "occupancy.households.crest_tpm.resolve_markov_chain_crest_params)"
        )
    tpm_weekday = np.asarray(tpm_weekday, dtype=float)
    tpm_weekend = np.asarray(tpm_weekend, dtype=float)
    n_states = ctx.size + 1
    expected_shape = (24, n_states, n_states)
    if (
        tpm_weekday.shape != expected_shape
        or tpm_weekend.shape != expected_shape
    ):
        raise ValueError(
            f"tpm_weekday/tpm_weekend must have shape {expected_shape} "
            f"(24, ctx.size + 1, ctx.size + 1); got "
            f"{tpm_weekday.shape} / {tpm_weekend.shape}"
        )

    states = np.arange(n_states)

    first = ctx.index[0]
    hour0, weekend0 = first.hour, 1 if first.weekday() >= 5 else 0
    current_state = int(
        ctx.rng.choice(
            states,
            p=_binomial_pmf(
                ctx.size, ctx.active_probabilities[hour0][weekend0]
            ),
        )
    )

    n_present: list[int] = []
    n_active: list[int] = []
    n_asleep: list[int] = []
    activity: list[str] = []

    for ts in ctx.index:
        hour = ts.hour
        weekend_index = 1 if ts.weekday() >= 5 else 0
        p_home = ctx.home_probabilities[hour][weekend_index]
        p_active = ctx.active_probabilities[hour][weekend_index]
        p_asleep = ctx.asleep_probabilities[hour][weekend_index]

        tpm = tpm_weekend if weekend_index else tpm_weekday
        row_probs = tpm[hour, current_state]
        current_state = int(ctx.rng.choice(states, p=row_probs))

        active = current_state
        extra_capacity = ctx.size - active
        p_extra_present = 0.0
        if extra_capacity > 0 and p_active < 1.0:
            p_extra_present = float(
                np.clip((p_home - p_active) / (1 - p_active), 0.0, 1.0)
            )
        extra_present = (
            int(ctx.rng.binomial(extra_capacity, p_extra_present))
            if extra_capacity > 0
            else 0
        )
        present = active + extra_present
        asleep = (
            int(ctx.rng.binomial(extra_present, p_asleep))
            if extra_present
            else 0
        )

        n_present.append(present)
        n_active.append(active)
        n_asleep.append(asleep)
        activity.append(_activity_label(present, active))

    return pd.DataFrame(
        {
            "n_present": n_present,
            "n_active": n_active,
            "n_asleep": n_asleep,
            "activity": activity,
        },
        index=ctx.index,
    )


def fixed_schedule(ctx: OccupancyGenerationContext) -> pd.DataFrame:
    """Deterministic open/close-hours occupancy ramp with light stochastic
    noise — the typical shape for service buildings (offices, schools,
    shops) rather than the residential presence models above.

    ``ctx.params`` keys: ``open_hour``/``close_hour`` (weekday, default
    8-18), ``weekend_open_hour``/``weekend_close_hour`` (default = weekday
    hours), ``closed_weekends`` (bool, default False), ``closed_months``
    (list of 1-12 month numbers with zero occupancy, e.g. school summer
    holidays), ``peak_occupancy_fraction`` (default 0.8 of ``size``),
    ``active_fraction`` (default 0.9 of present occupants), ``noise``
    (stdev of occupancy-fraction jitter, default 0.1).
    """
    params = ctx.params
    open_hour = int(params.get("open_hour", 8))
    close_hour = int(params.get("close_hour", 18))
    weekend_open_hour = int(params.get("weekend_open_hour", open_hour))
    weekend_close_hour = int(params.get("weekend_close_hour", close_hour))
    closed_weekends = bool(params.get("closed_weekends", False))
    closed_months = set(params.get("closed_months", []))
    peak_fraction = float(params.get("peak_occupancy_fraction", 0.8))
    active_fraction = float(params.get("active_fraction", 0.9))
    noise = float(params.get("noise", 0.1))

    hours = ctx.index.hour.to_numpy()
    is_weekend = ctx.index.weekday >= 5

    open_h = np.where(is_weekend, weekend_open_hour, open_hour)
    close_h = np.where(is_weekend, weekend_close_hour, close_hour)
    is_open = (hours >= open_h) & (hours < close_h)
    if closed_weekends:
        is_open &= ~is_weekend
    if closed_months:
        is_open &= ~np.isin(ctx.index.month.to_numpy(), list(closed_months))

    jitter = ctx.rng.normal(loc=0.0, scale=noise, size=len(hours))
    occupancy_fraction = np.clip(
        np.where(is_open, peak_fraction + jitter, 0.0), 0.0, 1.0
    )

    n_present = ctx.rng.binomial(ctx.size, occupancy_fraction)
    n_active = np.where(
        n_present > 0,
        ctx.rng.binomial(n_present, active_fraction),
        0,
    )
    inactive_present = n_present - n_active
    weekend_index = is_weekend.astype(int)
    p_asleep = ctx.asleep_probabilities[hours, weekend_index]
    n_asleep = np.where(
        inactive_present > 0,
        ctx.rng.binomial(inactive_present, p_asleep),
        0,
    )
    activity = [
        _activity_label(int(p), int(a))
        for p, a in zip(n_present, n_active, strict=True)
    ]

    return pd.DataFrame(
        {
            "n_present": n_present,
            "n_active": n_active,
            "n_asleep": n_asleep,
            "activity": activity,
        },
        index=ctx.index,
    )


def hourly_occupancy_curve(ctx: OccupancyGenerationContext) -> pd.DataFrame:
    """Occupancy driven by an explicit 24-hour occupancy-fraction table
    (weekday/weekend), rather than a single open/close window + flat peak
    like :func:`fixed_schedule`. Matches the shape of published reference
    schedules (e.g. DOE/ASHRAE 90.1 prototype-building
    ``Schedule:Compact`` fractional schedules) for building types whose
    day-shape a single rectangle can't represent — a hotel's near-constant
    overnight guest presence plus checkout/check-in peaks, for instance.

    ``ctx.params`` keys: ``occupancy_fraction`` (required — 24 rows of
    ``[weekday, weekend]`` fractions of ``size``, same shape convention as
    ``home_probabilities``), ``active_fraction`` (default 0.5),
    ``closed_months`` (as in :func:`fixed_schedule`), ``noise`` (stdev of
    additive jitter, default 0.05). ``ctx.asleep_probabilities`` feeds
    ``n_asleep`` exactly as in the other generators.
    """
    params = ctx.params
    if "occupancy_fraction" not in params:
        raise ValueError(
            "hourly_occupancy_curve requires 'occupancy_fraction' "
            "(24 rows of [weekday, weekend] fractions) in generator_params"
        )
    curve = np.asarray(params["occupancy_fraction"], dtype=float)
    if curve.shape != (24, 2):
        raise ValueError("occupancy_fraction must have shape (24, 2)")
    active_fraction = float(params.get("active_fraction", 0.5))
    noise = float(params.get("noise", 0.05))
    closed_months = set(params.get("closed_months", []))

    hours = ctx.index.hour.to_numpy()
    is_weekend = ctx.index.weekday >= 5
    weekend_index = is_weekend.astype(int)
    base_fraction = curve[hours, weekend_index]
    if closed_months:
        closed = np.isin(ctx.index.month.to_numpy(), list(closed_months))
        base_fraction = np.where(closed, 0.0, base_fraction)

    jitter = ctx.rng.normal(loc=0.0, scale=noise, size=len(hours))
    occupancy_fraction = np.clip(base_fraction + jitter, 0.0, 1.0)

    n_present = ctx.rng.binomial(ctx.size, occupancy_fraction)
    n_active = np.where(
        n_present > 0,
        ctx.rng.binomial(n_present, active_fraction),
        0,
    )
    inactive_present = n_present - n_active
    p_asleep = ctx.asleep_probabilities[hours, weekend_index]
    n_asleep = np.where(
        inactive_present > 0,
        ctx.rng.binomial(inactive_present, p_asleep),
        0,
    )
    activity = [
        _activity_label(int(p), int(a))
        for p, a in zip(n_present, n_active, strict=True)
    ]

    return pd.DataFrame(
        {
            "n_present": n_present,
            "n_active": n_active,
            "n_asleep": n_asleep,
            "activity": activity,
        },
        index=ctx.index,
    )


_GENERATORS: dict[str, GeneratorFn] = {
    "binomial_independent": binomial_independent,
    "markov_chain": markov_chain,
    "markov_chain_crest": markov_chain_crest,
    "fixed_schedule": fixed_schedule,
    "hourly_occupancy_curve": hourly_occupancy_curve,
}


def register_generator(name: str, fn: GeneratorFn) -> None:
    """Register a new occupancy-generation strategy under ``name``."""
    _GENERATORS[name] = fn


def get_generator(name: str) -> GeneratorFn:
    try:
        return _GENERATORS[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown occupancy generator strategy {name!r}. "
            f"Registered: {sorted(_GENERATORS)}"
        ) from exc

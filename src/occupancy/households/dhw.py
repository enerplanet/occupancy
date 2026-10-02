"""Domestic hot water (DHW) tapping-event generation for households.

Answers buem's ``dhw_cooking_heat_handoff.md`` ask #1 ("expose DHW draw
volumes"), gated on the literature review and the design questions the
user raised about it -- see ``docs/dhw/`` for the full review, source
list, and design rationale this module implements. This docstring covers
only the mechanics; read ``docs/dhw/design.md`` before changing the
method.

**Scope, deliberately liters-only.** Per this repo's ownership-boundary
convention (``CLAUDE.md``): occupancy owns occupant/equipment *behavior*
-- what gets drawn, and when; buem owns the temperature/delta-T/energy
math, once it has a DHW term to do that math for (it does not yet -- see
``docs/dhw/buem_engine_reference.md``). :func:`generate_dhw_draws`
therefore returns liters, never kWh.

**Single point of configuration.** Every deterministic number this
module uses -- fixture ownership rates, flow rates, durations, reference
event frequencies, the reference household size they're all calibrated
to -- lives in ``dhw_tapping_categories.csv`` (see that file's own header
for full provenance), not scattered across this module as Python
constants. Editing that one file -- a row's numbers, or adding a new row
entirely -- is sufficient on its own; no matching Python or JSON change
is needed. ``volume_per_event_l`` is deliberately *not* a column in that
file: it is derived here from ``flow_rate_l_per_min * duration_min``, so
there is exactly one place (the CSV) where a fixture's volume can drift
out of sync with its flow rate and duration -- nowhere, because it is
never stored twice. :func:`load_tapping_categories` validates the table
on every load (required columns present, one shared
``reference_num_persons``, positive flow/duration, ownership
probabilities in ``[0, 1]``) so a broken hand-edit fails loudly at load
time instead of producing silently-wrong output.

**Method, in one paragraph.** For each tapping-category row, a fixture
is stochastically owned or not (seeded Bernoulli draw against
``ownership_probability`` -- real, per-fixture data, not a household-size
proxy). If owned, the row's reference daily event count is scaled by
this household's ``num_persons`` relative to the table's
``reference_num_persons``, a Poisson draw turns that expected count into
an actual whole number of events for the profile's duration, and each
event is (a) assigned an hour by weighted random choice against a timing
envelope, and (b) assigned a volume by a Poisson draw centred on the
row's derived mean volume (matching the stochastic-volume approach the
primary source's own runtime model uses -- see the CSV header -- rather
than a fixed volume repeated every time). Timing envelopes are looked up
by the row's ``activity_link`` in a small registry
(:data:`_TIMING_ENVELOPES` / :func:`register_timing_envelope`, mirroring
:mod:`occupancy.core.equipment`'s ``register_strategy`` pattern): kitchen
-sink draws (``"cooking"``) reuse the ``cooking_active`` signal
(:mod:`occupancy.core.equipment`'s kitchen category); everything else
(``"washing_and_dressing"``) uses a transition-weighted occupancy
envelope (see :func:`_washing_and_dressing_envelope`) -- not a flat
``n_active`` average, since real washing-and-dressing activity clusters
at wake-up and bedtime rather than spreading evenly across every hour
someone happens to be present. A custom ``tapping_categories`` table
introducing a new ``activity_link`` value that has no registered
envelope still works: it falls back to plain ``n_active``, a documented,
honest default rather than a silent misrouting.

**Status: first-pass, illustrative** -- same disclosure standard as this
repo's other early-stage additions (``core/disaggregation.py``,
``equipment.json``'s hourly weight shapes). Real, sourced numbers
throughout; the genuinely unsourced piece is the hybrid apportionment
used to derive ``events_per_day_reference`` in the bundled CSV -- see
that file's own header and ``docs/dhw/design.md``.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from occupancy.core.loader import load_csv_resource
from occupancy.core.seed import derive_default_seed

_TAPPING_CATEGORIES_PACKAGE = "occupancy.households"
_TAPPING_CATEGORIES_RESOURCE = "data/dhw_tapping_categories.csv"

_REQUIRED_COLUMNS = {
    "fixture_label",
    "activity_link",
    "ownership_probability",
    "flow_rate_l_per_min",
    "duration_min",
    "events_per_day_reference",
    "reference_num_persons",
}

#: A timing-envelope function maps (n_active, cooking_signal) -> an
#: hourly array of non-negative weights used to place draw events. Both
#: arguments are always the full arrays for the profile being generated;
#: cooking_signal is ``None`` when the caller didn't supply one.
TimingEnvelope = Callable[[np.ndarray, "np.ndarray | None"], np.ndarray]


def _cooking_envelope(
    n_active: np.ndarray, cooking_signal: np.ndarray | None
) -> np.ndarray:
    """Kitchen-sink draws follow the real ``cooking_active`` signal when
    supplied; falls back to general active occupancy otherwise -- still
    occupancy-driven, just without the finer kitchen-specific timing."""
    return cooking_signal if cooking_signal is not None else n_active


def _washing_and_dressing_envelope(
    n_active: np.ndarray, cooking_signal: np.ndarray | None
) -> np.ndarray:
    """basin/shower/bath draws cluster around wake-up and bedtime -- the
    hours where the number of active occupants *changes* -- rather than
    spreading evenly across every hour someone happens to be active.
    This reuses Richardson et al. (2008)'s own validation concept
    (counting "people becoming active"/"people becoming inactive"
    transitions, their Figs. 33-34) as a timing proxy: no new data, just
    a derived transformation of the ``n_active`` column this repo already
    generates. Combined additively with ``n_active`` itself so hours of
    sustained (not just changing) presence still carry some weight -- a
    household doesn't only wash up at the exact moment someone wakes."""
    transitions = np.abs(np.diff(n_active, prepend=n_active[0]))
    return n_active + transitions


def _default_envelope(
    n_active: np.ndarray, cooking_signal: np.ndarray | None
) -> np.ndarray:
    return n_active


_TIMING_ENVELOPES: dict[str, TimingEnvelope] = {
    "cooking": _cooking_envelope,
    "washing_and_dressing": _washing_and_dressing_envelope,
}


def register_timing_envelope(
    activity_link: str, envelope: TimingEnvelope
) -> None:
    """Register a timing-envelope function for a custom
    ``activity_link`` value, so a user-edited ``dhw_tapping_categories.csv``
    can introduce a new category (e.g. ``"outdoor_tap"``,
    ``"laundry_presoak"``) and have :func:`generate_dhw_draws` route its
    timing through real logic instead of silently falling back to plain
    ``n_active``. Mirrors :func:`occupancy.core.equipment.register_strategy`'s
    registry pattern."""
    _TIMING_ENVELOPES[activity_link] = envelope


def _prepare_tapping_categories(table: pd.DataFrame) -> pd.DataFrame:
    """Validate a tapping-category table and derive
    ``volume_per_event_l``. Shared by :func:`load_tapping_categories` and
    by :func:`generate_dhw_draws` when a caller supplies a custom table
    directly, so both paths get the same checks."""
    missing = _REQUIRED_COLUMNS - set(table.columns)
    if missing:
        raise ValueError(
            "dhw_tapping_categories table is missing required column(s): "
            f"{sorted(missing)}"
        )

    table = table.copy()

    if (table["flow_rate_l_per_min"] <= 0).any() or (
        table["duration_min"] <= 0
    ).any():
        raise ValueError(
            "dhw_tapping_categories table: flow_rate_l_per_min and "
            "duration_min must be positive for every row"
        )
    ownership = table["ownership_probability"]
    if ((ownership < 0) | (ownership > 1)).any():
        raise ValueError(
            "dhw_tapping_categories table: ownership_probability must be "
            "between 0 and 1 for every row"
        )

    reference_num_persons_values = table["reference_num_persons"].unique()
    if len(reference_num_persons_values) != 1:
        raise ValueError(
            "dhw_tapping_categories table: every row must share the same "
            "reference_num_persons (the whole table is calibrated to one "
            f"reference household size); found {sorted(reference_num_persons_values)}"
        )

    table["volume_per_event_l"] = (
        table["flow_rate_l_per_min"] * table["duration_min"]
    )
    return table


def load_tapping_categories() -> pd.DataFrame:
    """Load and validate the bundled, editable DHWcalc/CREST-sourced
    tapping-category reference table (see the CSV's own header for full
    provenance). Returns a fresh, validated copy each call, so a caller
    may freely mutate the result (e.g. to override a row, or hand a
    variant to :func:`generate_dhw_draws` via ``tapping_categories=``)
    without affecting other callers. Raises ``ValueError`` with a
    specific, actionable message if the table has been hand-edited into
    an inconsistent state (missing columns, non-positive flow/duration,
    out-of-range ownership probabilities, or disagreeing
    ``reference_num_persons`` values)."""
    table = load_csv_resource(
        _TAPPING_CATEGORIES_PACKAGE, _TAPPING_CATEGORIES_RESOURCE
    )
    return _prepare_tapping_categories(table)


def _profile_year(profile: pd.DataFrame) -> int:
    """Best-effort extraction of a representative year from ``profile``'s
    index, for default-seed derivation only. Falls back to ``0`` (not an
    error) if the index isn't datetime-like -- year is one of several
    inputs distinguishing the derived default seed, not a hard
    requirement of :func:`generate_dhw_draws`'s contract (which only
    needs ``len(profile)``, not timestamp values, for anything else)."""
    try:
        return int(profile.index[0].year)
    except AttributeError:
        return 0


def generate_dhw_draws(
    profile: pd.DataFrame,
    *,
    num_persons: int,
    cooking_active: pd.Series | None = None,
    tapping_categories: pd.DataFrame | None = None,
    seed: int | np.random.Generator | None = None,
) -> pd.DataFrame:
    """Generate stochastic hourly DHW draw volumes in liters.

    Returns a DataFrame aligned to ``profile``'s index with one
    ``dhw_liters_<fixture_label>`` column per tapping-category row (e.g.
    ``dhw_liters_basin``, ``dhw_liters_kitchen_sink``,
    ``dhw_liters_shower``, ``dhw_liters_bath`` for the bundled default
    table) plus a summed ``dhw_liters_total`` column. A fixture a
    household doesn't own (per the table's ``ownership_probability``)
    contributes an all-zero column for that run.

    Parameters
    ----------
    profile:
        An hourly-indexed occupancy profile carrying at least an
        ``n_active`` column (e.g. ``HouseholdProfile.get_profile()``'s
        output, or the equivalent from
        ``ElectricityConsumptionProfile``). Length must be a whole
        number of days (8760 or 8784 for a full year).
    num_persons:
        Used to scale each owned category's reference daily event count
        relative to the tapping-category table's own
        ``reference_num_persons`` column; see this module's docstring.
    cooking_active:
        Optional boolean/0-1 Series aligned to ``profile``, e.g.
        ``ElectricityConsumptionProfile.get_profile()["cooking_active"]``.
        Drives the timing of ``"cooking"``-linked categories (kitchen-sink
        draws). If omitted, those categories fall back to the same
        ``n_active`` envelope used as the default for other categories --
        still occupancy-driven, just without the finer kitchen-specific
        timing.
    tapping_categories:
        Optional override of the bundled reference table (same shape as
        :func:`load_tapping_categories`'s return value, minus the derived
        ``volume_per_event_l`` column) -- e.g. a variant with an added or
        edited row, or an entirely different reference dataset. Validated
        the same way as the bundled table. Defaults to loading the
        bundled CSV.
    seed:
        Owns this function's randomization the same way ``seed=`` already
        works on ``HouseholdProfile``/``ServiceBuildingProfile`` -- a
        caller never needs to construct or manage a raw
        ``np.random.Generator`` itself. Three forms are accepted:

        - ``None`` (the default): a deterministic seed is derived from
          ``num_persons`` and ``profile``'s own year via
          :func:`occupancy.core.seed.derive_default_seed` (``kind="dhw"``,
          distinct from any ``HouseholdProfile``'s own default seed, so
          calling this on a household's profile does not replay the same
          bit-stream that household's own generation already consumed).
          Same inputs always reproduce the same DHW draws; a caller
          wanting a specific household's draws to also vary
          independently across repeat calls should pass an explicit
          ``seed=`` (e.g. offset from ``household.seed``).
        - An ``int``: used directly via ``np.random.default_rng(seed)``,
          the same convention as every other explicit ``seed=`` in this
          repo.
        - An ``np.random.Generator``: used as-is (advanced in place across
          this call) -- an escape hatch for tests or callers who already
          manage their own generator lifecycle; this repo's own test
          suite uses this form.
    """
    if num_persons <= 0:
        raise ValueError(f"num_persons must be positive, got {num_persons}")
    num_hours = len(profile)
    if num_hours == 0 or num_hours % 24 != 0:
        raise ValueError(
            "generate_dhw_draws expects an hourly profile whose length "
            f"is a whole number of days; got {num_hours} rows"
        )
    num_days = num_hours / 24

    if isinstance(seed, np.random.Generator):
        rng = seed
    else:
        if seed is None:
            seed = derive_default_seed(
                kind="dhw",
                size=num_persons,
                year=_profile_year(profile),
                archetype="",
                region="",
            )
        rng = np.random.default_rng(seed)

    if tapping_categories is None:
        tapping_categories = load_tapping_categories()
    else:
        tapping_categories = _prepare_tapping_categories(tapping_categories)

    reference_num_persons = float(
        tapping_categories["reference_num_persons"].iloc[0]
    )

    n_active = profile["n_active"].to_numpy(dtype=float)
    cooking_signal = (
        cooking_active.to_numpy(dtype=float)
        if cooking_active is not None
        else None
    )

    result = pd.DataFrame(index=profile.index)
    total = np.zeros(num_hours)

    for row in tapping_categories.itertuples(index=False):
        column = np.zeros(num_hours)
        owned = bool(rng.random() < row.ownership_probability)

        if owned:
            scale = num_persons / reference_num_persons
            expected_events = row.events_per_day_reference * scale * num_days
            n_events = int(rng.poisson(expected_events))

            if n_events > 0:
                envelope_fn = _TIMING_ENVELOPES.get(
                    row.activity_link, _default_envelope
                )
                weights = envelope_fn(n_active, cooking_signal)
                weight_sum = weights.sum()
                if weight_sum <= 0:
                    # No timing signal at all (e.g. zero active occupancy
                    # anywhere in the profile, which shouldn't normally
                    # happen) -- fall back to a flat hourly distribution
                    # rather than silently dropping every draw.
                    weights = np.ones(num_hours)
                    weight_sum = weights.sum()

                hours = rng.choice(
                    num_hours, size=n_events, p=weights / weight_sum
                )
                volumes = rng.poisson(row.volume_per_event_l, size=n_events)
                np.add.at(column, hours, volumes.astype(float))

        result[f"dhw_liters_{row.fixture_label}"] = column
        total += column

    result["dhw_liters_total"] = total
    return result

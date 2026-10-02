"""Estimate per-equipment usage intensity from a supplied whole-building
electricity profile.

Answers buem's long-deferred "back-calculate equipment usage from an
externally-supplied elecLoad" ask (see
``d:/test/buem/.claude/occupancy_module_activities.md`` item 3 and this
repo's own ``.claude/open.md`` "pylovo/multi-profile" note, direction 2's
substitution-vs-inference distinction). :func:`occupancy.core.buem_adapter.
to_buem_profiles`'s existing ``elec_load=`` parameter is, and remains, pure
wholesale substitution — this module is a separate, optional preprocessing
step a caller can run *before* constructing a fresh
:class:`~occupancy.households.electricity.ElectricityConsumptionProfile` /
:class:`~occupancy.services_buildings.building_profile.ServiceBuildingProfile`
with the fitted ``equipment=`` table, if a per-equipment breakdown is
wanted. It does **not** change ``to_buem_profiles``'s contract or feed a
revised ``Q_ig`` automatically — that remains an explicit choice for the
caller, not something this module does on its own.

**Method**: every registered equipment trigger strategy
(:mod:`occupancy.core.equipment`) has a deterministic closed-form expected
value (see ``get_expected_value_strategy``) — no simulation is needed to
build a basis template per item. :func:`estimate_equipment_usage` stacks
those templates into a matrix ``X`` (columns = items, rows = hours) and
solves ``elec_load ~= X @ c`` for non-negative per-item intensity
coefficients ``c`` via ``scipy.optimize.nnls`` (the standard Lawson-Hanson
non-negative-least-squares algorithm — chosen over a hand-rolled solver so
this is a recognizable, trustworthy technique, not a bespoke one).

**Caveats — this is illustrative estimation, not a validated calibration**
(same disclosure standard this repo already applies to its other
illustrative data, e.g. ``households/data/equipment.json``'s hourly weight
shapes): identifiability is limited (equipment items with similarly-shaped
templates are collinear — only their coefficient *sum* is reliable, not the
individual split); the fit is against each item's *expected-value* template,
not the true per-draw stochastic signal, so recovered coefficients describe
typical/average intensity, not an exact minute-by-minute disaggregation;
and ``sessions_per_week``'s expected-value template
(:func:`occupancy.core.equipment.expected_sessions_per_week`) spreads
probability mass uniformly across eligible hours, discarding the real
placement's clustering/spacing.
"""

from __future__ import annotations

import warnings
from dataclasses import replace

import numpy as np
import pandas as pd
from scipy.optimize import nnls

from occupancy.core.equipment import (
    EquipmentContext,
    EquipmentSpec,
    get_expected_value_strategy,
)


def _build_template_matrix(
    equipment_table: dict[str, EquipmentSpec],
    profile: pd.DataFrame,
) -> tuple[list[str], np.ndarray]:
    """Return (item_names, X) where X[:, i] is item_names[i]'s
    expected-value power template over profile's index. Items whose
    strategy has no registered expected-value counterpart are skipped
    (with a warning) rather than raising, since a caller's equipment table
    may include custom strategies added via
    :func:`occupancy.core.equipment.register_strategy` without a matching
    :func:`~occupancy.core.equipment.register_expected_value_strategy`
    call."""
    ctx = EquipmentContext(
        profile=profile,
        rng=np.random.default_rng(0),  # unused by any expected-value fn
        hours=profile.index.hour.to_numpy(),
        is_weekend=profile.index.weekday >= 5,
        weekday_index=profile.index.weekday.to_numpy(),
    )
    names: list[str] = []
    columns: list[np.ndarray] = []
    for name, spec in equipment_table.items():
        if not spec.enabled:
            continue
        try:
            expected_value_fn = get_expected_value_strategy(spec.strategy)
        except ValueError:
            warnings.warn(
                f"equipment item {name!r} uses strategy {spec.strategy!r}, "
                "which has no registered expected-value counterpart -- "
                "skipping it in the disaggregation basis. Register one via "
                "occupancy.core.equipment.register_expected_value_strategy "
                "if this item should be included.",
                stacklevel=2,
            )
            continue
        names.append(name)
        columns.append(expected_value_fn(spec, ctx))
    if not names:
        raise ValueError(
            "No equipment_table item has a registered expected-value "
            "strategy -- nothing to fit against."
        )
    return names, np.column_stack(columns)


def estimate_equipment_usage(
    elec_load: pd.Series,
    profile: pd.DataFrame,
    equipment_table: dict[str, EquipmentSpec],
    *,
    regularization: float = 0.0,
    min_coefficient: float = 1e-6,
) -> dict[str, EquipmentSpec]:
    """Fit non-negative per-item usage-intensity coefficients against a
    supplied whole-building ``elec_load`` series.

    Parameters
    ----------
    elec_load:
        Hourly whole-building power series (kW), reindexed onto
        ``profile.index`` (same alignment convention as
        :func:`occupancy.core.buem_adapter.to_buem_profiles`'s
        ``elec_load`` parameter). Raises ``ValueError`` if it doesn't cover
        ``profile.index`` after reindexing.
    profile:
        A real, already-generated occupancy profile (``n_present``/
        ``n_active`` columns) for the *same* household/building the
        equipment table belongs to -- e.g.
        ``HouseholdProfile(...).get_profile()`` or
        ``ServiceBuildingProfile(...).get_profile()``. Disaggregation runs
        *alongside* a real occupancy generation, exactly like
        ``to_buem_profiles(elec_load=...)`` already does for
        ``Q_ig``/``occ_nothome``/``occ_sleeping``.
    equipment_table:
        The candidate equipment items to fit against, e.g.
        ``ElectricityConsumptionProfile(household).get_equipment_table()``
        or ``ServiceBuildingProfile(...).get_equipment_table()``.
    regularization:
        When > 0, pulls each item's fitted coefficient toward its
        ``ownership_probability`` prior (ridge-style), by augmenting the
        least-squares system with one extra row per item. Useful when the
        system is underdetermined (more items than the aggregate curve can
        genuinely identify) to avoid an arbitrary all-or-nothing split
        between collinear items.
    min_coefficient:
        Fitted coefficients at or below this are treated as "not present"
        and dropped from the result (same "absent key = excluded"
        convention as the ``equipment=`` parameter on
        ``ElectricityConsumptionProfile``/``ServiceBuildingProfile``).

    Returns
    -------
    A new ``dict[str, EquipmentSpec]`` containing only the items whose
    fitted coefficient exceeds ``min_coefficient``. Both ``rated_power_kw``
    and ``standby_power_kw`` are scaled by the fitted coefficient (exact,
    since every expected-value template is homogeneous of degree 1 in
    those two fields) and ``ownership_probability`` is forced to ``1.0``
    (the fitted intensity already *is* the estimate -- a probability field
    left below 1.0 would trigger a fresh Bernoulli re-draw in
    ``ElectricityConsumptionProfile._owned_by_name()`` on the next
    construction, discarding the fit). The result slots directly into
    ``equipment=`` on ``ElectricityConsumptionProfile`` or
    ``ServiceBuildingProfile``.
    """
    aligned = elec_load.reindex(profile.index)
    if aligned.isna().any():
        raise ValueError(
            "elec_load does not cover profile's index after reindexing -- "
            "pass a series aligned to profile.index."
        )

    names, template = _build_template_matrix(equipment_table, profile)
    target = aligned.to_numpy(dtype=float)

    if regularization > 0:
        priors = np.array(
            [equipment_table[name].ownership_probability for name in names]
        )
        reg_rows = regularization * np.eye(len(names))
        template = np.vstack([template, reg_rows])
        target = np.concatenate([target, regularization * priors])

    coefficients, _residual = nnls(template, target)

    fitted: dict[str, EquipmentSpec] = {}
    for name, coefficient in zip(names, coefficients, strict=True):
        if coefficient <= min_coefficient:
            continue
        spec = equipment_table[name]
        fitted[name] = replace(
            spec,
            rated_power_kw=spec.rated_power_kw * coefficient,
            standby_power_kw=spec.standby_power_kw * coefficient,
            ownership_probability=1.0,
        )
    return fitted

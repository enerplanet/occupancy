"""Household-composition archetype registry.

Each archetype is a JSON file under ``data/archetypes/`` — adding a new one
(a different composition, or the same composition for a new region) is a
config addition, not a code change. See :func:`register_archetype` for the
rare case of registering one programmatically instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from occupancy.core.loader import iter_json_resources, load_json_resource

_PACKAGE = "occupancy.households"
_ARCHETYPES_DIR = "data/archetypes"


@dataclass(frozen=True)
class ArchetypeSpec:
    """One household-composition archetype."""

    id: str
    description: str
    region: str
    num_persons_default: int
    generator: str
    generator_params: dict[str, Any]
    home_probabilities: np.ndarray
    active_probabilities: np.ndarray
    equipment_overrides: dict[str, dict[str, np.ndarray]] = field(
        default_factory=dict
    )
    # Conditional on being present-but-inactive: probability of being asleep
    # rather than just quietly awake. Feeds `n_asleep` in
    # `core/occupancy_engine.py`'s generator output, in turn buem's
    # `occ_sleeping` via `core/buem_adapter.py`. Defaults to all-zero (no
    # sleep signal) for any archetype JSON that doesn't define it.
    asleep_probabilities: np.ndarray = field(
        default_factory=lambda: np.zeros((24, 2))
    )
    # Heat gain per occupant [kW], building-total (see
    # `core/buem_adapter.py` module docstring for units/rationale/sources).
    # Defaults match that module's own fallback constants.
    heat_gain_present_kw: float = 0.100
    heat_gain_active_kw: float = 0.150
    # Area-normalized equipment/lighting internal-gain density [W/m^2],
    # building-total. Optional -- `None` (the default for every archetype
    # today) means "no area-driven component", preserving the pre-existing
    # per-occupant-only behavior exactly. See `core/buem_adapter.py`'s
    # `to_buem_profiles(floor_area_m2=..., gain_w_per_m2=...)` for how this
    # blends with `heat_gain_present_kw`/`heat_gain_active_kw` rather than
    # replacing them (buem's `occupancy_gains_handoff.md` Gap 1). Left unset
    # for households deliberately -- a household's per-occupant gain is
    # already a reasonable physical assumption and dwelling floor area
    # correlates loosely with household size; this field exists mainly for
    # service-building types where that correlation breaks down.
    gain_w_per_m2: float | None = None


def _parse_archetype(data: dict[str, Any]) -> ArchetypeSpec:
    overrides: dict[str, dict[str, np.ndarray]] = {}
    for name, override in data.get("equipment_overrides", {}).items():
        overrides[name] = {
            "weekday": np.asarray(
                override.get("weekday", [1.0] * 24), dtype=float
            ),
            "weekend": np.asarray(
                override.get("weekend", [1.0] * 24), dtype=float
            ),
        }
    asleep = data.get("asleep_probabilities")
    return ArchetypeSpec(
        id=data["id"],
        description=data.get("description", ""),
        region=data.get("region", "NL"),
        num_persons_default=int(data.get("num_persons_default", 1)),
        generator=data.get("generator", "binomial_independent"),
        generator_params=data.get("generator_params", {}),
        home_probabilities=np.asarray(data["home_probabilities"], dtype=float),
        active_probabilities=np.asarray(
            data["active_probabilities"], dtype=float
        ),
        equipment_overrides=overrides,
        asleep_probabilities=(
            np.asarray(asleep, dtype=float)
            if asleep is not None
            else np.zeros((24, 2))
        ),
        heat_gain_present_kw=float(data.get("heat_gain_present_kw", 0.100)),
        heat_gain_active_kw=float(data.get("heat_gain_active_kw", 0.150)),
        gain_w_per_m2=(
            float(data["gain_w_per_m2"])
            if data.get("gain_w_per_m2") is not None
            else None
        ),
    )


def _load_all() -> dict[str, ArchetypeSpec]:
    archetypes: dict[str, ArchetypeSpec] = {}
    for filename in iter_json_resources(_PACKAGE, _ARCHETYPES_DIR):
        data = load_json_resource(_PACKAGE, f"{_ARCHETYPES_DIR}/{filename}")
        spec = _parse_archetype(data)
        archetypes[spec.id] = spec
    return archetypes


HOUSEHOLD_ARCHETYPES: dict[str, ArchetypeSpec] = _load_all()


def register_archetype(spec: ArchetypeSpec) -> None:
    """Register a new household archetype (e.g. from a future reference
    occupancy module) under ``spec.id``."""
    HOUSEHOLD_ARCHETYPES[spec.id] = spec


def get_archetype(name: str) -> ArchetypeSpec:
    try:
        return HOUSEHOLD_ARCHETYPES[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown household archetype {name!r}. "
            f"Registered: {sorted(HOUSEHOLD_ARCHETYPES)}"
        ) from exc

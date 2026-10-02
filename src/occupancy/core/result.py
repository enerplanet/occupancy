from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pandas as pd


@dataclass
class OccupancyResult:
    """Typed output contract shared by household and service-building
    profiles."""

    profile: pd.DataFrame
    year: int
    num_persons: int
    building_type: str = "household"
    region: str = "NL"
    # Per-occupant heat gain [kW], carried from the originating archetype/
    # building-type spec so `core.buem_adapter.to_buem_profiles()` can use
    # a type-appropriate value instead of its own module-level fallback.
    # None means "no per-type value available -- use the adapter's default".
    heat_gain_present_kw: float | None = None
    heat_gain_active_kw: float | None = None
    # Area-normalized equipment/lighting internal-gain density [W/m^2],
    # carried from the originating archetype/building-type spec the same
    # way as `heat_gain_present_kw`/`heat_gain_active_kw`. None means "no
    # per-type value available" -- `to_buem_profiles(floor_area_m2=...)`
    # then requires an explicit `gain_w_per_m2` override or raises.
    gain_w_per_m2: float | None = None
    generated_at: str = field(
        default_factory=lambda: datetime.now(tz=UTC).isoformat()
    )

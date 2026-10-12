"""Multi-dwelling building aggregation: N distinct households summed,
instead of one household scaled by a dwelling count.

Closes `UU-BUEM/occupancy#14
<https://github.com/UU-BUEM/occupancy/issues/14>`_: a building with N
dwellings was previously modeled downstream as N copies of one generated
``HouseholdProfile`` -- every dwelling peaking at the same hour, so the
block's aggregate peak was N times one household's peak regardless of N
(measured peak/mean ratio ~17 at N=1, 5 or 20 for one real building type/
year). :class:`MultiDwellingProfile` instead draws
``n = min(round(dwellings), cap)`` genuinely distinct households (each its
own seed, so its own draw of occupancy/electricity/DHW timing), sums their
occupancy fractions, electricity and DHW draws, and scales the sum by
``dwellings / n`` to preserve the building's total magnitude while letting
individual-household timing diversify the aggregate peak (measured peak/
mean ratio ~5.8 at N=20 for the same building). A cap (default 20) bounds
the per-dwelling generation cost (~25 ms/household measured) once the
diversity benefit has saturated -- going from 20 to 200 distinct draws does
not materially change the aggregate's shape, just its cost.

Household sizes across dwellings are drawn from the two integers
bracketing ``mean_num_persons`` (e.g. mean 2.3 people/dwelling splits
dwellings between 2- and 3-person households) so the building's mean
household size is preserved exactly rather than rounded to one size.

A ``dwellings=1`` building is unaffected relative to a plain
``HouseholdProfile``: ``n`` resolves to 1, ``scale`` to 1.0, and the one
household drawn uses the same default-seed derivation as a standalone
``HouseholdProfile`` would (no special-casing needed -- the general path
already collapses to that at N=1).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from occupancy.core.result import OccupancyResult
from occupancy.core.seed import derive_default_seed
from occupancy.households.archetypes import get_archetype
from occupancy.households.dhw import generate_dhw_draws
from occupancy.households.electricity import ElectricityConsumptionProfile
from occupancy.households.household_profile import HouseholdProfile

#: Default cap on the number of distinct households generated per
#: building, regardless of ``dwellings`` -- see module docstring.
DEFAULT_DWELLING_CAP = 20

# Large odd stride so consecutive dwelling indices land far apart in the
# 63-bit default-seed space, rather than producing near-identical seeds
# (and hence correlated draws) for adjacent dwellings.
_DWELLING_SEED_STRIDE = 104_395_301
_SEED_MODULUS = 1 << 63


def _dwelling_household_sizes(n: int, mean_num_persons: float) -> list[int]:
    """``n`` household sizes bracketing ``mean_num_persons`` so their mean
    equals it (to the precision ``n`` allows) rather than every dwelling
    rounding to the same size."""
    low = max(1, int(np.floor(mean_num_persons)))
    high = low + 1
    frac = mean_num_persons - low
    n_high = min(max(round(frac * n), 0), n)
    n_low = n - n_high
    return [low] * n_low + [high] * n_high


@dataclass
class MultiDwellingProfile:
    """Aggregate occupancy/electricity/DHW profile for a multi-dwelling
    building, built from ``n = min(round(dwellings), cap)`` distinct
    :class:`~occupancy.households.household_profile.HouseholdProfile`
    instances rather than one household scaled by ``dwellings``. See the
    module docstring for why.

    ``dwellings`` need not be a whole number (e.g. a GIS-derived dwelling
    count estimate); it only has to be positive. ``mean_num_persons`` is
    the building's average household size -- see
    :func:`_dwelling_household_sizes` for how it's realized across the
    ``n`` distinct households actually drawn.
    """

    dwellings: float
    mean_num_persons: float
    year: int
    archetype: str = "generic"
    region: str = "NL"
    seed: int | None = None
    cap: int = DEFAULT_DWELLING_CAP
    include_dhw: bool = False

    def __post_init__(self) -> None:
        if self.dwellings <= 0:
            raise ValueError("dwellings must be greater than 0")
        if self.mean_num_persons <= 0:
            raise ValueError("mean_num_persons must be greater than 0")
        if self.cap < 1:
            raise ValueError("cap must be >= 1")

        if self.seed is None:
            self.seed = derive_default_seed(
                kind="building",
                size=round(self.mean_num_persons),
                year=self.year,
                archetype=self.archetype,
                region=self.region,
            )

        self.n_households = max(1, min(round(self.dwellings), self.cap))
        self.scale = self.dwellings / self.n_households

        self._households: list[HouseholdProfile] | None = None
        self._profile: pd.DataFrame | None = None

    def get_households(self) -> list[HouseholdProfile]:
        """The ``n_households`` distinct, lazily-built households backing
        this building, each with its own seed derived from the building's
        seed and its dwelling index."""
        if self._households is None:
            sizes = _dwelling_household_sizes(
                self.n_households, self.mean_num_persons
            )
            assert self.seed is not None
            self._households = [
                HouseholdProfile(
                    num_persons=size,
                    year=self.year,
                    archetype=self.archetype,
                    region=self.region,
                    seed=(self.seed + i * _DWELLING_SEED_STRIDE)
                    % _SEED_MODULUS,
                )
                for i, size in enumerate(sizes)
            ]
        return self._households

    def generate(self) -> pd.DataFrame:
        """Generate, sum and scale the ``n_households`` households'
        occupancy fractions, electricity and (if ``include_dhw``) DHW
        draws into one building-level profile."""
        households = self.get_households()
        elec_profiles = [
            ElectricityConsumptionProfile(occupancy_profile=hh).get_profile()
            for hh in households
        ]

        index = elec_profiles[0].index
        n_present = np.zeros(len(index))
        n_active = np.zeros(len(index))
        n_asleep = np.zeros(len(index))
        total_power_kwh = np.zeros(len(index))
        cooking_count = np.zeros(len(index))
        for profile in elec_profiles:
            n_present += profile["n_present"].to_numpy(dtype=float)
            n_active += profile["n_active"].to_numpy(dtype=float)
            n_asleep += profile["n_asleep"].to_numpy(dtype=float)
            total_power_kwh += profile["total_power_kwh"].to_numpy(dtype=float)
            cooking_count += profile["cooking_active"].to_numpy(dtype=float)

        result = pd.DataFrame(
            {
                "n_present": n_present * self.scale,
                "n_active": n_active * self.scale,
                "n_asleep": n_asleep * self.scale,
                "total_power_kwh": total_power_kwh * self.scale,
                "cooking_active": cooking_count > 0,
            },
            index=index,
        )

        if self.include_dhw:
            dhw_total = np.zeros(len(index))
            for hh, profile in zip(households, elec_profiles, strict=True):
                assert hh.seed is not None
                dhw = generate_dhw_draws(
                    profile,
                    num_persons=hh.num_persons,
                    cooking_active=profile["cooking_active"],
                    seed=(hh.seed + _DWELLING_SEED_STRIDE // 2)
                    % _SEED_MODULUS,
                )
                dhw_total += dhw["dhw_liters_total"].to_numpy(dtype=float)
            result["dhw_liters_total"] = dhw_total * self.scale

        self._profile = result
        return result

    def get_profile(self) -> pd.DataFrame:
        if self._profile is None:
            return self.generate()
        return self._profile

    def to_result(self) -> OccupancyResult:
        """Like ``HouseholdProfile.to_result()``, but ``num_persons`` is
        the building's total occupant count (``dwellings *
        mean_num_persons``, for normalizing occupancy fractions in
        :func:`occupancy.core.buem_adapter.to_buem_profiles`) rather than
        one household's."""
        archetype_spec = get_archetype(self.archetype)
        return OccupancyResult(
            profile=self.get_profile(),
            year=self.year,
            num_persons=round(self.dwellings * self.mean_num_persons),
            building_type="household",
            region=self.region,
            heat_gain_present_kw=archetype_spec.heat_gain_present_kw,
            heat_gain_active_kw=archetype_spec.heat_gain_active_kw,
            gain_w_per_m2=archetype_spec.gain_w_per_m2,
        )


__all__ = ["DEFAULT_DWELLING_CAP", "MultiDwellingProfile"]

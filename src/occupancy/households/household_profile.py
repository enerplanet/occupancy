from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from occupancy.core.occupancy_engine import (
    OccupancyGenerationContext,
    get_generator,
)
from occupancy.core.result import OccupancyResult
from occupancy.core.seed import derive_default_seed
from occupancy.households.archetypes import get_archetype
from occupancy.households.crest_tpm import (
    MAX_CALIBRATED_SIZE,
    resolve_markov_chain_crest_params,
)


@dataclass
class HouseholdProfile:
    """Stochastic hourly occupancy model for a single household.

    ``archetype`` selects the default occupancy-probability data and
    generator strategy from
    :data:`occupancy.households.archetypes.HOUSEHOLD_ARCHETYPES`
    (default ``"generic"``, the pre-restructuring behavior). Any of
    ``home_probabilities``/``active_probabilities``/``generator``/
    ``generator_params`` can be overridden explicitly, same as before.
    """

    num_persons: int
    year: int
    archetype: str = "generic"
    # `None` (the default) no longer means "seed from OS entropy" -- it
    # resolves to a deterministic hash of this profile's own construction
    # inputs (see `core.seed.derive_default_seed`), overwritten onto this
    # field in `__post_init__` so downstream consumers relying on
    # `self.seed` (e.g. `ElectricityConsumptionProfile`) inherit it too.
    # Pass an explicit int to override with a caller-chosen seed instead.
    seed: int | None = None
    region: str = "NL"
    home_probabilities: np.ndarray | None = None
    active_probabilities: np.ndarray | None = None
    asleep_probabilities: np.ndarray | None = None
    generator: str | None = None
    generator_params: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.num_persons <= 0:
            raise ValueError("num_persons must be greater than 0")
        if self.year < 1900:
            raise ValueError("year must be >= 1900")

        self._archetype_spec = get_archetype(self.archetype)
        archetype_spec = self._archetype_spec

        home = (
            self.home_probabilities
            if self.home_probabilities is not None
            else archetype_spec.home_probabilities
        )
        active = (
            self.active_probabilities
            if self.active_probabilities is not None
            else archetype_spec.active_probabilities
        )
        asleep = (
            self.asleep_probabilities
            if self.asleep_probabilities is not None
            else archetype_spec.asleep_probabilities
        )
        self.home_probabilities = np.asarray(home, dtype=float)
        self.active_probabilities = np.asarray(active, dtype=float)
        self.asleep_probabilities = np.asarray(asleep, dtype=float)
        if self.home_probabilities.shape != (24, 2):
            raise ValueError("home_probabilities must have shape (24, 2)")
        if self.active_probabilities.shape != (24, 2):
            raise ValueError("active_probabilities must have shape (24, 2)")
        if self.asleep_probabilities.shape != (24, 2):
            raise ValueError("asleep_probabilities must have shape (24, 2)")

        self._generator_name = self.generator or archetype_spec.generator
        self._generator_params = (
            self.generator_params
            if self.generator_params is not None
            else archetype_spec.generator_params
        )

        if self.seed is None:
            self.seed = derive_default_seed(
                kind="household",
                size=self.num_persons,
                year=self.year,
                archetype=self.archetype,
                region=self.region,
            )
        self._rng = np.random.default_rng(self.seed)
        self._index = pd.date_range(
            start=f"{self.year}-01-01",
            end=f"{self.year}-12-31 23:00",
            freq="h",
        )
        self._profile: pd.DataFrame | None = None

    def generate(self, seed: int | None = None) -> pd.DataFrame:
        """Generate and cache the yearly occupancy profile."""
        assert self.home_probabilities is not None
        assert self.active_probabilities is not None
        assert self.asleep_probabilities is not None
        rng = self._rng if seed is None else np.random.default_rng(seed)

        generator_name = self._generator_name
        generator_params = self._generator_params or {}
        if generator_name == "markov_chain_crest":
            if self.num_persons > MAX_CALIBRATED_SIZE:
                warnings.warn(
                    "markov_chain_crest has real CREST transition data "
                    f"only for household sizes 1-{MAX_CALIBRATED_SIZE}; "
                    f"num_persons={self.num_persons} falls back to the "
                    "synthesized 'markov_chain' generator instead.",
                    stacklevel=2,
                )
                generator_name = "markov_chain"
            else:
                generator_params = resolve_markov_chain_crest_params(
                    self.num_persons, generator_params
                )

        ctx = OccupancyGenerationContext(
            size=self.num_persons,
            index=self._index,
            home_probabilities=self.home_probabilities,
            active_probabilities=self.active_probabilities,
            asleep_probabilities=self.asleep_probabilities,
            rng=rng,
            params=generator_params,
        )
        strategy = get_generator(generator_name)
        self._profile = strategy(ctx)
        return self._profile

    def get_profile(self) -> pd.DataFrame:
        """Return a generated profile, creating one lazily if needed."""
        if self._profile is None:
            return self.generate()
        return self._profile

    def to_result(self) -> OccupancyResult:
        return OccupancyResult(
            profile=self.get_profile(),
            year=self.year,
            num_persons=self.num_persons,
            building_type="household",
            region=self.region,
            heat_gain_present_kw=self._archetype_spec.heat_gain_present_kw,
            heat_gain_active_kw=self._archetype_spec.heat_gain_active_kw,
            gain_w_per_m2=self._archetype_spec.gain_w_per_m2,
        )

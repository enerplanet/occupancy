"""Deterministic default-seed derivation for RNG-reproducibility.

Backs the "Seed ownership" proposal in buem's ``occupancy_gains_handoff.md``
(raised 2026-08-07 while closing that hand-off's Gaps 1-3, previously
unimplemented): ``seed`` is an internal RNG-reproducibility knob for this
package's stochastic generation, not something a caller like buem or
EnerPlanET should need to think about or pass explicitly. Historically
``seed=None`` fell back to ``numpy.random.default_rng(None)``'s OS-entropy
seeding -- genuinely non-deterministic, a fresh draw every construction --
which pushed the reproducibility burden onto callers (buem's own
``DEFAULT_SEED = 42`` stopgap, passed on every call so its own
``test_hash_determinism`` wouldn't flake). That stopgap has a real flaw:
every building sharing (building_type/archetype, num_persons/capacity,
year) with no override gets the exact same seed, hence byte-identical
draws -- fine for single-building reproducibility, unrealistic for a
portfolio of many similar buildings.

:func:`derive_default_seed` replaces the OS-entropy fallback: a stable hash
of the profile's own construction inputs, used only when the caller doesn't
pass an explicit ``seed``. This gives both properties the stopgap couldn't:
same inputs -> same profile (reproducible without the caller managing
anything), and different inputs -> (almost certainly) different profile
(real portfolio diversity). ``HouseholdProfile``/``ServiceBuildingProfile``
overwrite ``self.seed`` with the resolved value in ``__post_init__``, so any
seed-dependent downstream consumer (e.g.
``ElectricityConsumptionProfile``'s ``self.seed = self.occupancy_profile.seed``
fallback, and its own ownership-draw seed offset) inherits the same
deterministic value automatically, not just the top-level occupancy draw.

**Residual limitation, same one the proposal itself accepts**: this can
only hash what the profile's constructor inputs actually distinguish. Two
genuinely different real buildings that happen to share every one of those
inputs (same building_type/archetype, num_persons/capacity, year, region)
still collide onto the same seed -- there is no building-identity input
available to hash instead. Real per-building uniqueness would need a
caller-supplied identifier (e.g. a building/parcel ID) threaded through as
an explicit ``seed=hash(building_id)`` override, which remains fully
supported; this default only improves on the *previous* default (OS entropy
sometimes, or a single shared constant), not on an explicit, more granular
seed a caller chooses to pass.
"""

from __future__ import annotations

import hashlib

# Keeps the derived seed a plain non-negative 63-bit int -- safely within
# `numpy.random.default_rng`'s accepted range on every platform, rather than
# relying on passing its full digest through `SeedSequence`'s wider
# arbitrary-precision int acceptance.
_SEED_MASK = (1 << 63) - 1


def derive_default_seed(
    *,
    kind: str,
    size: int,
    year: int,
    archetype: str,
    region: str,
) -> int:
    """Stable, deterministic seed derived from a profile's own construction
    inputs.

    ``kind`` distinguishes households (``"household"``, since
    ``HouseholdProfile`` has no other type dimension) from service-building
    types (the building type id itself, e.g. ``"supermarket"``). ``size`` is
    ``num_persons``/``capacity``. ``archetype`` is the household-archetype
    id for households, or ``""`` for service buildings (no equivalent
    field). Same inputs always hash to the same seed; changing any one
    input changes the seed (and hence the generated profile) with
    overwhelming probability.
    """
    key = f"{kind}|{size}|{year}|{archetype}|{region}"
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & _SEED_MASK


__all__ = ["derive_default_seed"]

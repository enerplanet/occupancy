# Resolved issues & settled decisions — cross-cutting

Household-specific items: `residential/resolved.md`. Service-building-
specific items: `services/resolved.md`. Do not re-raise. "BY-DESIGN" are
deliberate choices.

## households + services_buildings restructuring — fixed/settled
- Dual config source-of-truth (root `configs/*.json` vs bundled
  `src/occupancy/config/data/*.json`) → root `configs/` deleted,
  `_defaults.py` deleted; every subpackage (`config/`, `households/`,
  `services_buildings/`) now bundles and loads its own `data/` via
  `importlib.resources` (`core/loader.py`). Single source per subpackage.
- `plot_weekly_total_power` lived in `electricity_consumption.py` instead
  of `visualization/plots.py` → resolved as part of the
  households/electricity.py rewrite.
- `OccupancyResult` was defined but never returned by
  `OccupancyProfile.generate()`/`get_profile()` → now the shared output
  contract (`core/result.py`) with `building_type`/`region` fields;
  `HouseholdProfile.to_result()` / `ServiceBuildingProfile.to_result()`
  wrap it.
- Occupancy column naming `n_home` → `n_present` (and `activity` value
  renaming) — deliberate, since the concept generalizes to service
  buildings that don't have a "home". Documented in `CHANGELOG.md`.

## BY-DESIGN (this round)
- simpy and mesa were evaluated as potential underlying engines and
  deliberately **not** adopted as dependencies — architecturally mismatched
  (simpy: event-driven vs. this project's fixed-hourly-tick vectorized
  model) or unnecessary weight for capabilities not used (mesa: spatial/
  agent-interaction features). Their `Model`/`Agent`-style separation and
  registry/strategy patterns informed the `core/occupancy_engine.py` +
  `core/equipment.py` registry design instead. Full research retained in
  `docs/plans/equipment-service-buildings-architecture.md`.
- Households and service buildings share one engine
  (`core/occupancy_engine.py` generator registry, `core/equipment.py`
  equipment registry) rather than parallel implementations — household is
  registered as just the first archetype/activity type, not special-cased.

## config — fixed (pre-existing, carried over)
- Fragile four-level `Path(__file__).parent` traversal in
  `ScenarioConfig.default()` → `importlib.resources`-based resolution.
- `!src/occupancy/config/data/` negation missing from `.gitignore` →
  added (extended this round with `!src/occupancy/households/data/` and
  `!src/occupancy/services_buildings/data/`).

## packaging/build — fixed (pre-existing, carried over)
- Stale `setup.py` stub conflicted with `pyproject.toml` build system →
  deleted.
- `write_to` (setuptools-scm legacy key) → renamed `version_file`.
- `src/occupancy/__init__.py` fallback version `"1.1.0"` → `"unknown"`.

## CI/CD — fixed (pre-existing, carried over)
- Node 20 deprecation on GitHub Actions →
  `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` added to both workflows.
- `contents: write` permission missing on release workflow → added.
- `setuptools-scm` couldn't read full tag history in CI → `fetch-depth: 0`
  added to checkout step.

## BY-DESIGN (pre-existing, carried over)
- Python baseline is 3.12 everywhere — do not reintroduce 3.14.
- No hardcoded numeric arrays in Python source — everything in bundled
  JSON, loaded at runtime.
- Docker base image pinned to `continuumio/miniconda3:24.1.2-0`; bind-mount
  pattern for `src/`, not build-time `COPY` (root `configs/` bind mount
  removed this round since that directory no longer exists).
- `occupancy` package has zero coupling to BuEM/weather monorepo
  internals.
- buem takes no occupancy/internal-gains/electricity input of its own —
  `occupancy` is the intended upstream source. **Correction (2026-07-28):**
  the original wording here ("no occupancy/internal-gains/electricity
  fields") was backwards — buem's `cfg` actually *requires* four series
  (`Q_ig`/`elecLoad`/`occ_nothome`/`occ_sleeping`) and fails without them;
  it generates none of them itself. `occupancy.core.buem_adapter.to_buem_profiles()`
  now supplies all four from an `OccupancyResult`. See `open.md` for the
  remaining package-name-mismatch follow-up on buem's side.

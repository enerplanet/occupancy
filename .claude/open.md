# Open issues / TODOs — cross-cutting

Household-specific items: `residential/open.md`. Service-building-specific
items: `services/open.md`.

## >>> NEXT MAJOR TASKS <<<
- [buem-linkage] **Household internal gains now scale with `num_persons`;
  findings written up for buem, not yet raised (2026-08-28)** — see
  `.claude/buem_household_scaling_findings.md`, the mirror of buem's own
  still-unraised `.claude/occupancy_service_scaling_request.md`. Since
  buem removed the `Q_ia` presence rescaling (`Q_ia = Q_ig + elecLoad`),
  `occ_nothome`/`occ_sleeping` carry no headcount by construction, so
  `Q_ig` and `elecLoad` are the only carriers — and `elecLoad`, the
  dominant term at 70% of `Q_ia`, moved only ×1.40 across 1-5 occupants
  because every household appliance keyed off `percent_active` (a
  fraction). New per-item `occupant_scaling` exponent fixes it (×2.20,
  `Q_ia` ×2.47→×3.03); details in `residential/open.md`. **Still to do**:
  raise the document with buem, and ask buem to re-run `validation.py` —
  every multi-occupant dwelling now gets more internal gain, so modelled
  heating demand drops and the known buem-vs-CBS overshoot should narrow.
- [services_buildings] **`occupant_scaling` is available to service
  buildings but not applied to them (2026-08-28)** — the mechanism lives
  in the shared `core/equipment.py`, so buem's
  `occupancy_service_scaling_request.md` item 1 (40× capacity moving
  annual electricity only ×1.46, same root cause as the household bug
  above) is now a per-type **data** change in
  `services_buildings/data/<type>/equipment.json`, not an engine change.
  Deliberately out of scope for the households round; nothing blocks it.
- [region] **Multi-region data** — `region` is threaded through
  `OccupancyResult` and archetype/building-type JSON, but only one
  region's data (`NL`) is populated. Adding a new region is a config
  addition (new archetype/building-type JSON files with a different
  `region` value); no registry keying by region exists yet if two regions
  need the *same* archetype id with different data — would need the
  registry key to become `(id, region)` if/when that's needed.

## cross-repo
- [dhw-cooking] **buem's DHW + gas-cooking heat-demand ask (2026-08-17,
  implemented 2026-08-18)** — docs are split by audience, not bundled:
  `residential/dhw_cooking_literature_review.md` holds the literature
  review and research trail (papers read, questions asked/answered along
  the way) as internal working notes, kept out of `docs/` on the user's
  explicit instruction ("These are internal discussions between claude
  agents and should never be a part of the external/official docs
  folder"); `docs/dhw/design.md` and `docs/buem_engine_reference.md` hold
  the official technical documentation (API, CSV schema, every
  deterministic value, buem's actual engine internals) — the only pieces
  of this work that belong in `docs/`. Status of buem's three original
  asks:
  - **Item 1** (CREST hot-water-fixture-derived liters output) —
    **implemented as a first pass**: `occupancy.generate_dhw_draws()`
    (`households/dhw.py`) + the editable, self-consistency-checked
    `households/data/dhw_tapping_categories.csv` (Jordan & Vajen 2005
    DHWcalc reference values, scaled by household size). Liters only,
    never kWh, and deliberately **not** wired into `to_buem_profiles()`
    or any `.generate()` default output — the user's explicit
    direction was that DHW isn't part of buem yet and won't be until
    after buem's own follow-up update. Real open items (per-fixture
    ownership sourcing, non-kitchen draw timing, service buildings) are
    listed in `docs/dhw/design.md`.
  - **Item 2** (separable `cooking_active` signal) — **done**, see
    `CHANGELOG.md` `[Unreleased]`; also closed buem's
    `occupancy_module_activities.md` item 1 (`EQUIPMENT_TYPES` export)
    and `occupancy_gains_handoff.md`'s "Seed ownership" item in the same
    pass.
  - **Item 3** (NTA 8800 cross-check) — still unstarted/lower-priority;
    two more pointer pages checked 2026-08-18
    (`residential/dhw_cooking_literature_review.md`'s NTA 8800 section)
    without surfacing the actual numbers — the base standard remains a
    paid NEN publication with no free full-text mirror found across two
    sessions.
- [pylovo/multi-profile] **Idea, not started (2026-07-31)** — two possible
  future directions raised for occupancy's elecLoad output interacting
  with more than one profile at a time, neither finalized/scoped:
  1. Feeding aggregated/peak elecLoad from multiple occupancy profiles
     (households and/or service buildings) into
     [enerplanet-pylovo](https://github.com/enerplanet/enerplanet-pylovo),
     which sizes LV/MV synthetic electricity networks and transformers
     from peak load. This needs more than N independent
     `HouseholdProfile`/`ServiceBuildingProfile` runs — realistic
     diversity/coincidence between profiles feeding the same
     transformer/feeder node matters, and correlation between profiles
     was flagged as worth studying rather than assuming independence.
  2. The reverse direction: if a user (or buem/enerplanet) supplies
     elecLoad externally rather than having occupancy generate it,
     occupancy should still be able to compute internal gains
     (`Q_ig`)/`occ_nothome`/`occ_sleeping` for buem's heat-demand calc.
     **Scaffolded (2026-08-07)**: `to_buem_profiles(elec_load=...)` now
     accepts an externally-sourced series and skips the `total_power_kwh`
     requirement, computing the other three series from occupancy's own
     generated presence pattern as before. Note this isn't literally
     "derive Q_ig from the elecLoad values themselves" (there's no
     elecLoad -> Q_ig transformation) — it's "let elecLoad's *source* be
     external while Q_ig/occ_nothome/occ_sleeping still come from
     occupancy's own occupancy-profile generation", which is what the
     handoff conversation actually needed. Direction 1 (pylovo
     aggregation/correlation) is still not started/not scoped.
  Whether these run independently or combined, and where the
  aggregation/correlation logic would live (occupancy vs. pylovo vs. a
  new cross-repo layer), is explicitly not decided yet — do not start
  building an API or batch-generation feature for this without
  re-confirming scope first.
- [harmonization] **Idea, not started (2026-07-30)**: a small shared
  "harmonization" package (env.yml/pyproject.toml/CI-workflow scaffolding)
  that occupancy/weather/buem would each conda-install from, instead of
  today's approach — every shared pin or fix (e.g. the numpy/pandas
  floor-only convention) gets hand-copied across all three repos' own env
  files and `.github/agents/uu-buem-align.agent.md`'s table by hand each
  time. See weather's `.claude/open.md` for the fuller note (same idea,
  cross-posted). Not designed or scoped yet — ask before acting if this
  comes up again.

## cross-module

- [all] Keep ruff/mypy/pytest clean; honour `pyproject.toml` settings at
  root.
- [all] Public API (`OccupancyProfile`/`HouseholdProfile`/
  `ElectricityConsumptionProfile`/`OccupancyResult`/`ServiceBuildingProfile`/
  `SERVICE_BUILDING_TYPES`/`HOUSEHOLD_ARCHETYPES`/`EQUIPMENT_TYPES`, all
  re-exported from `occupancy/__init__.py`) is the compatibility surface
  going forward — deep module paths are not guaranteed stable.
  `SERVICE_BUILDING_TYPES` was promoted to this top-level surface
  (2026-08-07) specifically so downstream consumers (buem) can
  enumerate/validate registered service-building-type ids at
  runtime (`sorted(occupancy.SERVICE_BUILDING_TYPES)`) instead of
  hand-copying the list into their own schema/enum, which was buem's
  `occupancy_gains_handoff.md` Gap 3 (registry duplication risk). Consuming
  it via the deep path (`occupancy.services_buildings.SERVICE_BUILDING_TYPES`)
  still works but isn't the documented-stable one going forward.

## external (context only)
- [buem] **Dynamic num_persons/capacity/year wiring already exists
  (2026-07-31)** — before assuming buem's `cfg_attribute.py` needs to be
  made request-aware, check `buem/src/buem/integration/scripts/
  attribute_builder.py`'s `AttributeBuilder.generate_electricity_profile()`
  (~lines 146-209) first: it already reads `num_persons`/`capacity`/
  `building_type`/`seed` from `self.merged_attrs` (the real per-request
  config, not a static default) and constructs `HouseholdProfile`/
  `ServiceBuildingProfile` accordingly, forcing `year` to the weather
  file's year. `cfg_attribute.py`'s module-level `HouseholdProfile(...)`
  call (~line 114) is only the `AttributeSpec` fallback default, not a
  bug. One loose end noticed there: line ~180 reads `capacity` from
  `merged_attrs` without the `int()` cast that `num_persons` gets on line
  173 — a string capacity from a JSON request could reach occupancy's
  `ServiceBuildingProfile.__post_init__` and fail its `self.capacity <= 0`
  comparison. This is a buem-side fix, not an occupancy one — flagged here
  only as context for whoever next touches that pipeline.
- [buem] **`occupancy_gains_handoff.md` Gaps 1/3 resolved on occupancy's
  side (2026-08-07)** — see CHANGELOG `[Unreleased]` for the full detail.
  Gap 1 (per-occupant-kW-only internal gains, no floor-area normalization):
  `to_buem_profiles()` gained optional `floor_area_m2`/`gain_w_per_m2`
  kwargs that blend an area-driven component into `Q_ig` rather than
  replacing the occupant-driven one; all 8 service-building types now carry
  an illustrative `gain_w_per_m2`. **Still open on buem's side**: nothing
  forwards `A_ref`/`computed_A_ref()` into the `floor_area_m2` kwarg yet —
  `AttributeBuilder.generate_electricity_profile()` would need that wiring
  (and note it runs before `CfgBuilding.to_cfg_dict()` computes the real
  `A_ref` today per buem's own `open.md` bug note, so ordering matters).
  Also still open, on occupancy's side: the `gain_w_per_m2` values are a
  first illustrative pass (ASHRAE 90.1 Table 9.5.1 LPD-based, not
  survey-calibrated), same caveat as `heat_gain_present_kw`/
  `heat_gain_active_kw` already carry. Gap 3 (building-type registry
  duplication): `occupancy.SERVICE_BUILDING_TYPES` is now a top-level
  export (see "cross-module" above) — buem's v4 draft schema enum can
  import it at runtime instead of hand-copying, whenever that gets picked
  up. Gap 2 (v3/v2 request forwarding of capacity/num_persons/seed/
  archetype) is buem-only (`geojson_validator.py`, a tier-1 file per buem's
  own guardrails) — no occupancy-side action possible or taken.
  Also scaffolded in the same pass, not from the handoff doc but from a
  separate user-directed forward-looking discussion (see "cross-repo"
  pylovo/multi-profile note above, direction 2):
  `to_buem_profiles(elec_load=...)` lets `Q_ig`/`occ_nothome`/
  `occ_sleeping` be derived from occupancy's own presence pattern even when
  elecLoad itself comes from somewhere else.
- [buem] **Superseded** — a prior pass claimed buem's `cfg_attribute.json`
  has no occupancy/internal-gains/electricity fields; that was wrong (or
  read a stale/different version). Direct inspection of
  `buem.config.cfg_attribute.ATTRIBUTE_SPECS` and
  `buem.thermal.model_buem.ModelBUEM._addPara`/`_addConstraints_sequential`
  (2026-07-28) confirms buem's `cfg` dict *requires* four series —
  `Q_ig`, `elecLoad`, `occ_nothome`, `occ_sleeping` — and raises
  `ValueError` if any are missing. `occupancy.core.buem_adapter.to_buem_profiles()`
  now builds all four from an `OccupancyResult`; see CHANGELOG
  `[Unreleased]` and README "Feeding buem".
- [buem] **User context (2026-07-28):** `occupancy` used to live inside the
  `buem` monorepo; it has since been split out into this standalone repo,
  and `buem` itself is being refactored to depend on it externally instead
  — that refactor is in progress, not complete. The package-name-mismatch
  item below is exactly the seam that refactor needs to close.
- [buem] **Package-name mismatch — fixed on buem's side (2026-07-29,
  uncommitted as of that date)**. buem's working tree now imports
  `from occupancy import ElectricityConsumptionProfile, HouseholdProfile,
  to_buem_profiles` and calls
  `to_buem_profiles(ElectricityConsumptionProfile(occupancy_profile=
  HouseholdProfile(...)).to_result())` in `cfg_attribute.py` — matching
  this repo's real public API and the exact pattern documented in this
  repo's README "Feeding buem" section. `pyproject.toml`'s
  `buem-occupancy`/`buem-weather` extras were also renamed to
  `occupancy`/`weather`. Not yet committed/merged on buem's side as of this
  note; re-verify once merged. Neither package is published to PyPI/
  conda-forge yet, so `pip install buem[occupancy]` won't resolve until
  either occupancy is published somewhere pip can reach, or the dependency
  is pointed at a VCS/local URL — occupancy does already ship a working
  conda recipe (`meta.yaml`) buildable locally via `conda build .` +
  `conda install --use-local occupancy`, which needs no publishing step.
  buem now targets Python >=3.14 (env + pyproject bumped); occupancy
  declares `>=3.12` with no upper pin so there's no hard version conflict,
  but occupancy's own dev/CI baseline is 3.12 (see `resolved.md` "Python
  baseline") and has never been run under 3.14 — untested, not blocked.
- [buem] **Original mismatch note (superseded by the fix above, kept for
  history)** — `buem`'s `cfg_attribute.py` imports
  `from buem_occupancy.occupancy_profile import OccupancyProfile` and
  `from buem_occupancy.electricity_consumption import ElectricityConsumptionProfile`
  (`pip install buem-occupancy`) as its intended real (non-fallback) source
  for `elecLoad`. Those class names and the
  `OccupancyProfile(num_persons=..., year=..., seed=...).generate()` /
  `ElectricityConsumptionProfile(occupancy_profile=...).generate()["total_power_kwh"]`
  shapes match this repo's actual API almost exactly — but this repo is
  packaged/importable as `occupancy`, not `buem_occupancy`, and the
  submodule paths (`occupancy.households.household_profile` /
  `occupancy.households.electricity`) don't match buem's expected
  `buem_occupancy.occupancy_profile` / `buem_occupancy.electricity_consumption`
  either. Also: buem's fallback path only ever calls
  `OccupancyProfile`/`ElectricityConsumptionProfile` (i.e. household-only)
  — it has no notion of pulling a `ServiceBuildingProfile` result, and no
  `Q_ig`/`occ_nothome`/`occ_sleeping` wiring at all, real or fallback. This
  needs resolving on the buem side (package rename/alias, or buem depending
  on `occupancy` directly and calling `to_buem_profiles()`) — flagged here,
  not fixed here, since it's a buem-repo change.
- [reference-repos] Design informed by pyCREST, richardsonpy, tsorb (all
  GPLv3 — concepts/schema only, no data/code copied), StROBe (unlicensed —
  household-archetype concept only), simpy and mesa (evaluated and
  deliberately not adopted as dependencies), plus two journal papers
  (Richardson et al. 2009 CREST domestic demand model; Buttitta & Finn
  2020 occupancy-integrated archetypes, *Energy & Buildings* 206:109577)
  — see `residential/open.md` for paper-specific follow-ups and license
  notes (CREST's own data download is CC BY-NC-ND, no derivatives).

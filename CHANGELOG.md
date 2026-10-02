# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [6.0.0] - 2026-08-28

### Changed

- **Behavior change**: household electricity demand now scales with
  `num_persons`. Previously every one of the 29 household appliances was
  household-size-blind — firing probability keyed off `percent_active`
  (`n_active / n_present`, a *fraction* that is 1.0 whether one person of
  one is active or five of five) plus an `n_active > 0` gate — so annual
  electricity moved only ×1.40 across 1-5 occupants. It now moves ×2.20,
  against roughly ×2.75 in published NL averages by household size.
  Single-occupant households are unaffected (identical output, same
  seed); every multi-occupant household draws more.

  This matters beyond the electricity figure: `buem` forms internal air
  gains as `Q_ia = Q_ig + elecLoad` with no presence rescaling, and
  `occ_nothome`/`occ_sleeping` are dimensionless occupant fractions, so
  `Q_ig` and `elecLoad` are the *only* carriers of occupant count into
  the thermal model. `elecLoad` is the dominant term (70% of `Q_ia` at
  one occupant). Combined `Q_ia` scaling across 1-5 occupants goes ×2.47
  → ×3.03. Downstream heating demand for multi-occupant dwellings will
  fall accordingly. Full measurement in
  `.claude/buem_household_scaling_findings.md`.

### Added

- `occupant_scaling` — optional per-item `strategy_params` exponent α in
  the shared equipment model (`core/equipment.py`), multiplying an
  item's firing probability by `max(gate_count, 1) ** α`, and its session
  count for `sessions_per_week` items. α defaults to `0.0`, which
  reproduces the previous behavior bit for bit under the same seed, so
  the engine change is backward compatible and service buildings (which
  do not set it) are unaffected. The 22 occupancy-driven household
  appliances are assigned to four sharing tiers: `1.0` per-person
  consumables (laundry, dishwasher, kettle, PC, iron), `0.5`
  partly-shared activities (cooking, vacuum, secondary TVs), `0.3`
  mostly-shared (lighting, printer), `0.15` one-per-household items (main
  TV, hi-fi). The 7 `flat_always_on` cold appliances and standby
  electronics are exempt by design. `1.0` is a deliberate ceiling — above
  it an appliance's usage would grow faster than the number of people
  using it. Rationale and provenance are in
  `households/data/equipment.json`'s own `_occupant_scaling_comment`;
  these tier assignments are this repo's own, **not** CREST figures.

### Fixed

- `ElectricityConsumptionProfile.to_result()` dropped `gain_w_per_m2`
  from the archetype spec, though `HouseholdProfile.to_result()` carried
  it. Since `to_buem_profiles()` requires a `total_power_kwh` column, the
  electricity path is the only household route into it, so passing
  `floor_area_m2=` for a household always raised "no gain_w_per_m2 is
  available" regardless of what the archetype defined. Currently latent
  (all five household archetypes leave `gain_w_per_m2` null — households
  get their real equipment/lighting gains through `elecLoad`, and adding
  an area-normalized density on top would double-count them), but the
  two `to_result()` methods no longer disagree.
- `core/buem_adapter.py`'s module docstring documented a superseded
  `Q_ia = (Q_ig + elecLoad) * (occ * (1 - occ_sleeping) + 0.5 *
  occ_sleeping)` formula; buem removed that presence rescaling. The
  docstring now states the real contract and its consequence — with no
  presence reweighting downstream, `Q_ig` and `elecLoad` must carry the
  occupant-count dependence themselves.

## [5.0.0] - 2026-08-18

### Changed

- **Breaking**: `generate_dhw_draws()`'s required positional `rng:
  np.random.Generator` argument is replaced by a keyword-only `seed: int
  | np.random.Generator | None = None`, matching `HouseholdProfile`/
  `ServiceBuildingProfile`'s own `seed=` convention. `seed=None` derives a
  deterministic default via `core/seed.py::derive_default_seed`
  (`kind="dhw"`, distinct from any household's own default seed); an
  `int` is used directly; a pre-built `np.random.Generator` still works
  as an escape hatch. Removes the only way to call this function that
  required either reaching into a household's private `_rng` attribute
  or restarting a fresh generator from a household's own seed (risking
  correlated, non-independent draws) — a caller can now do
  `generate_dhw_draws(profile, num_persons=..., seed=household.seed)`
  using only public API. See `docs/dhw/design.md`'s "Randomization"
  section.

### Added

- `scripts/extract_dhw_tapping_categories.py` — reproducible extraction
  of `households/data/dhw_tapping_categories.csv` from
  `data/inputs/CREST_Demand_Model_v2.3.3.xlsm`, mirroring
  `scripts/extract_crest_tpm.py`'s established pattern. Regenerating the
  CSV from this script (rather than the one-off manual read `v4.0.0`
  shipped with) gives full floating-point precision and a byte-for-byte
  reproducible provenance path; the CSV itself remains directly
  user-editable afterward.

### Docs

- Literature review and research trail for the DHW work moved from
  `docs/dhw/` back to `.claude/residential/dhw_cooking_literature_review.md`
  — internal research notes, not official user-facing documentation, per
  explicit user direction. `docs/dhw/` now holds only `design.md` (the
  technical reference for what was built) and its `README.md`.

## [4.0.0] - 2026-08-18

### Added

- `occupancy.generate_dhw_draws()` (new `households/dhw.py`) — stochastic
  hourly domestic-hot-water draw volumes in **liters** (never kWh; see
  `docs/buem_engine_reference.md` for why), one `dhw_liters_<fixture>`
  column per tapping category (`basin`, `kitchen_sink`, `shower`, `bath`
  by default) plus a summed `dhw_liters_total`. Answers buem's
  `dhw_cooking_heat_handoff.md` ask #1. Every deterministic number this
  model uses — fixture ownership rates, flow rates, durations, reference
  event frequencies, and the reference household size they're calibrated
  to — lives in exactly one editable file, `households/data/
  dhw_tapping_categories.csv` (real values read directly from McKenna &
  Thomson's (2016) own CREST runtime workbook, `CREST_Demand_Model_
  v2.3.3.xlsm`; see `docs/dhw/design.md` for the full derivation,
  including the one hybrid figure — `events_per_day_reference`, apportioned
  from that workbook's own aggregate total using DHWcalc/Jordan & Vajen
  (2005)'s relative category shares, honestly flagged as such); loaded
  and validated (required columns, positive flow/duration, `[0, 1]`
  ownership probabilities, one shared `reference_num_persons`) via a new
  `core/loader.py::load_csv_resource` helper (mirrors
  `load_json_resource`) and `households/dhw.py`'s own
  `load_tapping_categories()`. Fixture **ownership** is now a real,
  per-fixture, seeded stochastic draw (`ownership_probability`, sourced
  from the same workbook) — a household without a bath draws zero from
  it, every run — not a household-size scaling proxy. Event **counts**
  are scaled by `num_persons / reference_num_persons` and drawn
  stochastically (Poisson); per-event **volume** is also stochastic
  (Poisson, centred on each fixture's derived mean), matching the source
  workbook's own volume-distribution approach rather than a fixed
  number every time. Event **timing** is resolved via a small
  registry (`_TIMING_ENVELOPES` / `households.dhw.
  register_timing_envelope()`, mirroring `core/equipment.py`'s
  `register_strategy` pattern, so a custom tapping-category table can
  introduce a new `activity_link` with real routed timing logic):
  kitchen-sink draws follow the already-shipped `cooking_active` signal;
  basin/shower/bath draws use a transition-weighted occupancy envelope
  (`n_active` plus extra weight at the hours active occupancy changes,
  i.e. waking/bedtime) rather than a flat average, reusing the same
  "occupants becoming active/inactive" concept Richardson et al. (2008)
  validate their own occupancy model against. Deliberately **not** wired
  into `HouseholdProfile.generate()`, `ElectricityConsumptionProfile.
  generate()`, or `to_buem_profiles()` — opt-in only (same pattern as
  `estimate_equipment_usage()`), per explicit user direction that DHW
  isn't part of buem yet and won't be until buem's own follow-up work.
  Full literature review, source list, answers to the design questions
  this was built around, and every deterministic value used (all in
  reviewable tables) are in `docs/dhw/` — see its `README.md`.
- New `docs/buem_engine_reference.md` — documents buem's 5R1C thermal
  engine's actual internal-gains pathway and required-config contract
  from occupancy's side (the reverse of what buem's own `.claude/
  occupancy_module_activities.md` does for occupancy), including direct
  confirmation, re-checked against buem's current code, that `q_w_nd`
  (TABULA's DHW parameter) is carried through buem's data model but never
  read by `ModelBUEM.sim_model()`, and where a future DHW energy term
  would (additive, after the 5R1C solve) and would not (inside `Q_ia`)
  plug in.
- New `markov_chain_crest` occupancy-generation strategy
  (`core/occupancy_engine.py`): active-occupant-count transitions drawn
  from real CREST Domestic Electricity Demand Model 1.0e
  transition-probability matrices (`tpm{1..5}_{wd,we}` sheets, indexed by
  household size 1-5), hourly-composed from the source 10-minute-
  resolution data via 6-step matrix multiplication
  (`households/crest_tpm.py::compose_hourly_transition_matrix`), one
  matrix per household size x weekday/weekend. New
  `households/data/tpm_crest.json` (extraction documented and reproducible
  via `scripts/extract_crest_tpm.py`, attribution matching the precedent
  set by `households/data/equipment.json`) and `households/crest_tpm.py`
  (loading/composition/resolution). Households with more than 5 residents
  (`households/crest_tpm.py::MAX_CALIBRATED_SIZE`, CREST's own modeled
  range) fall back to the existing synthesized `markov_chain` generator
  with a `warnings.warn`. Only the active-occupant-count transition is
  CREST-calibrated — presence-vs-active split and `n_asleep` are still
  derived from this repo's own (illustrative) marginal arrays. Resolves
  the `.claude/residential/open.md` "Source real regional TPM survey
  data" NEXT MAJOR TASK.
- `occupancy.estimate_equipment_usage()` (new `core/disaggregation.py`):
  fits non-negative per-item equipment usage-intensity coefficients against
  a supplied whole-building `elec_load` series via `scipy.optimize.nnls`
  on closed-form deterministic expected-value templates (new
  `expected_probabilistic_event`/`expected_sessions_per_week` counterparts
  in `core/equipment.py`, alongside the already-deterministic
  `flat_always_on`/`linear_in_occupants`, plus a new
  `register_expected_value_strategy`/`get_expected_value_strategy`
  registry mirroring `register_strategy`/`get_strategy`). Returns a
  `dict[str, EquipmentSpec]` that slots directly into `equipment=` on
  `ElectricityConsumptionProfile`/`ServiceBuildingProfile`. Answers buem's
  long-deferred `occupancy_module_activities.md` item 3 ("investigate
  profile-based equipment-usage-pattern inference"). Explicitly
  illustrative/estimation-only, not a validated calibration (identifiability
  is limited for collinear/similarly-shaped items; fits *expected-value*
  templates, not the true per-draw stochastic signal) — see the function's
  docstring for the full caveat. Does **not** change
  `to_buem_profiles()`'s contract or `Q_ig` computation; it's a standalone
  preprocessing step a caller opts into. New `scipy>=1.11` runtime
  dependency (`pyproject.toml`, `infrastructure/env/occupancy_env.yml`,
  `meta.yaml`) — already a `buem` dependency, so no new transitive cost for
  that consumer.
- `ServiceBuildingProfile.equipment: dict[str, EquipmentSpec] | None = None`
  and a new `get_equipment_table()` method — per-item equipment inclusion/
  exclusion for service buildings, mirroring
  `ElectricityConsumptionProfile.equipment`/`get_equipment_table()` on the
  household side exactly (`None` uses the building type's full default
  table; a dict is used as-is, so any item id absent from it is fully
  excluded). Resolves buem's `occupancy_module_activities.md` item 2
  (`ServiceBuildingProfile` previously had only an all-or-nothing
  `include_equipment: bool` switch, no way to select individual items).
  `include_equipment=False` remains a separate master switch that omits
  `total_power_kwh` entirely regardless of `equipment=`; `equipment={}`
  with `include_equipment=True` keeps the column present but all-zero —
  document this distinction where used. Pure parameter parity, no new
  occupancy-side modeling concept.
- `occupancy.HOUSEHOLD_ARCHETYPES` promoted to the top-level public API
  (`occupancy/__init__.py`), mirroring `SERVICE_BUILDING_TYPES`'s promotion
  in `[3.1.0]` (buem's `occupancy_gains_handoff.md` Gap 3). Fixes a public-
  API asymmetry raised during a buem/occupancy review (2026-08-14):
  `HOUSEHOLD_ARCHETYPES` was already the household-composition-registry
  counterpart to `SERVICE_BUILDING_TYPES` (same `ArchetypeSpec`/
  `ServiceBuildingTypeSpec` shape, same per-JSON-file loading pattern) but
  was only reachable via the deep `occupancy.households` path. Downstream
  consumers can now do `sorted(occupancy.HOUSEHOLD_ARCHETYPES)` to
  enumerate/validate registered household-archetype ids at runtime instead
  of hand-copying the list.
- `occupancy.EQUIPMENT_TYPES` promoted to the top-level public API
  (`occupancy/__init__.py`), mirroring `SERVICE_BUILDING_TYPES`'s/
  `HOUSEHOLD_ARCHETYPES`'s promotion above — resolves buem's
  `occupancy_module_activities.md` item 1 ("promote a top-level
  household-equipment registry export"). The live `dict[str, EquipmentSpec]`
  of the 29 registered household equipment ids (same object
  `households.electricity.default_equipment_table()` copies from, so it
  can't drift out of sync with a future `equipment.json` addition).
  Downstream consumers (e.g. buem's `building.equipment` field validation)
  can now do `set(occupancy.EQUIPMENT_TYPES)` instead of hand-copying the
  29 ids into their own constant/schema enum.
- Boolean `cooking_active` column on the generated occupancy profile
  (`ElectricityConsumptionProfile`/`ServiceBuildingProfile`, wherever
  equipment is generated), and a matching optional 5th key in
  `to_buem_profiles()`'s returned dict when present. True whenever the
  `"kitchen"` equipment category (hob/oven/microwave/kettle/
  small_cooking_group for households; the equivalent items in restaurant/
  bakery/school service-building types) is drawing above-standby power —
  derived from the exact same per-item stochastic draws that already
  produce `total_power_kwh` (new `category_totals=` param on
  `core/equipment.py::generate_equipment_power`), not a second,
  independently-seeded pass. Resolves buem's `dhw_cooking_heat_handoff.md`
  ask #2 ("expose a separable cooking activity signal") — lets a future
  gas-cooking-energy term be driven by real per-building cooking timing
  instead of a flat national average. Reuses existing kitchen-equipment
  generation; no new modeling capability or data source.

### Changed

- **Breaking**: `HouseholdProfile`/`ServiceBuildingProfile`'s `seed=None`
  default no longer seeds from OS entropy — it now resolves to a
  deterministic hash of the profile's own construction inputs (new
  `core/seed.py::derive_default_seed`, hashing
  `(building_type_or_"household", num_persons_or_capacity, year,
  archetype, region)`), and that resolved value overwrites `self.seed` so
  downstream consumers relying on it (e.g. `ElectricityConsumptionProfile`'s
  `self.seed = self.occupancy_profile.seed` fallback and its ownership-draw
  seed offset) inherit the same determinism automatically. Resolves the
  "Seed ownership" item in buem's `occupancy_gains_handoff.md` (raised
  2026-08-07, previously unimplemented): a caller no longer needs to pass
  an explicit `seed=` for reproducibility, and — unlike buem's own
  `DEFAULT_SEED = 42` stopgap this replaces the need for — different
  buildings/households now get different (not identical) default draws.
  Passing an explicit `seed=` is unaffected and still takes priority. Same
  Alpha-package breaking-change posture as `markov_chain_crest` above:
  accepted deliberately, numeric output for any caller currently relying on
  `seed=None`'s old non-determinism (there shouldn't be any, by
  definition) or on OS-entropy randomness changes.

- **Breaking**: `working_couple` archetype's `generator` field changed
  from `"markov_chain"` to `"markov_chain_crest"`
  (`households/data/archetypes/working_couple.json`) — its numeric output
  changes for the same seed vs. earlier releases, since it now draws real
  CREST transition data instead of the synthesized persistence-blend
  formula (see the `markov_chain_crest` `Added` entry above). Deliberately
  accepted (package is Alpha; real data is strictly better). The original
  `markov_chain` generator is unchanged and still registered/available for
  any other caller/archetype.

## [3.1.0] - 2026-08-10

### Changed

- Removed the `numpy<3`/`pandas<3` upper-bound caps from `pyproject.toml`/`meta.yaml`
  (floors only now: `numpy>=1.26`, `pandas>=2.0`). The caps weren't actually being
  enforced in practice — `occupancy_env`'s `pip install -e . --no-deps` workflow
  skips dependency version checks entirely — and the full `pytest` suite (69/69)
  passes clean on numpy 2.5.1/pandas 3.0.5. `infrastructure/env/occupancy_env.yml`'s
  hard `=1.26.*`/`=2.2.*` pins relaxed to match.

### Added

- `to_buem_profiles(floor_area_m2=..., gain_w_per_m2=...)`: optional
  area-normalized equipment/lighting internal-gain component, **blended
  with** (not replacing) the existing per-occupant `Q_ig` calculation.
  Resolves buem's `occupancy_gains_handoff.md` Gap 1 (internal gains were
  per-occupant kW only, floor area never entered the calculation) on
  occupancy's side, per the ownership boundary in `CLAUDE.md`: occupancy
  owns all occupant/equipment-behavior modeling, buem should not need its
  own gain-density table. New optional `gain_w_per_m2` field on
  `ArchetypeSpec`/`ServiceBuildingTypeSpec` (`None` by default — no
  behavior change unless a type opts in) carries a per-type W/m² density
  through to `OccupancyResult.gain_w_per_m2`; all 8 service-building types
  now set an illustrative value (ASHRAE 90.1 Table 9.5.1 lighting power
  density plus, for kitchen/refrigeration-heavy types, an illustrative
  equipment margin — see each type's `schedule.json` `_comment`; not
  survey-calibrated). Left unset for household archetypes deliberately
  (lower-priority case per the handoff doc). The area component is scaled
  by the same per-hour occupant-presence fraction as `occ_nothome`, so it
  contributes nothing when the building is empty rather than adding a flat
  24/7 term. Passing `floor_area_m2` without a resolvable `gain_w_per_m2`
  (neither the kwarg nor `result.gain_w_per_m2`) raises `ValueError` rather
  than silently guessing a density or skipping the component.
- `to_buem_profiles(elec_load=...)`: accepts an externally-sourced
  `pd.Series` as `elecLoad` instead of requiring a `total_power_kwh` column
  on `result.profile`. Lets `Q_ig`/`occ_nothome`/`occ_sleeping` still be
  derived from occupancy's own generated presence pattern when elecLoad
  comes from somewhere else (buem, real metering, a future pylovo-driven
  scenario) — scaffolding for the cross-repo multi-profile/pylovo direction
  noted in `.claude/open.md`. Raises `ValueError` if the given series
  doesn't cover `result.profile`'s index after reindexing.
- `occupancy.SERVICE_BUILDING_TYPES` promoted to the top-level public API
  (`occupancy/__init__.py`, alongside the profile classes) so downstream
  consumers can enumerate/validate registered building-type ids at runtime
  (`sorted(occupancy.SERVICE_BUILDING_TYPES)`) instead of hand-copying the
  list into their own schema — resolves buem's `occupancy_gains_handoff.md`
  Gap 3 (registry duplication risk) on occupancy's side; the dict itself
  was already accessible via the deep `occupancy.services_buildings` path,
  this just makes it part of the documented-stable surface.

## [3.0.0] - 2026-07-29

### Added

- `occupancy.core.buem_adapter.to_buem_profiles()` (also exported as
  `occupancy.to_buem_profiles`): converts an `OccupancyResult` into the four
  `pd.Series` buem's `ModelBUEM` requires in `cfg` — `Q_ig`, `elecLoad`,
  `occ_nothome`, `occ_sleeping` — confirmed against
  `buem.thermal.model_buem.ModelBUEM._addPara`/`_addConstraints_sequential`,
  which raise `ValueError` if any of the four is missing. `elecLoad` reuses
  the existing `total_power_kwh` equipment output; `occ_nothome` is
  `1 - n_present / num_persons`.
- `Q_ig` (internal gains, kW, building-total) is derived from
  `n_present`/`n_active` using a per-occupant heat-gain split
  (present-but-inactive vs. active), sourced from a new
  `heat_gain_present_kw`/`heat_gain_active_kw` pair on each household
  archetype and service-building type (ISO 7730 / ASHRAE Fundamentals
  Ch. 18-informed, illustrative, not survey-calibrated) — e.g. school
  (0.085/0.120 kW) and supermarket (0.100/0.180 kW) now differ, rather than
  every building sharing one hardcoded constant. `to_buem_profiles()` falls
  back to its own module constants only when a result carries no per-type
  value.
- `occ_sleeping` is now real generator output, not a heuristic:
  `core/occupancy_engine.py`'s three generators (`binomial_independent`,
  `markov_chain`, `fixed_schedule`) all emit a new `n_asleep` column, drawn
  from the present-but-inactive occupant share via a new
  `asleep_probabilities` `(24, 2)` array (conditional probability of being
  asleep rather than just quietly present-inactive). All 5 household
  archetypes now define `asleep_probabilities` (illustrative, hand-authored
  curves peaking overnight, shaped per archetype — e.g. `student_shared`
  shifted several hours later, `retired_single` with a small midday-nap
  allowance). Service buildings never set it, so `n_asleep` is always `0`
  for the 4 current building types without special-casing
  `fixed_schedule` — households and service buildings share one output
  schema either way. `to_buem_profiles()` uses `n_asleep` directly when
  present; the previous 23:00–07:00 window heuristic is now only a fallback
  for profiles/DataFrames that predate this column.
- `ElectricityConsumptionProfile.to_result()` — previously only
  `HouseholdProfile.to_result()`/`ServiceBuildingProfile.to_result()`
  existed, and a bare `HouseholdProfile.to_result()` has no
  `total_power_kwh` column (equipment lives in the separate
  `ElectricityConsumptionProfile` wrapper for households only). This closes
  that asymmetry so both household and service-building results reach
  `to_buem_profiles()` the same way.
- New `hourly_occupancy_curve` occupancy-generation strategy
  (`core/occupancy_engine.py`): an explicit 24-hour occupancy-fraction
  table (weekday/weekend), for building types whose day-shape a single
  open/close window + flat peak (`fixed_schedule`) can't represent — a
  hotel's near-continuous overnight guest presence plus checkout/check-in
  peaks, for instance. Shaped like published DOE/ASHRAE 90.1
  prototype-building `Schedule:Compact` fractional schedules.
  `ServiceBuildingTypeSpec`/`ServiceBuildingProfile` also gain
  `asleep_probabilities` (same field, same mechanism households already
  had) so a service-building type can have genuine sleeping occupants;
  `to_buem_profiles()`'s `occ_sleeping` no longer special-cases
  `building_type == "household"` — it uses real `n_asleep` output for any
  building type that has it.
- Four new service-building types, informed by DOE/NREL Commercial
  Reference Building Models (Deru et al. 2011), ASHRAE 90.1 Table 9.5.1,
  and ASHRAE 62.1 Table 6-1 (occupant densities/LPD — see each type's
  `schedule.json` `_comment` for exact citations; still illustrative/
  hand-interpolated, not a literal reproduction of a published schedule):
  `hotel` (uses `hourly_occupancy_curve`, the first building type with
  genuine `asleep_probabilities`), `bakery` (small retail, early opening),
  `warehouse` (sparse occupant density, weekday-only), `clinic` (outpatient
  healthcare, weekday + partial-Saturday hours — distinct from a 24/7
  hospital, which isn't modeled). 8 service-building types total.

### Breaking

- Occupancy profile DataFrames (both households and service buildings) gain
  a new `n_asleep` column between `n_active` and `activity` —
  `list(profile.columns)` changes from `["n_present", "n_active",
  "activity", ...]` to `["n_present", "n_active", "n_asleep", "activity",
  ...]`. `OccupancyGenerationContext` gains an `asleep_probabilities` field
  (default all-zero, so existing callers that don't pass it are
  unaffected). `ArchetypeSpec`/`ServiceBuildingTypeSpec` gain
  `asleep_probabilities`/`heat_gain_present_kw`/`heat_gain_active_kw`
  fields (all with defaults, so existing archetype/building-type JSON
  without them still loads). `OccupancyResult` gains
  `heat_gain_present_kw`/`heat_gain_active_kw` (both `None`-default).

## [2.0.0] - 2026-07-24

### Added (household equipment expansion)

- `households/data/equipment.json` expanded from 7 illustrative appliances
  to 29 real ones (Cold, Consumer Electronics + ICT, Cooking, Wet
  categories), plus a new aggregate `lighting` item. `ownership_probability`,
  `rated_power_kw`, and `standby_power_kw` are sourced from the CREST
  Domestic Electricity Demand Model 1.0e (Richardson, Thomson, Infield --
  Loughborough University CREST, obtained via the paper's own public
  download link); hourly weekday/weekend weight shapes remain this repo's
  own illustrative arrays, calibrated so each item's expected annual
  triggered-use energy roughly matches CREST's reported figure. Water
  heating and Electric Space Heating categories are deliberately excluded
  (thermal loads belonging to buem's domain). See
  `.claude/residential/resolved.md` for the full attribution/license
  rationale.
- `ownership_probability` (previously defined in `EquipmentSpec` but
  unused) is now wired up: each household draws, once per seed, whether it
  owns each sub-1.0-probability item (`ElectricityConsumptionProfile._owned_by_name`).
- New `has_lighting` flag (`ElectricityConsumptionProfile`, `ScenarioConfig`,
  CLI, `default_scenario.json`), alongside the existing `has_*` flags —
  each now gates a *list* of individual equipment items rather than one
  (e.g. `has_fridge` covers `chest_freezer`/`fridge_freezer`/`refrigerator`/
  `upright_freezer`).

### Breaking

- Full restructuring for households + service buildings. `src/occupancy/internal_gains/`
  and `src/occupancy/electricity/` are removed; root `configs/` is removed
  (each subpackage now bundles its own `data/` via `importlib.resources`,
  no more dual source-of-truth). `src/occupancy/_defaults.py` is removed.
  Top-level `from occupancy import OccupancyProfile, ElectricityConsumptionProfile,
  OccupancyResult` continues to work (now aliased to the new
  `HouseholdProfile`); deep import paths do not — update
  `occupancy.internal_gains.occupancy_profile.OccupancyProfile` →
  `occupancy.households.HouseholdProfile`, and
  `occupancy.electricity.electricity_consumption.ElectricityConsumptionProfile`
  → `occupancy.households.ElectricityConsumptionProfile`.
- Occupancy profile columns renamed `n_home` → `n_present` (generalized for
  service buildings, which don't have a "home"); `activity` values renamed
  `not_home`/`at_home_inactive`/`at_home_active` →
  `not_present`/`present_inactive`/`present_active`.
- `ElectricityConsumptionProfile`'s `weightage_table` constructor arg and
  `get_weightage_table()` method are replaced by `equipment` and
  `get_equipment_table()`, returning `dict[str, EquipmentSpec]` instead of
  `dict[str, ApplianceWeights]`. `ScenarioConfig`'s JSON schema:
  `electricity.weightage_table` → `electricity.equipment`.
- Equipment item names changed with the CREST-informed expansion above:
  `fridge` → `chest_freezer`/`fridge_freezer`/`refrigerator`/
  `upright_freezer`; `cooking` → `hob`/`oven`/`microwave`/`kettle`/
  `small_cooking_group`; `laundry` → `dish_washer`/`tumble_dryer`/
  `washing_machine`/`washer_dryer`; `tv` → `tv_1`/`tv_2`/`tv_3`/`vcr_dvd`/
  `tv_receiver_box`; `cleaning` → `vacuum`; `other` → 8 named electronics
  items. `has_*` flags keep their old names and behavior (each now maps to
  the corresponding list of new item names).

### Added

- `src/occupancy/core/`: shared engine used by both households and service
  buildings — `occupancy_engine.py` (pluggable generator-strategy registry:
  `binomial_independent`, `markov_chain`, `fixed_schedule`), `equipment.py`
  (config-driven `EquipmentSpec` + trigger-strategy registry:
  `probabilistic_event`, `flat_always_on`, `sessions_per_week`,
  `linear_in_occupants`), `result.py` (`OccupancyResult`, now wired up as
  the shared output contract with `building_type`/`region` fields).
- `src/occupancy/households/`: household occupancy + electricity modeling,
  with a `HOUSEHOLD_ARCHETYPES` registry (`generic`, `working_couple`,
  `family_with_children`, `retired_single`, `student_shared`) loaded from
  `data/archetypes/*.json`. `fridge`, `ironing`, `other` — previously
  hardcoded with no JSON representation — are now `EquipmentSpec` rows like
  the other 4 appliances.
- `working_couple` archetype uses the new `markov_chain` generator as a
  proof-of-concept: a persistence-parameterized Markov chain over active-
  occupant count (inspired by the CREST/Richardson/tsorb transition-
  probability-matrix approach), synthesized at runtime from this repo's own
  validated hourly probability arrays — not copied from any external
  survey dataset. Other archetypes keep the original `binomial_independent`
  generator (bit-for-bit reproducible under the same seed).
- `src/occupancy/services_buildings/`: service (non-residential) building
  modeling, starting with `supermarket`, `office`, `restaurant`, `school`.
  Each type is a thin module (config path + registration) backed by
  `data/<type>/{schedule.json,equipment.json}`; new types register via
  `SERVICE_BUILDING_TYPES`.
- CLI: `--building-type`, `--archetype`, `--region` flags (all default to
  the pre-restructuring household behavior).
- `validate.py` — repo-root validation script for conda env, CLI, tests, and
  package structure checks.
- `push.ps1` — Windows push workflow ported from `UU-BUEM/weather`; supports
  conventional commit validation, tag creation, and changelog body auto-read.

### Changed

- `.github/workflows/ci.yml`: `actions/checkout@v6`, `setup-miniconda@v4`
  (auto-activate, fixes MultipleKeysError), `codecov-action@v6`, added
  `fetch-depth: 0` so `setuptools-scm` reads full tag history in CI.
- `.github/workflows/release.yml`: `actions/checkout@v6`.
- `pyproject.toml`: renamed `write_to` → `version_file` (setuptools-scm ≥ 8).
- `src/occupancy/__init__.py`: fallback version `"1.1.0"` → `"unknown"` to
  avoid silently reporting a stale version number when `_version.py` is absent.
- `.gitignore`: added `push.ps1` and `.commit-message.md`.

## [1.1.0] - 2026-05-18

### Added

- `configs/occupancy_probabilities.json` — default 24-hour home/active
  probability arrays (weekday/weekend) extracted from Python source.
- `configs/electricity_weightage.json` — default hourly usage-weight tables
  for all four appliances (tv, cooking, laundry, cleaning).
- `src/occupancy/_defaults.py` — single loader that reads both JSON files at
  import time and exposes `HOURLY_HOME_PROBABILITIES`,
  `HOURLY_ACTIVE_PROBABILITIES`, and `WEIGHTAGE_TABLE`.
- `src/occupancy/config/` subpackage (`config.py` + `__init__.py`) with
  `importlib.resources`-based path resolution for bundled JSON defaults.
- `src/occupancy/visualization/plots.py` — `plot_weekly_active_occupants`
  separated from core module so matplotlib is not a hard dependency.
- `OccupancyResult` dataclass — typed output contract (profile, year,
  num_persons, generated_at) consumed by downstream modules.
- `conda_build_config.yaml` — numpy=1.26 pin, aligns with `UU-BUEM/weather`.
- `.env.example` — documents `OCCUPANCY_OUTPUT_DIR` environment variable.
- `.github/workflows/ci.yml` — CI pipeline: lint, type-check, tests, CLI
  smoke test, Codecov upload.
- `.github/workflows/release.yml` — auto-publish build artifacts to GitHub
  Releases on `v*` tag push.

### Changed

- Python baseline raised to 3.12 everywhere (pyproject.toml, meta.yaml,
  ci.yml, occupancy_env.yml); removes pre-release 3.14 dependency.
- `ScenarioConfig.default()` uses `importlib.resources` instead of fragile
  four-level `Path(__file__).parent` traversal.
- `meta.yaml` overhauled: Jinja2 version templating from git tag, `pip install
  . --no-deps -vv` build script, pinned numpy/pandas run deps, pip in host.
- `infrastructure/env/occupancy_env.yml` pinned: numpy=1.26.*, pandas=2.2.*,
  pytest=8.*, pytest-cov=5.*; ruff/mypy moved to pip subsection; `-e .` entry
  removed (must be run separately from repo root).
- Docker base image standardised to `continuumio/miniconda3:24.1.2-0` (pinned,
  aligns with weather); bind-mount pattern replaces build-time `COPY src/`;
  OCI LABEL metadata added.
- `setup.ps1` / `setup.bat` now run `pip install -e . --no-deps` and include
  post-install `python -m occupancy --help` verification.
- `pyproject.toml`: dep upper bounds (numpy<3, pandas<3), wheel added to
  build-system.requires, ruff/mypy target updated to py312.

### Fixed

- Deleted `setup.py` stub (conflicted with pyproject.toml build system).
- `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` added to both workflows (Node 20
  deprecation on GitHub Actions).
- `contents: write` permission added to release workflow (resolved 403 error
  when creating GitHub Releases with default read-only token).
- `!src/occupancy/config/data/` negation added to `.gitignore` so bundled
  JSON config files are not excluded by the top-level `data/` rule.

## [0.1.0] - 2026-05-15

### Added

- Occupancy-native package API with `occupancy` CLI.
- `src/occupancy/__init__.py`, `src/occupancy/__main__.py`, and `src/occupancy/cli.py`.
- Clean conda environment, container, and setup scripts for independent repo usage.

### Changed

- Refactored occupancy and electricity modules to remove BuEM/weather coupling.
- Updated package metadata, script entry points, and repository URLs.
- Reduced dependencies to those actually required for occupancy modeling.

### Fixed

- Invalid import path from BuEM monorepo in electricity module.
- Multiple weather-template leftovers in docs and infrastructure.

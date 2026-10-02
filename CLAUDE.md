# CLAUDE.md

Guidance for Claude Code (and other agents) working in this repository.

## What this repo is

`occupancy` generates stochastic hourly occupancy states and electricity-
demand profiles for **households and service buildings**. It is the
intended **intermediate layer** feeding
[UU-BUEM/buem](https://github.com/UU-BUEM/buem), an open-source building
thermal-demand module: buem models only the building envelope (walls, roof,
floor, windows, doors, ventilation, U-values) and takes no occupancy/
internal-gains/electricity input itself — that's this package's job to
supply.

**Ownership boundary (user directive, 2026-08-07):** every occupancy-related
activity — people-presence/activity/sleep state, equipment on/off and power
draw, and any future occupant- or equipment-driven behavior — is modeled
inside *this* package, not downstream. buem owns the envelope/thermal
network and consumes occupancy's output; it should never need to reimplement
occupant- or equipment-behavior logic of its own (e.g. its own internal-
gains-density table) just because occupancy's existing output doesn't yet
cover a given case — extend occupancy instead. This is why, e.g., Gap 1's
floor-area-normalized internal gains (see `to_buem_profiles()`'s
`floor_area_m2`/`gain_w_per_m2`) were implemented on occupancy's side rather
than left to buem to compute independently.

The original design proposal is in
`docs/plans/equipment-service-buildings-architecture.md`, superseded during
implementation; that file points to where the actual rationale now lives:
this file (architecture, extension points), `.claude/open.md` /
`.claude/resolved.md` (research into pyCREST, richardsonpy, tsorb, StROBe,
simpy, mesa; why the Markov-chain generator exists; why simpy/mesa were not
adopted), and `CHANGELOG.md`'s `[Unreleased]` section (breaking changes and
additions).

## Repository layout

```text
occupancy/
├── src/occupancy/
│   ├── __init__.py          # public API: HouseholdProfile, ServiceBuildingProfile,
│   │                        #   ElectricityConsumptionProfile, OccupancyResult,
│   │                        #   to_buem_profiles,
│   │                        #   + OccupancyProfile = HouseholdProfile (back-compat alias)
│   ├── cli.py                 # occupancy CLI: --building-type/--archetype/--region/...
│   ├── config/                 # CLI-facing ScenarioConfig (JSON scenario files)
│   ├── core/                   # shared engine used by BOTH households and services_buildings
│   │   ├── occupancy_engine.py   # generator-strategy registry (see below)
│   │   ├── equipment.py          # EquipmentSpec + trigger-strategy registry
│   │   ├── loader.py             # importlib.resources JSON loading helpers
│   │   ├── result.py             # OccupancyResult (shared output contract)
│   │   └── buem_adapter.py       # OccupancyResult -> buem's Q_ig/elecLoad/occ_nothome/occ_sleeping
│   ├── households/             # base __init__.py registers HOUSEHOLD_ARCHETYPES
│   │   ├── archetypes.py         # ArchetypeSpec + registry, loads data/archetypes/*.json
│   │   ├── household_profile.py  # HouseholdProfile
│   │   ├── electricity.py        # ElectricityConsumptionProfile (EquipmentSpec-driven)
│   │   └── data/{archetypes/*.json, equipment.json}
│   ├── services_buildings/     # base __init__.py registers SERVICE_BUILDING_TYPES
│   │   ├── building_types.py     # ServiceBuildingTypeSpec + registry
│   │   ├── building_profile.py   # ServiceBuildingProfile
│   │   ├── {supermarket,office,restaurant,school,hotel,bakery,warehouse,clinic}.py
│   │   │                        #   one thin file per type (8 today)
│   │   └── data/<type>/{schedule.json, equipment.json}
│   └── visualization/
```

## Core data flow

`JSON config` → `ScenarioConfig` (CLI overrides) → `HouseholdProfile` /
`ServiceBuildingProfile` → (household path only) optional
`ElectricityConsumptionProfile` → CSV.

Household and service-building profiles both dispatch to the **same**
`core/occupancy_engine.py` generator registry and `core/equipment.py`
equipment/strategy registry — households and service buildings are two
config-driven consumers of one shared engine, not parallel implementations.

## Extension points (the whole point of this architecture)

- **New household appliance**: add a row to
  `households/data/equipment.json` (29 items today, CREST-sourced
  ownership/power figures — see `.claude/residential/resolved.md` for
  provenance) or a per-archetype override in
  `households/data/archetypes/<name>.json`'s `equipment_overrides`. Only
  write new Python if the trigger logic is genuinely novel — then register
  it via `core.equipment.register_strategy`.
- **New household archetype**: add
  `households/data/archetypes/<name>.json` (probabilities, generator,
  equipment overrides). No code change; `households/archetypes.py` loads
  every JSON file in that folder automatically.
- **New service-building type**: add
  `services_buildings/data/<type>/{schedule.json,equipment.json}` plus a
  thin `services_buildings/<type>.py` that calls
  `load_building_type("<type>")`, then import it from
  `services_buildings/__init__.py`.
- **New occupancy-generation strategy** (e.g. from a future reference
  occupancy module the user supplies): implement a function matching
  `core.occupancy_engine.GeneratorFn` and register it with
  `register_generator`. Currently registered: `binomial_independent`
  (default, original algorithm), `markov_chain` (persistence-parameterized,
  used by `working_couple`), `fixed_schedule` (single open/close window +
  flat peak — most service buildings), `hourly_occupancy_curve` (explicit
  24-hour occupancy-fraction table, weekday/weekend — for building types
  whose day-shape a single rectangle can't represent, e.g. `hotel`'s
  near-continuous overnight-guest presence with checkout/check-in peaks;
  mirrors the shape of published DOE/ASHRAE 90.1 prototype-building
  `Schedule:Compact` fractional schedules more closely than
  `fixed_schedule`).
- **A building type with genuine overnight/sleeping occupants**: set
  `asleep_probabilities` in that type's `schedule.json` (same `(24, 2)`
  shape and semantics as a household archetype's field of the same name —
  conditional probability that a present-but-inactive occupant is asleep).
  Every generator threads it through to a shared `n_asleep` output column,
  which `core.buem_adapter.to_buem_profiles()` consumes directly as
  buem's `occ_sleeping` for *any* building type, not just households —
  see `hotel`'s `schedule.json` for a working example. Building types that
  never set it (most service buildings) simply always have `n_asleep == 0`.

## Conventions

- No hardcoded numeric arrays in Python — everything lives in bundled JSON
  under each subpackage's own `data/`, loaded via `importlib.resources`
  (see `core/loader.py`). There is a single source of truth per subpackage
  — no root-level `configs/` duplicate (that dual-source setup was removed
  during the households/services_buildings restructuring).
- Conventional Commits for commit messages.
- Update `CHANGELOG.md` under `[Unreleased]` for user-facing changes (see
  `CONTRIBUTING.md`).

## Dev commands

```bash
ruff format .
ruff check .
pytest
mypy src
python validate.py
```

## Known limitations / follow-ups

See `.claude/open.md` (cross-cutting), `.claude/residential/open.md`
(households), and `.claude/services/open.md` (service buildings) for the
live lists. Notably:

- `markov_chain`'s transition data is synthesized at runtime from this
  repo's own validated hourly probability arrays (see
  `core/occupancy_engine.py` docstring) — it is **not** calibrated against
  real regional survey data. Sourcing real (e.g. Dutch) time-use survey
  data is flagged as follow-up, not fabricated.
- CLI/config capacity resolution for service buildings only respects the
  `--persons`/`--capacity` CLI flag, not a scenario config file's
  `num_persons` — needs a dedicated `capacity` config field.
- `region` is threaded through the data model (`OccupancyResult.region`,
  archetype/building-type JSON `region` field) but only one region's data
  (`NL`/generic-EU) is populated; adding a new region is a config addition.

# Occupancy

Stochastic occupancy and electricity-demand profile modeling for households
and service buildings, for UU-BUEM. Feeds
[UU-BUEM/buem](https://github.com/UU-BUEM/buem) (a pure envelope/thermal
model) with the occupancy/internal-gains/electricity input it doesn't
generate itself.

## What This Repo Does

This package generates stochastic hourly occupancy states and derives total
hourly electricity demand from those states, for:

- **Households** — via composition archetypes (`generic`, `working_couple`,
  `family_with_children`, `retired_single`, `student_shared`, ...).
- **Service buildings** — `supermarket`, `office`, `restaurant`, `school`,
  `hotel`, `bakery`, `warehouse`, `clinic`, easily extended with more
  types.

Core models:

- Household occupancy: `HouseholdProfile` (aliased as `OccupancyProfile`)
- Household electricity: `ElectricityConsumptionProfile`
- Service building occupancy + electricity: `ServiceBuildingProfile`

Everything — occupancy probabilities, household archetypes, appliance/
equipment specs, service-building schedules — is config-driven JSON, not
hardcoded Python. Adding a new appliance, household archetype, or building
type is a config addition; see `CLAUDE.md` and
`docs/plans/equipment-service-buildings-architecture.md` for the extension
points and design rationale.

## Repository Layout

```text
occupancy/
├── src/
│   └── occupancy/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── config/                 # CLI-facing ScenarioConfig
│       │   ├── __init__.py
│       │   ├── config.py
│       │   └── data/default_scenario.json
│       ├── core/                   # shared engine (households + services_buildings)
│       │   ├── equipment.py          # EquipmentSpec + trigger-strategy registry
│       │   ├── occupancy_engine.py   # generator-strategy registry
│       │   ├── loader.py
│       │   └── result.py             # OccupancyResult
│       ├── households/
│       │   ├── __init__.py           # HOUSEHOLD_ARCHETYPES registry
│       │   ├── archetypes.py
│       │   ├── household_profile.py
│       │   ├── electricity.py
│       │   └── data/
│       │       ├── archetypes/*.json
│       │       └── equipment.json
│       ├── services_buildings/
│       │   ├── __init__.py           # SERVICE_BUILDING_TYPES registry
│       │   ├── building_profile.py
│       │   ├── building_types.py
│       │   ├── supermarket.py
│       │   ├── office.py
│       │   ├── restaurant.py
│       │   ├── school.py
│       │   ├── hotel.py
│       │   ├── bakery.py
│       │   ├── warehouse.py
│       │   ├── clinic.py
│       │   └── data/<type>/{schedule,equipment}.json
│       └── visualization/
│           ├── __init__.py
│           └── plots.py
├── infrastructure/
│   ├── env/
│   │   └── occupancy_env.yml
│   └── container/
│       ├── Dockerfile
│       ├── docker-compose.yml
│       └── occupancy.def
├── tests/
├── pyproject.toml
├── meta.yaml
├── setup.ps1
└── setup.bat
```

## Quickstart (Conda)

```powershell
# 1. Create/update the conda environment and install the 'occupancy' command:
.\setup.ps1          # PowerShell
setup.bat            # CMD

# 2. Activate and verify:
conda activate occupancy_env
occupancy --help
```

> `conda develop src` is **not** used here. `setup.ps1` creates the conda
> environment and runs `pip install -e . --no-deps` from the repo root so the
> editable install works correctly.

Generate a household occupancy profile (defaults to the `generic` archetype):

```bash
occupancy --year 2026 --persons 3 --seed 42 --output outputs/occupancy.csv
```

Generate occupancy + electricity for a specific household archetype:

```bash
occupancy --year 2026 --persons 2 --archetype working_couple --seed 42 \
  --include-electricity --output outputs/working_couple.csv
```

Generate a service building profile:

```bash
occupancy --building-type supermarket --year 2026 --seed 42 \
  --include-electricity --output outputs/supermarket.csv
```

Run a fully reproducible scenario from config:

```bash
occupancy --config path/to/scenario.json
```

## Configuration

Every numerical default — occupancy probabilities, household archetypes,
appliance/equipment specs, service-building schedules — is bundled JSON
under each subpackage's own `data/` folder (`config/data/`,
`households/data/`, `services_buildings/data/`), loaded via
`importlib.resources`. No hardcoded arrays in Python source.

| Location | Contents |
| --- | --- |
| `config/data/default_scenario.json` | Year, persons/capacity, seed, building type, appliance flags, output path |
| `households/data/archetypes/*.json` | Per-archetype occupancy probabilities, generator strategy, equipment overrides |
| `households/data/equipment.json` | 29 household appliances as `EquipmentSpec` rows (ownership/power figures sourced from the CREST Domestic Electricity Demand Model) |
| `services_buildings/data/<type>/schedule.json` | Capacity, generator strategy + params (open hours, etc.) |
| `services_buildings/data/<type>/equipment.json` | That building type's `EquipmentSpec` rows |

Pass a custom scenario JSON via `--config` to override any subset of the
scenario/occupancy/electricity fields without touching the bundled defaults.
Adding a new appliance, household archetype, or service-building type is a
JSON addition — see `CLAUDE.md` for the registry mechanism.

## Feeding buem

[UU-BUEM/buem](https://github.com/UU-BUEM/buem)'s `ModelBUEM` requires four
`pd.Series` in its `cfg` dict — `Q_ig` (internal gains, kW), `elecLoad`
(electric load, kW), `occ_nothome` (fraction of occupants away, 0-1),
`occ_sleeping` (fraction asleep, 0-1) — and raises `ValueError` if any is
missing (`buem.thermal.model_buem.ModelBUEM._addPara`/
`_addConstraints_sequential`). `occupancy.to_buem_profiles()` builds all
four from an `OccupancyResult`:

```python
from occupancy import (
    ElectricityConsumptionProfile,
    HouseholdProfile,
    ServiceBuildingProfile,
    to_buem_profiles,
)

# Service buildings include equipment power by default.
office = ServiceBuildingProfile(building_type="office", year=2025, seed=1)
buem_inputs = to_buem_profiles(office.to_result())

# Households: equipment lives in ElectricityConsumptionProfile, not
# HouseholdProfile itself -- use its `.to_result()`, not the bare profile's.
household = HouseholdProfile(num_persons=3, year=2025, seed=1)
elec = ElectricityConsumptionProfile(occupancy_profile=household, seed=1)
buem_inputs = to_buem_profiles(elec.to_result())

cfg = {**cfg, **buem_inputs}  # merge into buem's cfg dict
```

`buem_inputs` is `{"Q_ig": pd.Series, "elecLoad": pd.Series, "occ_nothome":
pd.Series, "occ_sleeping": pd.Series}`, indexed the same as `result.profile`.
Notes:

- `Q_ig` is derived from `n_present`/`n_active`, split into present-but-
  inactive vs. active occupants, each with its own per-occupant heat-gain
  constant. Those constants come from `heat_gain_present_kw`/
  `heat_gain_active_kw` on the profile's originating archetype
  (`households/data/archetypes/*.json`) or building type
  (`services_buildings/data/<type>/schedule.json`) — e.g. office
  (0.100/0.130 kW) vs. supermarket (0.100/0.180 kW) vs. school
  (0.085/0.120 kW) — illustrative, ISO 7730 / ASHRAE Fundamentals
  Ch. 18-informed, not yet survey-calibrated. Pass `gain_present_kw`/
  `gain_active_kw` explicitly to override.
- `occ_sleeping` is real generator output: `core/occupancy_engine.py`'s
  generators emit an `n_asleep` column (drawn from the profile's
  `asleep_probabilities`), and `occ_sleeping = n_asleep / num_persons` —
  for *any* building type, not just households. Most service-building
  types never set `asleep_probabilities` (they're never occupied
  overnight) so `n_asleep` stays `0` for them, but `hotel` does and gets
  genuine sleeping occupants through the same mechanism. A fixed
  23:00–07:00 window heuristic is used only as a household-only fallback
  for profiles generated before this column existed.
- buem (`UU-BUEM/buem`)'s `cfg_attribute.py` now imports
  `from occupancy import ElectricityConsumptionProfile, HouseholdProfile,
  to_buem_profiles` and calls them in exactly the pattern shown above —
  the earlier `buem_occupancy` package-name mismatch this section used to
  document has been fixed on buem's side.

## Docker

```bash
# Build the image (bind-mounts src/ at runtime, including package data):
docker compose -f infrastructure/container/docker-compose.yml build

# Run (src/ is bind-mounted for live development):
docker compose -f infrastructure/container/docker-compose.yml up

# Standalone run:
docker run --rm occupancy:latest python -m occupancy --help
```

Output CSV is written to `outputs/` on the host via bind mount.

## Development Checks

```bash
ruff format .
ruff check .
pytest
mypy src
python validate.py
```

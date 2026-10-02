# Contributing

Thank you for contributing to occupancy.

## Development Setup

```powershell
# Creates the conda environment and installs the package in editable mode:
.\setup.ps1          # PowerShell
setup.bat            # CMD

conda activate occupancy_env
occupancy --help
```

> **Do not run `conda develop src`.**  Use `pip install -e . --no-deps` from
> the repo root instead (this is what `setup.ps1` does automatically).

## Config Files

All default numerical parameters live in bundled JSON under each
subpackage's own `data/` folder — edit these instead of touching Python
source:

- `src/occupancy/households/data/archetypes/*.json` — per-archetype
  occupancy probabilities, generator strategy, equipment overrides
- `src/occupancy/households/data/equipment.json` — household appliance
  specs
- `src/occupancy/services_buildings/data/<type>/schedule.json` /
  `equipment.json` — per building-type schedule and equipment specs
- `src/occupancy/config/data/default_scenario.json` — CLI scenario
  defaults (year, persons, building type, flags)

To test a custom scenario, pass `--config <path>` on the CLI or call
`load_scenario_config(path)` in Python. To add a new appliance, household
archetype, or service-building type, see the extension points in
`CLAUDE.md` — it's a config addition, not a Python change.

## Code Quality

```bash
ruff format .
ruff check .
pytest
mypy src
```

## Commit Style

Use Conventional Commits:

```text
feat: add occupancy CLI output options
fix: correct random-state handling in electricity model
docs: clarify conda setup for Windows
```

## Pull Requests

- Keep PRs focused and small.
- Include tests for behavior changes.
- Update `CHANGELOG.md` under `[Unreleased]`.
- Ensure CI or local checks pass before requesting review.

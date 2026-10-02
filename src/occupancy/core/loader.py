"""Shared package-data JSON loading, used by households/ and
services_buildings/.

Replaces the old fragile ``_defaults.py`` path traversal against a root
``configs/`` directory: every subpackage now loads its own bundled JSON via
``importlib.resources`` against its own ``data/`` folder, so there is a
single source of truth per subpackage instead of a duplicated root copy.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

import pandas as pd


def load_json_resource(package: str, relative_path: str) -> dict[str, Any]:
    """Load and parse a JSON file bundled inside ``package``'s data files."""
    target = files(package).joinpath(relative_path)
    with target.open("r", encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)
    return data


def load_csv_resource(
    package: str, relative_path: str, *, comment: str = "#"
) -> pd.DataFrame:
    """Load a bundled CSV as a DataFrame, e.g. a literature-sourced
    reference table a user may want to edit in place (see
    ``households/data/dhw_tapping_categories.csv``). ``comment`` rows
    (default ``#``-prefixed) are treated as documentation, not data --
    the same convention plain-text editors and spreadsheet tools both
    honour, so the file stays reviewable as a table without a
    side-channel JSON/README explaining it."""
    target = files(package).joinpath(relative_path)
    with target.open("r", encoding="utf-8") as handle:
        return pd.read_csv(handle, comment=comment)


def iter_json_resources(package: str, relative_dir: str) -> list[str]:
    """List the ``*.json`` filenames bundled under
    ``package``/``relative_dir``."""
    directory = files(package).joinpath(relative_dir)
    return sorted(
        entry.name
        for entry in directory.iterdir()
        if entry.name.endswith(".json") and not entry.name.startswith("_")
    )

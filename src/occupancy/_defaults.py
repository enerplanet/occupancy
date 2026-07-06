"""Load default numerical parameters from the packaged config/data/ directory."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

# Package-internal location (src/occupancy/config/data/*.json), bundled into
# the wheel via [tool.setuptools.package-data]. The repo-root configs/
# directory these files are mirrored from is a dev convenience only — it
# isn't shipped in an installed package, so resolving against __file__'s
# repo-root-relative position (the previous behavior) broke for anyone who
# `pip install`-ed rather than working from a source checkout.
_CONFIGS_DIR = Path(__file__).parent / "config" / "data"


def _read_json(filename: str) -> dict:
    with (_CONFIGS_DIR / filename).open(encoding="utf-8") as fh:
        return json.load(fh)


def _load_occupancy_probabilities() -> tuple[np.ndarray, np.ndarray]:
    data = _read_json("occupancy_probabilities.json")
    return (
        np.asarray(data["home_probabilities"], dtype=float),
        np.asarray(data["active_probabilities"], dtype=float),
    )


def _load_weightage_table() -> dict[str, dict[str, np.ndarray]]:
    data = _read_json("electricity_weightage.json")
    return {
        appliance: {
            "weekday": np.asarray(weights["weekday"], dtype=float),
            "weekend": np.asarray(weights["weekend"], dtype=float),
        }
        for appliance, weights in data.items()
        if not appliance.startswith("_")
    }


(
    HOURLY_HOME_PROBABILITIES,
    HOURLY_ACTIVE_PROBABILITIES,
) = _load_occupancy_probabilities()
WEIGHTAGE_TABLE = _load_weightage_table()

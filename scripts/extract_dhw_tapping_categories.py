"""One-time, reproducible extraction of real DHW tapping-fixture data into
``src/occupancy/households/data/dhw_tapping_categories.csv``.

Not part of the installed ``occupancy`` package -- a dev-only tool, run
once (or re-run if the source workbook is ever replaced), mirroring
``scripts/extract_crest_tpm.py``'s pattern exactly.

Unlike ``tpm_crest.json`` (pure derived data, "generated, do not
hand-edit"), the output CSV is *also* meant to stay directly user-editable
afterward -- see ``households/dhw.py``'s module docstring and
``docs/dhw/design.md``. Re-run this script only to reset to the
source-derived defaults, or to extract a different apportionment scheme;
hand-tuning individual rows for a specific scenario afterward is expected
and supported (``generate_dhw_draws()`` validates the table's shape, not
its exact values).

**Requires** ``openpyxl`` (not an ``occupancy`` runtime/dev dependency --
install ad hoc: ``pip install openpyxl`` or ``conda install -c conda-forge
openpyxl`` into the dev env before running this script).

**Source**: ``data/inputs/CREST_Demand_Model_v2.3.3.xlsm`` (McKenna,
Thomson -- Loughborough University CREST integrated thermal-electrical
model), gitignored and not committed to this repo (CC BY-NC-ND, same
posture as ``CREST_Domestic_electricity_demand_model_1.0e.xlsm`` -- no
redistribution of the raw workbook). Obtain it directly via the paper's
own public download link if missing locally; see ``.claude/residential/
dhw_cooking_literature_review.md`` for the full provenance trail.

**What this reads**:

- ``AppliancesAndWaterFixtures`` sheet, rows 46-49 (Basin/Sink/Shower/
  Bath): per-fixture ownership probability (col F), activity-profile link
  (col G), mean flow rate L/min (col P), mean cycle duration min (col R),
  and the workbook's own mean-volume figure (col Q, used only as a
  cross-check against flow_rate * duration).
- Same sheet, row 53 ("Hot water" summary cell, col E): the workbook's own
  aggregate household daily DHW total for its example dwelling.
- ``Dwellings`` sheet, row 5, col B ("Number of residents"): the reference
  household size that total and every per-fixture figure above apply to.

**One genuinely hybrid step**: the workbook gives an aggregate total but
not an independent per-fixture daily-volume split (see ``docs/dhw/
design.md``'s "one genuinely hybrid number" section for why). This script
apportions that total across fixtures using DHWcalc's (Jordan & Vajen
2005) own published relative category shares -- a *different*, German,
freely-published reference dataset, used here only for its relative
*shares*, not its absolute L/day totals. Change ``_DHWCALC_SHARES`` below
if a better-sourced split ever becomes available.

Usage::

    python scripts/extract_dhw_tapping_categories.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_XLSM_PATH = _REPO_ROOT / "data" / "inputs" / "CREST_Demand_Model_v2.3.3.xlsm"
_OUTPUT_PATH = (
    _REPO_ROOT
    / "src"
    / "occupancy"
    / "households"
    / "data"
    / "dhw_tapping_categories.csv"
)

_FIXTURES_SHEET = "AppliancesAndWaterFixtures"
_DWELLINGS_SHEET = "Dwellings"

# (row, workbook short-name) for each fixture, in the sheet's own order.
_FIXTURE_ROWS = [
    (46, "BASIN"),
    (47, "SINK"),
    (48, "SHOWER"),
    (49, "BATH"),
]
_COL_OWNERSHIP = 6  # F: "Proportion of dwellings with appliance"
_COL_ACTIVITY_LINK = 7  # G: "Associated activity use profile"
_COL_FLOW_RATE = 16  # P: "Mean cycle flow rate (litres/min)"
_COL_MEAN_VOLUME = 17  # Q: "Mean cycle flow volume (litre)" -- cross-check
_COL_DURATION = 18  # R: "Mean cycle duration (min)"

_HOT_WATER_TOTAL_ROW = 53
_COL_HOT_WATER_TOTAL = 5  # E

_RESIDENTS_ROW = 5
_COL_NUM_RESIDENTS = 2  # B

# Workbook short-name -> this repo's fixture_label / activity_link vocabulary.
_FIXTURE_LABELS = {
    "BASIN": "basin",
    "SINK": "kitchen_sink",
    "SHOWER": "shower",
    "BATH": "bath",
}
_ACTIVITY_LINKS = {
    "ACT_WASHDRESS": "washing_and_dressing",
    "ACT_COOKING": "cooking",
}

# Jordan & Vajen (2005) DHWcalc, Fig. 5's single-family-house IEA SHC
# Task 26 reference example -- relative *shares* of the 200 L/day total,
# by category. Applied here to CREST's own aggregate total (a different,
# real number) -- see this script's own docstring and docs/dhw/design.md.
_DHWCALC_SHARES = {
    "basin": 0.14,
    "kitchen_sink": 0.36,
    "shower": 0.40,
    "bath": 0.10,
}

# Regression anchors, confirmed by direct inspection this session. Catch a
# row/column-offset error in the read before it can silently corrupt the
# extracted data.
_ANCHOR_BASIN_OWNERSHIP = 0.994
_ANCHOR_HOT_WATER_TOTAL = 119.62586974793265
_ANCHOR_NUM_RESIDENTS = 1

_CSV_HEADER_COMMENT = """\
# Domestic hot water tapping-event reference categories.
#
# PRIMARY SOURCE (ownership_probability, flow_rate_l_per_min, duration_min,
# reference_num_persons): McKenna, E., Thomson, M. (2016) "High-resolution
# stochastic integrated thermal-electrical domestic demand model," Applied
# Energy 165. Numbers below are read directly off that model's own runtime
# workbook -- CREST_Demand_Model_v2.3.3.xlsm, sheets `AppliancesAndWater
# Fixtures` (rows 46-53) and `WaterUsage` (its own header cites, verbatim:
# "Data estimated from Clarke, A., Grant, N., Thornton, J., 2009
# Quantifying the energy and carbon effects of water saving: Final Report
# for the Environment Agency and Energy Saving Trust") -- not the paper's
# own text, which does not publish these numbers. See
# .claude/residential/dhw_cooking_literature_review.md for exactly where
# this workbook came from, and docs/dhw/design.md for the full
# extraction, including the plausible-but-hybrid derivation of
# events_per_day_reference below.
#
# Generated by scripts/extract_dhw_tapping_categories.py from the source
# workbook -- re-run that script to regenerate this file from scratch.
# Unlike tpm_crest.json, this file is also meant to stay directly
# user-editable afterward: change a row's numbers (or add a new row
# entirely) to fit your own scenario, and generate_dhw_draws() picks it
# up on the next run, no code change required.
#
# flow_rate_l_per_min * duration_min = each fixture's mean draw volume
# (this file does not store that volume separately -- households/dhw.py
# derives it on load, so editing flow_rate or duration is the one place
# to change a fixture's typical volume; per-event volume is then drawn
# stochastically around that mean via a Poisson distribution, matching
# the source workbook's own WaterUsage sheet, which carries this exact
# distribution shape -- not invented here).
#
# ownership_probability is real, per-fixture, from the workbook's
# "Proportion of dwellings with appliance" column -- basins and kitchen
# sinks are near-universal; showers and baths are not, and a household
# without a fixture draws zero from it, every run.
#
# reference_num_persons is not an assumption: the workbook's own
# `Dwellings` sheet example this data was read from has "Number of
# residents" set to this value. events_per_day_reference is the one
# genuinely hybrid figure here: the workbook gives an aggregate household
# total but not a clean independent per-fixture daily-volume split
# reachable without decompiling its VBA macros this session -- so that
# total is apportioned across rows using DHWcalc's (Jordan & Vajen 2005)
# relative category shares, a *different*, German, freely-published
# reference dataset, chosen only for its category proportions, not its
# absolute totals. Flagged explicitly, not smoothed over -- see
# docs/dhw/design.md.
#
# Both source studies are Western-European (UK, Germany) research
# baselines, neither Dutch -- this table is not NTA-8800-specific and
# is not expected to be. If per-region defaults are ever needed (e.g. for
# Germany, Austria, Czech Republic), add a sibling file following this
# repo's existing per-region convention (CLAUDE.md: new archetype/
# building-type JSON per region) -- e.g. dhw_tapping_categories_DE.csv --
# rather than editing this one in place.
#
# activity_link follows McKenna & Thomson's own fixture-to-activity
# assignment (Section 3.4): kitchen sink -> "cooking"; basin/shower/bath
# -> "washing_and_dressing". occupancy's generate_dhw_draws() uses this to
# pick a timing envelope -- see households/dhw.py's own module docstring
# for how each envelope is computed, and register_timing_envelope() to
# add a new one for a custom activity_link.
#
# Every row must share the same reference_num_persons value (the whole
# table is calibrated to one reference household) -- this is validated
# on load.
"""


def _cell(ws: Any, row: int, col: int) -> Any:
    return ws.cell(row=row, column=col).value


def main() -> None:
    try:
        import openpyxl
    except ImportError as exc:
        raise SystemExit(
            "openpyxl is required to run this script -- install ad hoc "
            "(`pip install openpyxl` or `conda install -c conda-forge "
            "openpyxl`), it is not an occupancy runtime/dev dependency."
        ) from exc

    if not _XLSM_PATH.exists():
        raise SystemExit(
            f"CREST workbook not found at {_XLSM_PATH}. Obtain it "
            "directly via McKenna & Thomson's (2016) own public download "
            "link (Loughborough University CREST); see "
            ".claude/residential/dhw_cooking_literature_review.md for "
            "provenance notes."
        )

    print(f"Reading {_XLSM_PATH} ...")
    workbook = openpyxl.load_workbook(
        _XLSM_PATH, read_only=True, data_only=True
    )
    fixtures_ws = workbook[_FIXTURES_SHEET]
    dwellings_ws = workbook[_DWELLINGS_SHEET]

    # Regression anchor checks before trusting anything else in the file.
    basin_ownership = _cell(fixtures_ws, _FIXTURE_ROWS[0][0], _COL_OWNERSHIP)
    if basin_ownership != _ANCHOR_BASIN_OWNERSHIP:
        raise SystemExit(
            f"Regression anchor check failed: {_FIXTURES_SHEET} row "
            f"{_FIXTURE_ROWS[0][0]} col {_COL_OWNERSHIP} (basin ownership) "
            f"read {basin_ownership!r}, expected {_ANCHOR_BASIN_OWNERSHIP!r}. "
            "The row/column layout may no longer match this workbook -- "
            "aborting rather than emitting silently wrong data."
        )
    hot_water_total = _cell(
        fixtures_ws, _HOT_WATER_TOTAL_ROW, _COL_HOT_WATER_TOTAL
    )
    if abs(hot_water_total - _ANCHOR_HOT_WATER_TOTAL) > 1e-6:
        raise SystemExit(
            f"Regression anchor check failed: {_FIXTURES_SHEET} row "
            f"{_HOT_WATER_TOTAL_ROW} col {_COL_HOT_WATER_TOTAL} (hot water "
            f"total) read {hot_water_total!r}, expected "
            f"{_ANCHOR_HOT_WATER_TOTAL!r}."
        )
    num_residents = _cell(dwellings_ws, _RESIDENTS_ROW, _COL_NUM_RESIDENTS)
    if num_residents != _ANCHOR_NUM_RESIDENTS:
        raise SystemExit(
            f"Regression anchor check failed: {_DWELLINGS_SHEET} row "
            f"{_RESIDENTS_ROW} col {_COL_NUM_RESIDENTS} (number of "
            f"residents) read {num_residents!r}, expected "
            f"{_ANCHOR_NUM_RESIDENTS!r}."
        )
    print("Regression anchor checks passed.")

    rows = []
    for row_num, short_name in _FIXTURE_ROWS:
        fixture_label = _FIXTURE_LABELS[short_name]
        ownership = float(_cell(fixtures_ws, row_num, _COL_OWNERSHIP))
        raw_activity = _cell(fixtures_ws, row_num, _COL_ACTIVITY_LINK)
        activity_link = _ACTIVITY_LINKS[raw_activity]
        flow_rate = float(_cell(fixtures_ws, row_num, _COL_FLOW_RATE))
        duration = float(_cell(fixtures_ws, row_num, _COL_DURATION))
        workbook_volume = float(_cell(fixtures_ws, row_num, _COL_MEAN_VOLUME))

        derived_volume = flow_rate * duration
        if abs(derived_volume - workbook_volume) > 0.05:
            raise SystemExit(
                f"{short_name} (row {row_num}): flow_rate * duration = "
                f"{derived_volume!r}, but the workbook's own mean-volume "
                f"column reads {workbook_volume!r} -- these should agree "
                "to within rounding; the column layout may have shifted."
            )

        share = _DHWCALC_SHARES[fixture_label]
        events_per_day = (share * hot_water_total) / derived_volume

        rows.append(
            {
                "fixture_label": fixture_label,
                "activity_link": activity_link,
                "ownership_probability": ownership,
                "flow_rate_l_per_min": flow_rate,
                "duration_min": duration,
                "events_per_day_reference": events_per_day,
                "reference_num_persons": int(num_residents),
            }
        )
        print(
            f"  {fixture_label}: ownership={ownership:.3f}, "
            f"flow={flow_rate:.2f} L/min, duration={duration:.4f} min, "
            f"events/day={events_per_day:.3f}"
        )

    workbook.close()

    fieldnames = [
        "fixture_label",
        "activity_link",
        "ownership_probability",
        "flow_rate_l_per_min",
        "duration_min",
        "events_per_day_reference",
        "reference_num_persons",
    ]
    with _OUTPUT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(_CSV_HEADER_COMMENT)
        handle.write(",".join(fieldnames) + "\n")
        for row in rows:
            handle.write(
                ",".join(str(row[field]) for field in fieldnames) + "\n"
            )
    print(f"Wrote {_OUTPUT_PATH}")


if __name__ == "__main__":
    main()

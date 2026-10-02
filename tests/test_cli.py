import pandas as pd

from occupancy.cli import main


def test_cli_household_default_run(tmp_path, monkeypatch) -> None:
    output = tmp_path / "household.csv"
    monkeypatch.setattr(
        "sys.argv",
        [
            "occupancy",
            "--year",
            "2025",
            "--persons",
            "2",
            "--seed",
            "1",
            "--include-electricity",
            "--output",
            str(output),
        ],
    )
    assert main() == 0
    frame = pd.read_csv(output)
    assert "total_power_kwh" in frame.columns


def test_cli_archetype_flag(tmp_path, monkeypatch) -> None:
    output = tmp_path / "retired.csv"
    monkeypatch.setattr(
        "sys.argv",
        [
            "occupancy",
            "--year",
            "2025",
            "--archetype",
            "retired_single",
            "--persons",
            "1",
            "--seed",
            "1",
            "--output",
            str(output),
        ],
    )
    assert main() == 0
    frame = pd.read_csv(output)
    assert (frame["n_present"] <= 1).all()


def test_cli_service_building_type(tmp_path, monkeypatch) -> None:
    output = tmp_path / "supermarket.csv"
    monkeypatch.setattr(
        "sys.argv",
        [
            "occupancy",
            "--building-type",
            "supermarket",
            "--year",
            "2025",
            "--seed",
            "1",
            "--include-electricity",
            "--output",
            str(output),
        ],
    )
    assert main() == 0
    frame = pd.read_csv(output)
    assert "total_power_kwh" in frame.columns

from occupancy.config import ScenarioConfig, load_scenario_config
from occupancy.households import (
    ElectricityConsumptionProfile,
    HouseholdProfile,
)


def test_default_scenario_config_round_trips() -> None:
    config = ScenarioConfig.default()

    assert config.year == 2026
    assert config.num_persons == 3
    assert config.building_type == "household"
    assert config.archetype == "generic"
    assert config.region == "NL"
    assert config.home_probabilities is None
    assert config.equipment is None


def test_load_scenario_config_with_overrides(tmp_path) -> None:
    config_path = tmp_path / "scenario.json"
    config_path.write_text(
        """
        {
          "scenario": {
            "year": 2027,
            "num_persons": 4,
            "seed": 7,
            "include_electricity": true,
            "archetype": "family_with_children",
            "region": "NL"
          },
          "occupancy": {
            "home_probabilities": [
              [1.0, 1.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0],
              [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0],
              [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0],
              [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0],
              [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0],
              [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]
            ],
            "active_probabilities": [
              [0.0, 0.0], [1.0, 1.0], [0.0, 0.0], [0.0, 0.0],
              [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0],
              [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0],
              [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0],
              [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0],
              [0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]
            ]
          },
          "electricity": {}
        }
        """,
        encoding="utf-8",
    )

    config = load_scenario_config(config_path)
    assert config.year == 2027
    assert config.num_persons == 4
    assert config.seed == 7
    assert config.include_electricity is True
    assert config.archetype == "family_with_children"
    assert config.home_probabilities[0, 0] == 1.0
    assert config.active_probabilities[1, 1] == 1.0


def test_equipment_override_from_mapping() -> None:
    config = ScenarioConfig.from_mapping(
        {
            "scenario": {"year": 2028, "num_persons": 2},
            "electricity": {
                "equipment": {
                    "tv": {
                        "weekday": [0.0] * 24,
                        "weekend": [0.0] * 24,
                        "rated_power_kw": 0.25,
                    },
                    "cooking": {
                        "weekday": [0.0] * 24,
                        "weekend": [0.0] * 24,
                        "rated_power_kw": 1.5,
                    },
                }
            },
        }
    )

    household = HouseholdProfile(
        num_persons=config.num_persons,
        year=config.year,
        seed=config.seed,
        home_probabilities=config.home_probabilities,
        active_probabilities=config.active_probabilities,
    )
    electricity = ElectricityConsumptionProfile(
        occupancy_profile=household,
        equipment=config.equipment,
    )

    assert electricity.get_equipment_table()["tv"].weekday[0] == 0.0

from __future__ import annotations

import argparse
from pathlib import Path

from occupancy.config import ScenarioConfig, load_scenario_config
from occupancy.households import (
    ElectricityConsumptionProfile,
    HouseholdProfile,
)
from occupancy.services_buildings import ServiceBuildingProfile
from occupancy.services_buildings.building_types import SERVICE_BUILDING_TYPES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="occupancy",
        description="Generate stochastic occupancy and electricity profiles "
        "for households and service buildings.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a JSON scenario config file.",
    )
    parser.add_argument(
        "--building-type",
        choices=["household", *sorted(SERVICE_BUILDING_TYPES)],
        default=None,
        help="Building type to model (default: household).",
    )
    parser.add_argument(
        "--archetype",
        default=None,
        help="Household archetype (household building type only).",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="Region key, e.g. 'NL' (default region data only, no-op today).",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Target year (e.g. 2026).",
    )
    parser.add_argument(
        "--persons",
        type=int,
        default=None,
        help="Number of occupants (household) or building capacity (service).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility.",
    )
    parser.add_argument(
        "--include-electricity",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Also generate total electricity demand profile.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output CSV path.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    config = ScenarioConfig.default()
    if args.config is not None:
        config = load_scenario_config(args.config)

    year = args.year if args.year is not None else config.year
    persons = args.persons if args.persons is not None else config.num_persons
    seed = args.seed if args.seed is not None else config.seed
    include_electricity = (
        args.include_electricity
        if args.include_electricity is not None
        else config.include_electricity
    )
    output = args.output if args.output is not None else config.output
    building_type = (
        args.building_type
        if args.building_type is not None
        else config.building_type
    )
    region = args.region if args.region is not None else config.region

    if building_type == "household":
        archetype = (
            args.archetype if args.archetype is not None else config.archetype
        )
        household = HouseholdProfile(
            num_persons=persons,
            year=year,
            archetype=archetype,
            seed=seed,
            region=region,
            home_probabilities=config.home_probabilities,
            active_probabilities=config.active_probabilities,
        )
        profile = household.get_profile()

        if include_electricity:
            electricity = ElectricityConsumptionProfile(
                occupancy_profile=household,
                seed=seed,
                equipment=config.equipment,
                has_cooking=config.has_cooking,
                has_tv=config.has_tv,
                has_laundry=config.has_laundry,
                has_cleaning=config.has_cleaning,
                has_ironing=config.has_ironing,
                has_fridge=config.has_fridge,
                has_other=config.has_other,
                has_lighting=config.has_lighting,
            )
            profile = electricity.get_profile()
    else:
        building = ServiceBuildingProfile(
            building_type=building_type,
            year=year,
            capacity=persons if args.persons is not None else None,
            seed=seed,
            region=region,
            include_equipment=include_electricity,
        )
        profile = building.get_profile()

    output.parent.mkdir(parents=True, exist_ok=True)
    profile.to_csv(output)
    print(f"Saved profile with {len(profile)} hourly rows to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

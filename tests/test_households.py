import warnings

import pytest

import occupancy
from occupancy.households import (
    EQUIPMENT_TYPES,
    HOUSEHOLD_ARCHETYPES,
    ElectricityConsumptionProfile,
    HouseholdProfile,
    get_archetype,
)
from occupancy.households.crest_tpm import MAX_CALIBRATED_SIZE
from occupancy.households.electricity import default_equipment_table


def test_generic_archetype_shape_and_columns() -> None:
    profile = HouseholdProfile(num_persons=3, year=2024, seed=1).get_profile()

    assert len(profile) in (8784, 8760)
    assert list(profile.columns) == [
        "n_present",
        "n_active",
        "n_asleep",
        "activity",
    ]
    assert (profile["n_active"] <= profile["n_present"]).all()
    assert (
        profile["n_asleep"] <= profile["n_present"] - profile["n_active"]
    ).all()


def test_all_archetypes_are_registered_and_generate() -> None:
    expected = {
        "generic",
        "working_couple",
        "family_with_children",
        "retired_single",
        "student_shared",
    }
    assert expected <= HOUSEHOLD_ARCHETYPES.keys()

    for name, spec in HOUSEHOLD_ARCHETYPES.items():
        assert spec.asleep_probabilities.shape == (24, 2)
        assert spec.heat_gain_present_kw > 0
        assert spec.heat_gain_active_kw > spec.heat_gain_present_kw

        profile = HouseholdProfile(
            num_persons=spec.num_persons_default,
            year=2025,
            archetype=name,
            seed=1,
        ).get_profile()
        assert (profile["n_active"] <= profile["n_present"]).all()
        assert (profile["n_present"] <= spec.num_persons_default).all()
        assert (
            profile["n_asleep"] <= profile["n_present"] - profile["n_active"]
        ).all()
        # every archetype's asleep_probabilities is nonzero somewhere ->
        # some hour across a full year should show a sleeping occupant.
        assert (profile["n_asleep"] > 0).any()


def test_unknown_archetype_raises() -> None:
    with pytest.raises(ValueError, match="Unknown household archetype"):
        HouseholdProfile(num_persons=2, year=2025, archetype="does_not_exist")


def test_working_couple_uses_crest_calibrated_markov_chain_generator() -> None:
    assert get_archetype("working_couple").generator == "markov_chain_crest"


def test_working_couple_generates_valid_profile() -> None:
    profile = HouseholdProfile(
        num_persons=2, year=2025, archetype="working_couple", seed=1
    ).get_profile()
    assert (profile["n_active"] <= profile["n_present"]).all()
    assert (profile["n_present"] <= 2).all()


def test_working_couple_above_calibrated_size_warns_and_falls_back() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        profile = HouseholdProfile(
            num_persons=MAX_CALIBRATED_SIZE + 2,
            year=2025,
            archetype="working_couple",
            seed=1,
        ).get_profile()
    assert any(
        "markov_chain_crest" in str(w.message)
        and "markov_chain" in str(w.message)
        for w in caught
    )
    assert (profile["n_present"] <= MAX_CALIBRATED_SIZE + 2).all()


def test_electricity_profile_has_total_power() -> None:
    household = HouseholdProfile(num_persons=2, year=2025, seed=42)
    profile = ElectricityConsumptionProfile(
        occupancy_profile=household,
        seed=42,
    ).get_profile()

    assert "total_power_kwh" in profile.columns
    assert (profile["total_power_kwh"] >= 0).all()


def test_to_result_carries_archetype_heat_gain() -> None:
    household = HouseholdProfile(
        num_persons=1, year=2025, archetype="retired_single", seed=1
    )
    bare_result = household.to_result()
    spec = get_archetype("retired_single")
    assert bare_result.heat_gain_present_kw == spec.heat_gain_present_kw
    assert bare_result.heat_gain_active_kw == spec.heat_gain_active_kw

    elec_result = ElectricityConsumptionProfile(
        occupancy_profile=household, seed=1
    ).to_result()
    assert elec_result.heat_gain_present_kw == spec.heat_gain_present_kw
    assert elec_result.heat_gain_active_kw == spec.heat_gain_active_kw
    assert "total_power_kwh" in elec_result.profile.columns
    # gain_w_per_m2 too: since to_buem_profiles() requires total_power_kwh,
    # this is the only household path into it, so dropping the field here
    # made floor_area_m2= unusable for every household regardless of what
    # the archetype defined.
    assert elec_result.gain_w_per_m2 == spec.gain_w_per_m2
    assert bare_result.gain_w_per_m2 == spec.gain_w_per_m2


def test_electricity_scales_with_household_size() -> None:
    """Regression guard for the person-count gap: before
    ``occupant_scaling`` existed, every household appliance keyed only off
    ``percent_active`` -- a fraction, invariant in household size -- so
    annual electricity moved just 1.40x across 1-5 occupants while
    published NL averages move ~2.75x. Both the per-step load and the
    annual total must now grow monotonically with ``num_persons``."""
    annual = []
    for num_persons in range(1, 6):
        household = HouseholdProfile(
            num_persons=num_persons, year=2025, seed=42
        )
        profile = ElectricityConsumptionProfile(
            occupancy_profile=household, seed=42
        ).get_profile()
        annual.append(float(profile["total_power_kwh"].sum()))

    assert annual == sorted(annual), annual
    # Well clear of the 1.40x the fraction-only model produced, and short
    # of a strictly linear 5x (real consumption is sublinear in headcount).
    ratio = annual[-1] / annual[0]
    assert 1.9 < ratio < 3.0, ratio


def test_occupant_scaling_covers_every_non_always_on_appliance() -> None:
    """Every appliance whose usage is occupancy-driven must declare an
    ``occupant_scaling`` tier, so a newly added item cannot silently
    reintroduce the household-size-blind behavior. ``flat_always_on``
    items are exempt by design -- a fridge's draw is set by the fridge."""
    equipment = default_equipment_table()
    missing = sorted(
        name
        for name, spec in equipment.items()
        if spec.strategy != "flat_always_on"
        and "occupant_scaling" not in spec.strategy_params
    )
    assert not missing, missing

    for name, spec in equipment.items():
        alpha = spec.strategy_params.get("occupant_scaling", 0.0)
        # 1.0 is the physical ceiling: usage cannot grow faster than the
        # number of people generating it.
        assert 0.0 <= alpha <= 1.0, (name, alpha)


def test_equipment_table_is_config_driven_and_complete() -> None:
    """Regression guard for the CREST-informed equipment expansion: every
    appliance -- including the ones that used to be hardcoded (fridge,
    ironing, other) -- is now a config-driven EquipmentSpec, none silently
    dropped."""
    household = HouseholdProfile(num_persons=2, year=2025, seed=1)
    equipment = ElectricityConsumptionProfile(
        occupancy_profile=household
    ).get_equipment_table()

    # One representative item per has_* category, plus the new lighting item.
    for name in (
        "fridge_freezer",  # has_fridge
        "iron",  # has_ironing
        "personal_computer",  # has_other
        "lighting",  # has_lighting
    ):
        assert name in equipment
        assert equipment[name].rated_power_kw > 0
        assert 0.0 < equipment[name].ownership_probability <= 1.0


def test_has_flags_disable_down_to_cold_appliances_only() -> None:
    household = HouseholdProfile(num_persons=2, year=2025, seed=5)
    electricity = ElectricityConsumptionProfile(
        occupancy_profile=household,
        seed=5,
        has_tv=False,
        has_cooking=False,
        has_laundry=False,
        has_cleaning=False,
        has_ironing=False,
        has_other=False,
        has_lighting=False,
    )
    profile = electricity.get_profile()

    # Only cold appliances (has_fridge, default True) remain -- each is
    # flat_always_on, so the total must be constant across every hour and
    # bounded by the sum of every cold appliance's rated power (ownership is
    # stochastic per household, so we can't assert an exact figure).
    cold_items = [
        "chest_freezer",
        "fridge_freezer",
        "refrigerator",
        "upright_freezer",
    ]
    equipment = electricity.get_equipment_table()
    max_possible = sum(equipment[name].rated_power_kw for name in cold_items)

    assert profile["total_power_kwh"].nunique() == 1
    total = profile["total_power_kwh"].iloc[0]
    assert 0.0 <= total <= max_possible + 1e-9

    # Same seed -> same ownership draw -> same result, deterministically.
    repeat = ElectricityConsumptionProfile(
        occupancy_profile=HouseholdProfile(num_persons=2, year=2025, seed=5),
        seed=5,
        has_tv=False,
        has_cooking=False,
        has_laundry=False,
        has_cleaning=False,
        has_ironing=False,
        has_other=False,
        has_lighting=False,
    ).get_profile()
    assert repeat["total_power_kwh"].iloc[0] == total


def test_family_with_children_equipment_overrides_applied() -> None:
    household = HouseholdProfile(
        num_persons=4, year=2025, archetype="family_with_children", seed=1
    )
    base = ElectricityConsumptionProfile(
        occupancy_profile=HouseholdProfile(num_persons=4, year=2025, seed=1)
    ).get_equipment_table()
    overridden = ElectricityConsumptionProfile(
        occupancy_profile=household
    ).get_equipment_table()

    assert (
        overridden["washing_machine"].weekday > base["washing_machine"].weekday
    ).all()
    assert (overridden["hob"].weekday > base["hob"].weekday).all()


def test_top_level_backward_compat_aliases() -> None:
    assert occupancy.OccupancyProfile is HouseholdProfile
    profile = occupancy.OccupancyProfile(
        num_persons=2, year=2025, seed=1
    ).get_profile()
    assert "n_present" in profile.columns


def test_equipment_types_top_level_export() -> None:
    """occupancy.EQUIPMENT_TYPES mirrors SERVICE_BUILDING_TYPES's promotion
    (buem's occupancy_module_activities.md item 1) -- a stable registry a
    downstream consumer can validate/enumerate against without reaching
    into the deep households.electricity module path."""
    assert occupancy.EQUIPMENT_TYPES is EQUIPMENT_TYPES
    assert set(EQUIPMENT_TYPES) == set(default_equipment_table())
    assert len(EQUIPMENT_TYPES) == 29
    assert EQUIPMENT_TYPES["hob"].category == "kitchen"


def test_default_seed_is_deterministic_across_constructions() -> None:
    """seed=None (the default) no longer draws from OS entropy -- two
    otherwise-identical constructions must produce byte-identical seeds and
    profiles (buem's occupancy_gains_handoff.md "Seed ownership" ask)."""
    kwargs = dict(num_persons=3, year=2025, archetype="generic", region="NL")
    first = HouseholdProfile(**kwargs)
    second = HouseholdProfile(**kwargs)

    assert first.seed is not None
    assert first.seed == second.seed
    pd_testing_equal = first.get_profile().equals(second.get_profile())
    assert pd_testing_equal


def test_default_seed_varies_with_construction_inputs() -> None:
    """Different households (by size here) must not collide onto the same
    default seed -- the portfolio-diversity property the previous
    single-shared-constant stopgap lacked."""
    seed_a = HouseholdProfile(num_persons=2, year=2025).seed
    seed_b = HouseholdProfile(num_persons=5, year=2025).seed
    assert seed_a != seed_b


def test_explicit_seed_still_overrides_the_default() -> None:
    explicit = HouseholdProfile(num_persons=3, year=2025, seed=7)
    assert explicit.seed == 7


def test_cooking_active_reflects_kitchen_equipment() -> None:
    household = HouseholdProfile(num_persons=3, year=2025, seed=1)
    profile = ElectricityConsumptionProfile(
        occupancy_profile=household, seed=1
    ).get_profile()

    assert profile["cooking_active"].dtype == bool
    # Over a full year with cooking enabled (default), some hour should show
    # kitchen equipment active.
    assert profile["cooking_active"].any()

    no_cooking_household = HouseholdProfile(num_persons=3, year=2025, seed=1)
    no_cooking_profile = ElectricityConsumptionProfile(
        occupancy_profile=no_cooking_household, seed=1, has_cooking=False
    ).get_profile()
    assert not no_cooking_profile["cooking_active"].any()

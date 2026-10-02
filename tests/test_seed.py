from occupancy.core.seed import derive_default_seed


def test_same_inputs_produce_same_seed() -> None:
    kwargs = dict(
        kind="household", size=3, year=2025, archetype="generic", region="NL"
    )
    assert derive_default_seed(**kwargs) == derive_default_seed(**kwargs)


def test_different_inputs_produce_different_seeds() -> None:
    base = dict(
        kind="household", size=3, year=2025, archetype="generic", region="NL"
    )
    baseline = derive_default_seed(**base)

    assert derive_default_seed(**{**base, "size": 4}) != baseline
    assert derive_default_seed(**{**base, "year": 2026}) != baseline
    assert (
        derive_default_seed(**{**base, "archetype": "working_couple"})
        != baseline
    )
    assert derive_default_seed(**{**base, "region": "DE"}) != baseline
    assert derive_default_seed(**{**base, "kind": "supermarket"}) != baseline


def test_seed_is_a_valid_non_negative_63_bit_int() -> None:
    seed = derive_default_seed(
        kind="household", size=1, year=1900, archetype="", region="NL"
    )
    assert isinstance(seed, int)
    assert 0 <= seed < 2**63

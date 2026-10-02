# DHW / cooking heat-demand documentation

Official technical documentation for `occupancy.generate_dhw_draws()` —
answers buem's `dhw_cooking_heat_handoff.md` ask.

- **`design.md`** — what was built, the CSV schema, every deterministic
  value it relies on in one reviewable table, and the open items/
  follow-ups still needed. Start here.

The literature review and research trail behind this feature (papers
reviewed, access status, the design questions asked and answered along
the way) live in `.claude/residential/dhw_cooking_literature_review.md`,
not here — that's a record of the research process, not user-facing
reference documentation of the shipped feature.

See also `../buem_engine_reference.md` — how buem's 5R1C thermal engine
actually consumes occupancy's output today, and precisely where (and
where not) a future DHW energy term would plug in.

## Quick orientation

- **Implementation**: `src/occupancy/households/dhw.py`,
  `src/occupancy/households/data/dhw_tapping_categories.csv`.
- **Extraction script**: `scripts/extract_dhw_tapping_categories.py`
  (regenerates the CSV from `data/inputs/CREST_Demand_Model_v2.3.3.xlsm`;
  the CSV itself stays directly user-editable afterward).
- **Tests**: `tests/test_dhw.py`.
- **Public API**: `occupancy.generate_dhw_draws`,
  `occupancy.households.dhw.load_tapping_categories`,
  `occupancy.households.dhw.register_timing_envelope`.
- **Output contract**: liters per hour, per fixture and total — never
  kWh (see `design.md` for why).
- **Randomization**: owned internally via `seed=` (an int, an
  `np.random.Generator`, or `None` for a deterministic default derived
  from the call's own inputs) — no private attribute access required.
- **Not yet done**: wiring into `to_buem_profiles()` or any household's
  default `.generate()` output (deliberately opt-in — see `design.md`);
  service-building DHW; real per-fixture washing-and-dressing timing data
  (uses a transition-weighted occupancy proxy instead — see `design.md`'s
  open items).

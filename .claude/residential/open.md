# Open issues / TODOs — households

## >>> NEXT MAJOR TASKS <<<
- [households] **8 new equipment items added 2026-09-18 need real
  ownership/power sourcing** — `laptop`, `smart_speaker`, `wifi_router`,
  `streaming_stick`, `robot_vacuum`, `air_fryer`, `coffee_machine` were
  added to `households/data/equipment.json` to cover common modern NL
  appliances CREST's 2008 UK survey predates, but their
  `ownership_probability`/`rated_power_kw`/`strategy_params` are
  estimates, not citations (flagged `_source: "estimated, unsourced"` in
  each entry). `ev_charger`'s `ownership_probability` (0.06) *is* sourced
  (CBS, 2025, "Meer dan 1 miljoen stekkerauto's in Nederland"), but its
  `rated_power_kw`/session-timing `strategy_params` are still estimates.
  Milieu Centraal's "Monitor Duurzaam Leven 2025" (used to source the
  `tumble_dryer` update in the same commit) does **not** cover most of
  these — it's a sustainability-attitudes survey, not an appliance
  census — so a different source (e.g. CBS StatLine, once a current
  successor to the discontinued `37926` table is found, or Milieu
  Centraal / GfK smart-appliance-ownership figures) is needed. The
  five CREST items downweighted in the same change
  (`answer_machine`, `cassette_cd_player`, `fax`, `vcr_dvd`,
  `cordless_telephone`) are judgment calls for the same reason — real
  NL ownership figures for these would replace the `_ownership_note`
  rationale with an actual citation.
- [households] **`ownership_probability` is household-size-independent —
  the remaining half of the person-count gap (2026-08-28)** — a real
  5-person household is likelier to own a dishwasher, a tumble dryer and
  a second TV than a 1-person one; here every household draws ownership
  from the same size-blind CREST marginal
  (`ElectricityConsumptionProfile._owned_by_name`). This is why annual
  electricity now moves ×2.20 across 1-5 occupants against roughly ×2.75
  in published NL averages, and the shortfall was deliberately **not**
  closed by inflating `occupant_scaling` past 1.0 (above 1.0 an
  appliance's usage would grow faster than the number of people using
  it — not a real effect). Closing it properly needs ownership rates
  conditioned on household size; CREST's workbook may carry them, worth
  checking before synthesizing anything. See
  `.claude/buem_household_scaling_findings.md` item 1 for the full
  measurement and `resolved.md` for the `occupant_scaling` change itself.
- [households] **No household-size-resolved electricity validation data**
  — CBS 81528NED (logged as this repo's residential validation
  reference) breaks down by *dwelling type*, not household size, so it
  cannot validate the `num_persons` axis at all. The ~×2.75 yardstick
  used above is published NL averages, an order-of-magnitude check only.
  Sourcing a real size-resolved NL/EU table would turn the item above
  from "roughly right direction" into an actual calibration.
- [households] **More archetypes / real calibration** — the 5 current
  archetypes (`generic`, `working_couple`, `family_with_children`,
  `retired_single`, `student_shared`) have illustrative, hand-authored
  probability arrays, explicitly not survey-calibrated (each JSON file
  says so in `_comment`). Real data is a follow-up.
- [households] **Consider an "occupancy-pattern" archetype axis, distinct
  from household composition** — Buttitta & Finn (2020, *Energy &
  Buildings* 206:109577, "occupancy-integrated archetypes") cluster UK TUS
  2015 diary data directly into 6 categories independent of household
  size/composition: 5 weekday patterns (OP1 Daily absence, OP2 Working
  hours absence, OP3 Lunchtime absence, OP4 Constant presence 1, OP5
  Constant presence 2) + 1 weekend pattern, via k-modes clustering, then a
  **3-state** (Active/Non-Active/Absent) first-order Markov chain with a
  transition matrix per category per 10-min step (144 steps/day) — no
  dependence on occupant count at all (a deliberate simplification vs.
  CREST, since heating demand tracks occupied/unoccupied periods more than
  headcount). This is a genuinely different, complementary axis to our
  composition-based archetypes (`working_couple`, `family_with_children`,
  ...) and could be added alongside them (e.g. an `occupancy_pattern`
  field cross-cut with `archetype`) once real data is sourced. Concept/
  methodology only — no data or code from the paper may be reused (no
  stated OA license on the paper text itself; MATLAB implementation is
  "available for download" via Mendeley Data but licensing wasn't
  confirmed, so treat as not reusable until checked).
- [households] Only `working_couple` demonstrates `markov_chain`; the
  rest use `binomial_independent`. Intentional scoping, not a bug.
- [households] **`asleep_probabilities` is hand-authored, not calibrated**
  — see `resolved.md` for the `n_asleep`/`asleep_probabilities` addition
  itself. The per-archetype curves (peak overnight, `student_shared`
  shifted later, `retired_single` with a midday-nap allowance) are
  illustrative, same caveat as `home_probabilities`/`active_probabilities`
  above. If/when the Buttitta & Finn 3-state (Active/Non-Active/Absent)
  approach is adopted, it would likely subsume `asleep_probabilities`
  entirely rather than sit alongside it — revisit together.
- [households] **Per-archetype `heat_gain_present_kw`/`heat_gain_active_kw`
  values are illustrative** (ISO 7730 / ASHRAE Fundamentals Ch. 18-informed
  ballparks, not survey-calibrated) — see `resolved.md` and
  `services/open.md`'s matching note for building types.

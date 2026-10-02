# Resolved issues & settled decisions — households

Do not re-raise. "BY-DESIGN" are deliberate choices.

## household size finally reaches internal gains (2026-08-28)

- **Every household appliance was household-size-blind → per-item
  `occupant_scaling` exponent.** `probabilistic_event`'s firing
  probability keyed only off `percent_active` (`n_active / n_present`, a
  fraction that is 1.0 whether one person of one or five of five is
  active) plus an `n_active > 0` gate; `linear_in_occupants` existed but
  no household item used it, so 100% of household rated power was
  person-count-independent and annual electricity moved ×1.40 across 1-5
  occupants. `core/equipment.py` now multiplies the probability by
  `max(gate_count, 1) ** α` (`_occupant_multiplier`), with `_gate_mask`
  returning the absolute `gate_count` alongside the intensive
  `percent_active`. α defaults to `0.0` = previous behavior bit for bit,
  so service buildings are untouched. Result: elec ×2.20, `Q_ia` ×3.03
  (was ×2.47). The α *tiers* are this repo's own assignment by how shared
  each appliance is, **not** CREST figures — CREST's headcount dependence
  lives in its 10-minute activity/TPM tables, which this repo does not
  reproduce. See `households/data/equipment.json`'s
  `_occupant_scaling_comment` and `.claude/buem_household_scaling_findings.md`.
- **BY-DESIGN: α is capped at 1.0.** An exponent above 1 means an
  appliance's usage grows faster than the number of people generating it.
  The residual gap to the ~×2.75 published yardstick is left open and
  attributed to size-independent `ownership_probability` (see
  `open.md`), not papered over by inflating exponents.
- **BY-DESIGN: household archetypes keep `gain_w_per_m2: null`.**
  Households already get real equipment and lighting gains through
  `elecLoad`, which buem adds into `Q_ia` directly; an area-normalized
  density on top would double-count the same equipment. Service buildings
  use the area path because their equipment model is coarser. The field
  is now propagated correctly by
  `ElectricityConsumptionProfile.to_result()` (it was silently dropped),
  but deliberately left unpopulated for households.

## households restructuring — fixed/settled
- `fridge`, `ironing`, `other` were hardcoded in
  `electricity_consumption.py` with no JSON representation → now
  `EquipmentSpec` rows in `households/data/equipment.json` like the other
  4 appliances, driven by the `flat_always_on`/`sessions_per_week`/
  `linear_in_occupants` strategies in `core/equipment.py`. Later expanded
  further — see below.
- **Equipment set expanded from 7 illustrative items to 29 real ones**,
  sourced from the CREST Domestic Electricity Demand Model 1.0e (Richardson,
  Thomson, Infield — Loughborough CREST), obtained directly by the user via
  the paper's own public download link (`data/inputs/*.xlsm`, gitignored,
  not committed to this repo). Checked both `.xlsm` files for an embedded
  license statement (docProps metadata + the `main` instruction sheet) —
  none found. The underlying power/cycle-length statistics on the
  `appliances` sheet are themselves credited to UK Market Transformation
  Programme Briefing Notes ("Crown Copyright", commonly OGL-licensed); the
  occupancy-dependency weighting separately derives from the UK 2000 Time
  Use Survey (UK Data Archive SN:4504), a licensed academic dataset whose
  exact reuse terms weren't independently re-verified. Given this, only
  `ownership_probability`, `rated_power_kw`, and `standby_power_kw` per
  item were taken from the sheet (attributed via each spec's
  `_crest_source` field); the hourly weekday/weekend weight shapes are
  this repo's own arrays (not CREST's 10-minute activity/TPM tables),
  calibrated so each item's expected annual energy roughly matches CREST's
  reported figure. Water heating and Electric Space Heating categories
  (DESWH, electric shower, storage heaters, ...) were deliberately
  excluded — thermal loads belonging to buem's domain, not this repo's;
  including them would double-count against buem's own heating
  calculation. `lighting` was added as one new aggregate item — CREST's
  own dedicated lighting sub-model is evidence lighting is a material
  internal-gain component, but `rated_power_kw` here is a fresh modern-
  LED-era estimate, not CREST's 2008 incandescent/CFL bulb wattages.
- `EquipmentSpec.ownership_probability` (previously unused) is now wired
  up in `ElectricityConsumptionProfile._owned_by_name()` — each household
  draws once, per seed, whether it owns each sub-1.0-probability item.
- `has_*` flags changed from a 1:1 flag→item mapping to 1:many
  (`_LEGACY_FLAG_TO_EQUIPMENT: dict[str, list[str]]`), since e.g.
  `has_fridge` now needs to cover 4 distinct cold-appliance items. Added
  `has_lighting` as a new flag alongside the existing 7.
- `internal_gains/` and `electricity/` (household-only logic) → moved to
  `households/household_profile.py` and `households/electricity.py`.
  Deep import paths removed as a breaking change (package is Alpha);
  `CHANGELOG.md` documents old→new paths.

## CREST TPM calibration round (2026-08-14) — fixed/settled
- **Real CREST transition-probability-matrix (TPM) data now backs a new
  `markov_chain_crest` generator** (`core/occupancy_engine.py`), resolving
  the former `open.md` "Source real regional TPM survey data" NEXT MAJOR
  TASK. Extracted (one-time, reproducible, `scripts/extract_crest_tpm.py`)
  from the official CREST Domestic Electricity Demand Model 1.0e workbook
  (`data/inputs/CREST_Domestic_electricity_demand_model_1.0e.xlsm`,
  gitignored, obtained directly by the user, CC BY-NC-ND — no
  redistribution of the raw workbook, only the derived numbers, same
  handling as `equipment.json`'s CREST-sourced fields). The workbook's 10
  sheets `tpm{1..5}_{wd,we}` are indexed by **household size** (1-5
  residents — confirmed directly against the workbook, not by the informal
  `tpm1-5` shorthand this doc previously used), each a 144-period
  (10-minute resolution) x 7x7 (active-occupant states 0-6) transition
  matrix; extraction trims to the reachable `(m+1, m+1)` submatrix per
  size `m` and composes the six 10-minute matrices covering each clock
  hour into one hourly matrix (`households/crest_tpm.py::
  compose_hourly_transition_matrix`, exact via the Chapman-Kolmogorov
  equation given CREST's own 10-minute-Markov assumption) — the committed
  artifact is `households/data/tpm_crest.json`, sizes 1-5 only.
- **Scope**: only the active-occupant-*count transition* dynamics are real
  CREST data. Presence-vs-active split and `n_asleep` still come from this
  repo's own (illustrative, non-CREST) `home_probabilities`/
  `active_probabilities`/`asleep_probabilities` arrays, exactly as the
  synthesized `markov_chain` generator already did — `markov_chain_crest`
  does not claim full-model CREST calibration, only this one dynamic.
- **`working_couple` migrated in place** from `markov_chain` to
  `markov_chain_crest` — a same-seed reproducibility break, deliberately
  accepted (package is Alpha; real CREST data is strictly better than the
  synthesized persistence-blend formula it replaces). Households above
  `households/crest_tpm.py::MAX_CALIBRATED_SIZE` (5 residents — CREST's own
  modeled range) fall back to the original synthesized `markov_chain` with
  a `warnings.warn`, rather than guessing/reusing the 5-resident matrix.
  `markov_chain` itself is unchanged and still registered, for any other
  caller/archetype.

## buem-alignment round (2026-07-28) — fixed/settled
- **Real "asleep" occupancy state added** — `occ_sleeping` for buem
  (`core/buem_adapter.py`) used to be a fixed 23:00-07:00 heuristic since
  the engine tracked no sleep state at all. Now `core/occupancy_engine.py`
  has a fourth per-hour signal, `asleep_probabilities` (`(24, 2)`, same
  shape as `home_probabilities`/`active_probabilities`), conditional on
  being present-but-inactive; all three generators
  (`binomial_independent`, `markov_chain`, `fixed_schedule`) draw and emit
  a real `n_asleep` column from it. All 5 household archetypes define
  illustrative curves (see `open.md` for the calibration caveat). Service
  buildings never set `asleep_probabilities`, so `n_asleep` stays `0` for
  them without special-casing `fixed_schedule` — the shared engine emits
  the same schema either way. The old fixed-window heuristic is retained
  in `to_buem_profiles()` only as a fallback for profiles/DataFrames built
  before this column existed.
- **Per-archetype `heat_gain_present_kw`/`heat_gain_active_kw`** —
  `core/buem_adapter.py`'s `Q_ig` used one global constant pair for every
  household and building type; now each archetype JSON carries its own
  pair (`ArchetypeSpec`), read by `HouseholdProfile.to_result()`/
  `ElectricityConsumptionProfile.to_result()` onto `OccupancyResult`, with
  the adapter's global constants demoted to a last-resort fallback. See
  `services/resolved.md` for the building-type side of the same change.

## BY-DESIGN
- `markov_chain`'s transition-probability data is **not** copied from
  pyCREST/richardsonpy/tsorb (GPLv3), StROBe (unlicensed), or the CREST
  Excel/data download itself (CC BY-NC-ND — noncommercial + no
  derivatives). Those were reviewed for *concept* and *schema* only. The
  default TPM is synthesized at runtime from this repo's own validated
  hourly probability arrays via a documented persistence-blend
  construction (`core/occupancy_engine.py` docstring), explicitly not
  claimed as survey-calibrated.
- Household archetypes are differentiated by **composition**
  (`working_couple`, `family_with_children`, `retired_single`,
  `student_shared`), not by clustered occupancy-pattern categories (see
  `open.md` re: Buttitta & Finn 2020) — a deliberate scoping choice for
  this round, not a rejection of that approach.

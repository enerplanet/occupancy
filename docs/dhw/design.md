# DHW tapping-event model — design and reference tables

What `households/dhw.py` implements, why, and every deterministic value it
depends on — collected in tables so each one can be checked, argued with,
and replaced independently. The literature review and research trail
behind this design (papers reviewed, questions asked and answered along
the way) live in `.claude/residential/dhw_cooking_literature_review.md`,
not here — this document is the technical reference for what was
actually built.

## What was built

`occupancy.generate_dhw_draws(profile, *, num_persons, cooking_active=None, tapping_categories=None, seed=None)`
— a standalone, opt-in function (not wired into `HouseholdProfile.generate()`,
`ElectricityConsumptionProfile.generate()`, or `to_buem_profiles()`; the
user's own directive: *"DHW was never supposed to be integrated into the
buem model... After this update in occupancy, I will add DHW in buem
after the occupancy module update"* — this repo's job is to make the
liters output available, not to wire it downstream). Returns one
`dhw_liters_<fixture_label>` column per tapping category plus a summed
`dhw_liters_total`, aligned to the caller's hourly profile index.

**Liters only, never kWh** — see `docs/buem_engine_reference.md` for why
that line is drawn where it is (nowhere in buem's 5R1C solve today; a
future DHW energy term would need a delivery-temperature assumption that
belongs on buem's side of the ownership boundary, not here).

## Single point of configuration

Every deterministic number this model uses lives in exactly one file,
`households/data/dhw_tapping_categories.csv` — fixture ownership rates,
flow rates, durations, reference event frequencies, and the reference
household size they're all calibrated to. Changing one row's numbers, or
adding an entirely new row (a new fixture, a new `activity_link`), needs
no matching Python or JSON edit; `load_tapping_categories()` picks it up
on the next call. `scripts/extract_dhw_tapping_categories.py` regenerates
this file from the source workbook (see below) — the CSV itself stays
directly user-editable afterward; re-run the script only to reset to the
source-derived defaults or to extract a different apportionment scheme.

Three design choices keep it that way:

- **`volume_per_event_l` is not a stored column.** It is derived on load
  as `flow_rate_l_per_min × duration_min`. A volume that lived in its own
  column would be a second, independently-editable number that could
  drift out of sync with the flow rate and duration it's supposed to
  represent — the earlier draft of this table had exactly that problem
  (a "self-consistency check," now retired because there is nothing left
  to be inconsistent).
- **The table is validated on every load**, not just tested once:
  `load_tapping_categories()` (and `generate_dhw_draws()`'s
  `tapping_categories=` override path, via the same shared
  `_prepare_tapping_categories()` helper) checks that all required
  columns are present, `flow_rate_l_per_min`/`duration_min` are positive,
  `ownership_probability` is in `[0, 1]`, and every row shares the same
  `reference_num_persons` — and raises a specific `ValueError` naming the
  problem if a hand-edit breaks any of these. This validation logic lives
  in the module itself (`households/dhw.py`), not duplicated in
  `tests/test_dhw.py` — the tests only assert that a deliberately-broken
  table *does* raise, they don't re-implement the check.
- **Randomization is owned internally, not passed in raw.** `seed=`
  accepts an int, an `np.random.Generator`, or `None` (a deterministic
  default derived from the call's own inputs) — see "Randomization"
  below. A caller never needs to reach into a household's private RNG
  state or construct a `Generator` itself.

## The tapping-category reference table

`households/data/dhw_tapping_categories.csv`, reproduced here for review
(`volume_per_event_l` is the derived column, shown for convenience — it
is not itself stored in the file):

| fixture_label | activity_link | ownership_probability | flow_rate (L/min) | duration (min) | volume/event (L, derived) | events/day @ 1 person |
|---|---|---|---|---|---|---|
| basin | washing_and_dressing | 0.994 | 3.54 | 0.6497 | 2.30 | 7.28 |
| kitchen_sink | cooking | 1.0 | 3.54 | 0.6497 | 2.30 | 18.72 |
| shower | washing_and_dressing | 0.997 | 9.26 | 2.7754 | 25.70 | 1.86 |
| bath | washing_and_dressing | 0.916 | 9.26 | 7.9158 | 73.30 | 0.163 |

**Source, and how this changed from the first draft.** The first pass of
this table used Jordan & Vajen's (2005) DHWcalc reference figures
(German, IEA SHC Task 26 example) for everything, with no ownership model
and a household-size scaling shortcut standing in for it. This version
replaces those numbers with real, first-party data extracted from
McKenna & Thomson's (2016) own CREST integrated thermal-electrical model
workbook — `data/inputs/CREST_Demand_Model_v2.3.3.xlsm`'s
`AppliancesAndWaterFixtures` (rows 46–53) and `WaterUsage` sheets, the
same kind of runtime workbook this repo already extracts from for the
electricity-only CREST 1.0e model (`households/crest_tpm.py`'s
precedent) — via `scripts/extract_dhw_tapping_categories.py`, a
reproducible extraction script, not a one-off manual read. That
workbook's own header cites Clarke, Grant & Thornton (2009) as *its*
source for the flow-rate/duration/ownership numbers. DHWcalc is still
cited and kept as a secondary cross-check (see the apportionment note
below) — the two sources are complementary, not competing: one UK, one
German, neither Dutch, both genuine European research baselines. See
"Keeping this generic, not Dutch-specific" below.

**Ownership is now real, not a scaling shortcut.** `ownership_probability`
is read directly off the workbook's own "Proportion of dwellings with
appliance" column — basins and kitchen sinks are near-universal;
showers (0.997) and baths (0.916) are not. `generate_dhw_draws()` draws a
Bernoulli outcome per fixture per call; a household that doesn't own a
bath draws zero from it, every time — this directly replaces the first
draft's "scale the whole table by household size" workaround with the
real mechanism the source model itself uses.

**Volume per event is now stochastic, not deterministic.** Each draw's
volume is a Poisson sample centred on the row's derived mean
(`volume_per_event_l`) rather than that exact fixed number every time —
matching the source workbook's own `WaterUsage` sheet, which carries a
Poisson probability-mass table for exactly this purpose (inspected
directly, not assumed).

**`reference_num_persons = 1` is now a fact, not a guess.** The first
draft's `REFERENCE_NUM_PERSONS = 4` was an explicitly-flagged assumption
(no source stated an occupant count for DHWcalc's 200 L/day example).
This version reads the number directly off the CREST workbook's own
`Dwellings` sheet, whose example household has `Number of residents = 1`
— the same sheet that produced the flow-rate/duration/ownership numbers
above, so the reference is internally consistent with the rest of the
table, not stitched together from two different sources' assumptions.

## The one genuinely hybrid number: `events_per_day_reference`

Everything above is a direct, first-party read. `events_per_day_reference`
is not — it is a documented apportionment, not hidden inside the numbers:

1. The CREST workbook gives a real aggregate total for its 1-person
   example — `AppliancesAndWaterFixtures`'s own "Hot water" summary cell,
   119.62586974793265 L/day.
2. That total needs splitting across the four fixtures to get a
   per-fixture daily event count, and the workbook's own per-minute
   stochastic switch-on mechanism (shared "activity probability" values
   across basin/shower/bath, further split by which specific fixture a
   washing-and-dressing event uses) is not reachable without decompiling
   its VBA macros.
3. So the split uses DHWcalc's (Jordan & Vajen 2005) own published
   relative category shares — 14% / 36% / 40% / 10% for
   basin / kitchen_sink / shower / bath — applied to the CREST total, not
   DHWcalc's own 200 L/day total. `events_per_day_reference = (share ×
   119.6) / volume_per_event_l` for each row.

This is a real, defensible engineering choice — the two source datasets'
*shapes* (which fixture gets how much of the daily total) are compatible
enough Western-European domestic-use patterns to combine, even though
their absolute totals come from different countries and years — but it
is a hybrid, not a pure single-source extraction, and is called out here
explicitly rather than left to look like a direct read.

## Plausibility cross-check, still worth keeping

McKenna & Thomson (2016) §5.2 cites the Energy Saving Trust's (2008)
measured UK average of 122.4 L/day/dwelling. UK average household size is
commonly cited around 2.3 persons (ONS): 122.4 / 2.3 ≈ 53 L/person/day.
The CREST workbook's own 1-person total, 119.6 L/day, is per-person by
construction (the example dwelling has exactly one resident) — noticeably
higher than 53 L/person/day, which is itself a real, useful finding: it
is plausible that a single-occupant household's per-capita DHW use is
higher than a multi-person household's average (fixed per-use volumes —
one bath fill is one bath fill — don't shrink per person the way they
might dilute across a larger household), not a sign either number is
wrong. Kept here as an honest data point, not resolved further.

## Timing: two registered envelopes, not a single flat average

`generate_dhw_draws()` looks up each row's `activity_link` in a small
registry (`_TIMING_ENVELOPES` / `register_timing_envelope()`, mirroring
`core/equipment.py`'s `register_strategy` pattern) to decide which hours
an owned fixture's events land in:

- **`"cooking"`** (kitchen_sink) — reuses the already-shipped
  `cooking_active` signal directly when supplied (falls back to
  `n_active` otherwise). Real, validated, no new data.
- **`"washing_and_dressing"`** (basin, shower, bath) — a
  *transition-weighted* occupancy envelope: `n_active + |Δn_active|`,
  i.e. plain active-occupancy weight plus an extra boost at the hours
  where the number of active occupants changes (waking up, going to
  bed). This reuses the concept Richardson et al. (2008) themselves
  validate their occupancy model against — counting "people becoming
  active"/"people becoming inactive" transitions (their Figs. 33–34) — as
  a timing proxy for washing-and-dressing behaviour, rather than
  assuming it is spread flat across every hour someone happens to be
  present. No new data: it's a derived transformation of the `n_active`
  column this repo already generates for every household.
- **Anything else** (a custom `activity_link` in a hand-edited or
  entirely custom table with no registered envelope) falls back to plain
  `n_active` — a documented, honest default, not a silent misrouting.
  `households.dhw.register_timing_envelope()` lets a caller register a
  real envelope for a new `activity_link` without touching this module's
  source.

This repo still has no extracted `Act_WashDress`-equivalent timing curve
from a CREST source (only `Act_Cooking` is extracted, via
`crest_tpm.py`'s precedent) — the transition-weighted envelope is a
principled proxy built from data already on hand, not a claim that it
equals a real measured washing-and-dressing activity curve. Listed below
as the one item that would still benefit from a genuinely sourced
replacement.

## Randomization: owned internally via `seed=`

`generate_dhw_draws()` never requires a caller to construct or manage a
raw `np.random.Generator` — `seed=` follows exactly the same convention
`HouseholdProfile`/`ServiceBuildingProfile` already use:

- `seed=None` (the default): a deterministic seed is derived from
  `num_persons` and the profile's own year via
  `occupancy.core.seed.derive_default_seed` (`kind="dhw"`, distinct from
  any `HouseholdProfile`'s own default seed, so calling this on a
  household's profile does not replay the same bit-stream that
  household's own generation already consumed). Same inputs always
  reproduce the same DHW draws.
- `seed=<int>`: used directly, same convention as every other explicit
  `seed=` in this repo. A caller that already has a `HouseholdProfile`
  can pass `seed=household.seed` — a fully public attribute — to tie
  a household's DHW draws to it, with no private-attribute access
  required.
- `seed=<np.random.Generator>`: used as-is, an escape hatch for tests or
  callers managing their own generator lifecycle.

This replaced an earlier design where the function took a required
positional `rng: np.random.Generator` argument — workable, but it forced
a caller (e.g. buem) to either reach into a household's private `_rng`
attribute (no documented public contract) or construct a fresh
`np.random.default_rng(household.seed)`, which restarts from the exact
same seed the household's own generation already consumed, risking
correlated (non-independent) draws. Owning the randomization internally,
the same way the rest of this package already does, removed the need for
either workaround.

## Keeping this generic, not Dutch-specific

Both sources this table draws on are UK/German research, not Dutch — this
was a deliberate choice, not an oversight: NTA 8800 (the Dutch-specific
standard this work was originally asked to cross-check) turned out to be
a paid publication with no accessible DHW default figures after two
sessions and four access attempts, while DHWcalc and the CREST/Clarke
data are both freely-verifiable Western-European baselines suitable as a
generic starting point for the Netherlands, Germany, Austria, and Czech
Republic alike — none of the mechanics here (ownership gating, Poisson
event/volume draws, transition-weighted timing) are Dutch-specific in
any way. If a specific region ever needs its own defaults (a different
bathing-frequency culture, a different fixture mix), the extension path
is the same one this repo already uses for archetypes and building types
(`CLAUDE.md`): add a sibling file, e.g. `dhw_tapping_categories_DE.csv`,
rather than editing this one in place — `generate_dhw_draws()`'s
`tapping_categories=` parameter already accepts any validated table, so
wiring in a region-specific variant needs no code change either.

## Open items — needs a decision or a document before further refinement

1. **`events_per_day_reference` is a hybrid apportionment** (CREST total
   × DHWcalc shares), not a pure single-source read — see above. The
   highest-value fix is a direct per-fixture daily-volume breakdown, if
   one exists outside the source workbook's VBA macros.
2. **basin/shower/bath timing** uses the transition-weighted `n_active`
   proxy (above), not a real washing-and-dressing activity curve. A
   genuine `Act_WashDress`-equivalent extraction (if a source ever
   becomes available) would improve this the same way `Act_Cooking`
   already improves kitchen-sink timing.
3. **Not wired to service buildings.** Both source datasets and this
   fixture set are household-specific; a service-building DHW model
   (commercial kitchens, staff washrooms, ...) needs its own literature
   base, not a naive reuse of this table.
4. **NTA 8800's Dutch-specific defaults** remain unverified against
   primary text — a lower-priority cross-check per the original ask,
   still open, and deliberately not load-bearing for this table (see
   "Keeping this generic" above).
5. **Ownership is re-resolved on every `generate_dhw_draws()` call**, not
   cached per household. Calling it twice for the "same" household with
   two different `seed=` values (or `seed=None`'s own derived default,
   which is stable per call but not tied to a specific household
   identity) can produce different ownership outcomes (e.g. a bath
   appearing in one run and not another) — a real characteristic of this
   stateless, functional design, not a bug, but worth knowing if a
   caller wants ownership held constant across multiple calls (pass the
   same explicit `seed=`).

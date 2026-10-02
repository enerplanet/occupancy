# DHW / cooking heat-demand: literature review (internal research notes)

Working notes from the research phase behind `occupancy.generate_dhw_draws()`
(`households/dhw.py`) — every paper/source consulted, its access status,
what was extracted from it, and the direct answers to the design questions
that gated the implementation. This is the research trail, kept here
rather than in `docs/` because it's exactly that: a record of what was
read, discussed, and decided during this work, not user-facing reference
documentation of the shipped feature. For the actual technical
documentation of what was built — the API, the CSV schema, every
deterministic value in reviewable tables — see `docs/dhw/design.md`,
which is the one piece of this work that belongs in `docs/`.

Companion: buem's `dhw_cooking_heat_handoff.md` (the ask this responds
to) and this repo's own `.claude/open.md` cross-repo pointer entry.

## Part 1 — Sources reviewed

Every source consulted while researching buem's `dhw_cooking_heat_handoff.md`
ask, across three research passes (2026-08-17 to 2026-08-18), with
**access status** and **exactly what was extracted and used**.

### Primary sources read in full

| # | Citation | Access | What was extracted / how it's used |
|---|---|---|---|
| 1 | Richardson, I., Thomson, M., Infield, D. (2008). "A high-resolution domestic building occupancy model for energy demand simulations." *Energy and Buildings* 40(8), 1560–1566. `doi:10.1016/j.enbuild.2008.02.006` | Read in full | The original CREST occupancy model: first-order Markov chain over UK 2000 Time-Use Survey (TUS) diary data, 144 ten-minute transition-probability matrices per household size (1–6) × weekday/weekend. This is the method `core/occupancy_engine.py`'s `markov_chain` generator and `households/crest_tpm.py`'s hourly-composed TPM extraction both implement/extend. No DHW content — occupancy-only, predates CREST's thermal/DHW extension by 8 years. Its "people becoming active/inactive" transition-counting validation concept (Figs. 33-34) is reused as the basis for `households/dhw.py`'s transition-weighted washing-and-dressing timing envelope. |
| 2 | Richardson, I., Thomson, M., Infield, D., Delahunty, A. (2009). "Domestic lighting: A high-resolution energy demand model." *Energy and Buildings* 41(7), 781–789. `doi:10.1016/j.enbuild.2009.02.010` | Read in full | Two-factor (active occupancy × natural irradiance) stochastic switch-on model per lighting unit; "effective occupancy" sharing curve (from US EIA data); Stokes et al.'s on-duration distribution. Conceptual precedent for this repo's own `lighting` equipment item. No DHW content. |
| 3 | Richardson, I., Thomson, M., Infield, D., Clifford, C. (2010). "Domestic electricity use: A high-resolution energy demand model." *Energy and Buildings* 42(10), 1878–1887. `doi:10.1016/j.enbuild.2010.05.023` | Read in full | The full 33-appliance electricity model: appliance→activity-profile mapping, TUS-code-derived daily activity probabilities, per-appliance "calibration scalars." Confirms two things: (a) the "cooking" activity profile is built from TUS codes 3100–3190 (food management/preparation/baking/**dish washing**/preserving/other) — Section 2.1; (b) Section 6.3.5 explicitly states the electric hob, oven, microwave **and dish-washer** are all assigned to the cooking activity profile for appliance-switch-on **timing** correlation purposes — a genuinely different claim from "dishwasher is a cooking/direct-heat appliance." This repo's own `equipment.json` already reflects the user's narrower definition: `dish_washer` (and `washing_machine`/`tumble_dryer`/`washer_dryer`) are filed under category `"laundry"`, separate from `hob`/`oven`/`microwave`/`kettle`/`small_cooking_group`'s `"kitchen"` category — confirmed by direct inspection, see Part 2 §5 below. Also explicitly states water heating and electric space heating are excluded from CREST's electricity model as thermal loads — the same exclusion this repo's `equipment.json` already documents. |
| 4 | Richardson, I. (2010). *Integrated High-resolution Modelling of Domestic Electricity Demand and Low Voltage Electricity Distribution Networks*. PhD thesis, Loughborough University. CC BY-NC-ND. | Read in full (contains papers #1–3 as appendices, plus the LV-network integration work) | No DHW content. Section 11.8 "Potential for further work" explicitly lists "Inclusion of a thermal model of dwellings in the demand model" as unstarted future work at time of writing — confirms DHW/thermal modelling postdates this 2010 body of work and only appears with McKenna & Thomson's 2016 extension (#5 below). Citation-completeness/provenance-chain only. |
| 5 | McKenna, E., Thomson, M. (2016). "High-resolution stochastic integrated thermal–electrical domestic demand model." *Applied Energy* 165, 445–461. `doi:10.1016/j.apenergy.2015.12.089` | Read in full | Section 3.4 describes the real hot-water module (stochastic fixture assignment, activity-linked timing, calibrated stochastic volume-per-event); Section 3.5.2 gives a constant 10 °C cold-mains assumption and cylinder sizing; Section 5.2 gives a real UK validation anchor (122.4 L/day/dwelling, EST measured data, vs. the model's own 117.5 L/day/dwelling output); Section 5.4 gives a DHW simultaneity factor of 0.13 at 30 dwellings, cross-checked against Baetens & Saelens' StROBe model (also 0.13). The exact per-fixture flow-rate/duration/volume numeric tables are not published in the paper's main text — see the workbook entry below, which supplied them instead. |
| 6 | Jordan, U., Vajen, K. (2005). "DHWcalc: Program to Generate Domestic Hot Water Profiles with Statistical Means for User Defined Conditions." *Proc. ISES Solar World Congress*, Orlando. | Read in full (free, direct PDF from University of Kassel's own repository) | The real numeric tapping-category table (small/medium/shower/bath: flow rate, duration, volume/event, events/day, portion of daily total) for a 200 L/day single-family-house IEA SHC Task 26 reference case. Superseded as the primary source for `dhw_tapping_categories.csv`'s absolute numbers once the CREST v2.3.3 workbook (below) was located — its relative category *shares* (14/36/40/10%) are still used, to apportion the workbook's real total across fixtures (see `docs/dhw/design.md`). |
| 7 | Home Energy Model (HEM), UK government's SAP successor. Technical guide: `home-energy-model.co.uk/technical/hot-water/` | Read in full (free, current) | Independent (non-CREST, non-DHWcalc) UK cross-check figures: legacy SAP flat bath volume = 73 L; generic tap draw-off default 12 L/min. Not wired into the implementation — kept as a validation reference only. |

### The CREST v2.3.3 workbook — the key find

`data/inputs/CREST_Demand_Model_v2.3.3.xlsm` — McKenna & Thomson's own
runtime workbook, distinct from the electricity-only `CREST_Domestic_
electricity_demand_model_1.0e.xlsm` this repo already bundles. Located by
scanning the user's own local reading-materials archive
(`OneDrive - Universiteit Utrecht/Old computer/Reading materials/Journal
papers/past_work/occupancy/`) before asking for documents that might
already be on hand, then copied into this repo's own `data/inputs/`
(gitignored, matching the 1.0e workbook's existing convention — CC BY-NC-ND,
no redistribution).

Its `AppliancesAndWaterFixtures` sheet (rows 46–53) gives, per fixture:
real ownership probability ("proportion of dwellings with appliance"),
mean cycle flow rate (L/min), mean cycle duration (min), and an aggregate
household hot-water total (119.62586974793265 L/day for its own example
dwelling). Its `Dwellings` sheet confirms that example has exactly 1
resident. Its `WaterUsage` sheet's own header cites, verbatim: *"Data
estimated from Clarke, A., Grant, N., Thornton, J., 2009 Quantifying the
energy and carbon effects of water saving: Final Report for the
Environment Agency and Energy Saving Trust"* — and carries a full Poisson
probability-mass table for per-event volume around each fixture's mean,
inspected directly (not assumed).

This is now the primary source for `dhw_tapping_categories.csv`, extracted
reproducibly via `scripts/extract_dhw_tapping_categories.py` (mirroring
`scripts/extract_crest_tpm.py`'s established pattern) rather than the
one-off manual `openpyxl` inspection this was first pulled from.

### Sources identified, not yet obtained

| Citation | What it would give us | Status |
|---|---|---|
| Clarke, A., Grant, N., Thornton, J. (2009). "Quantifying the energy and carbon effects of water saving: Final Report for the Environment Agency and Energy Saving Trust." Elemental Solutions, London. | The primary-source version of the per-fixture ownership/volume numbers now used via the CREST workbook's own citation of it. | Not accessed — not found in the scanned local archive; the CREST workbook's own citation of it is the closest available source. |
| Energy Saving Trust (2008). "Measurement of domestic hot water consumption in dwellings." | The primary source behind the 122.4 L/day/dwelling UK figure quoted (secondhand, via McKenna & Thomson). | Not accessed — only the summary figure inside McKenna & Thomson's own text was usable; `STP09-DHW01_Analysis_of_EST_DHW_data.pdf` (found locally, not yet opened) may be adjacent to this. |
| Pullinger, M., Browne, A., Anderson, B., Medd, W. (2013). "Patterns of water..." Lancaster University. | Originally suspected as the ownership-probability source; read in full this session — a large practice-theory survey report. Its own text does not carry a simple per-fixture ownership-percentage table in the form the CREST workbook does, so it remains a comparison/context source, not the operative one for the numbers now in the CSV. | Read in full, not the operative source. |
| McKenna, E., Thomson, M. (2015). "High-resolution integrated thermal–electrical domestic demand model (Software download)." DOI: 10.17028/rd.lboro.2001129 | Possibly a newer/different release of the workbook now in use, or documentation clarifying the per-fixture daily-volume split this session had to approximate via a DHWcalc-share apportionment. | Not accessed as a separate download — `CREST_Demand_Model_v2.3.3.xlsm`, found locally, already serves this purpose; lower priority now. |

### NTA 8800 — checked twice, still not resolved

Two pages the user supplied were checked directly (2026-08-18):

- `gebouwenergieprestatie.nl/bepalingsmethode/` — the official Dutch
  "Bepalingsmethode" portal. Confirmed legitimate, but doesn't publish
  DHW default figures — links onward to the paid standard purchase page
  (`nen.nl/nta-8800-2025-c1-2026-nl-349740`).
- `zenronline.eu/.../new-nta-8800-assessment-guidelines...` — a
  third-party news article. Also no DHW numbers; suggests contacting NEN
  directly (`bi@nen.nl`, +31 15 269 0324).

**Net result**: the 40.3 L/person/day / 545 kWh/person/year figure carried
in buem's `dhw_cooking_heat_handoff.md` remains **not independently
re-verified against primary NTA 8800 text**, across two sessions and four
distinct access attempts. The base standard is a paid NEN publication
with no free full-text mirror found. Deliberately not made load-bearing
for the shipped implementation — see Part 2 below and `docs/dhw/
design.md`'s "keeping this generic" note (neither CREST nor DHWcalc is
Dutch-specific either, which is a feature, not a gap, given the user
needs this to generalize to Germany/Austria/Czech Republic too).

## Part 2 — Questions answered

Direct answers to the design questions raised during this work, updated
as the research progressed.

### 1. Does fixture ownership matter for this scope?

Only affects the *magnitude* of DHW volume (whether a household has a
bath materially changes its total draw), never the internal-gains term —
confirmed directly against `model_buem.py`: `Q_ia = (Q_ig + elecLoad) *
(...)` has no DHW term of any kind (see `docs/buem_engine_reference.md`).

Resolved with real data: the CREST v2.3.3 workbook's own per-fixture
"proportion of dwellings with appliance" figures (basin 0.994, kitchen
sink 1.0, shower 0.997, bath 0.916) now drive a seeded Bernoulli draw per
fixture, per household (`households/dhw.py`) — a household without a
bath draws zero from it, every run. This replaced an earlier household-
size-scaling workaround that existed only because the ownership source
hadn't been located yet.

### 2. Can draw duration reuse the existing kitchen-equipment timing?

Timing transfers cleanly for the kitchen-linked category: the
`cooking_active` signal drives kitchen-sink draw *timing* directly — zero
new data, reuses the already-shipped signal. Duration/volume needed a
literature source regardless (a different physical quantity from
electrical on-time) — now the CREST workbook's own flow-rate/duration
figures.

McKenna & Thomson's own fixture-to-activity mapping (Section 3.4: *"Basins,
showers, and baths, are assigned to the 'washing and dressing' activity,
while kitchen sinks are assigned to the 'cooking' activity"*) independently
confirms the mapping this repo inferred before reading the full text.

**Gap, since addressed with a principled proxy, not left flat**: this
repo has no extracted `Act_WashDress` timing curve — CREST's electricity
-only 1.0e workbook doesn't carry it, and the v2.3.3 workbook ties its
own washing-and-dressing timing to a per-minute VBA mechanism not
reachable without decompiling macros. Rather than a flat `n_active`
average, `generate_dhw_draws()` uses a transition-weighted envelope
(`n_active + |Δn_active|`, extra weight at the hours active occupancy
changes) — reusing Richardson et al. (2008)'s own "people becoming
active/inactive" validation concept (Part 1, source #1) as a timing proxy
built from data this repo already generates. Still a proxy, not a
measured curve — the highest-value remaining open item in `docs/dhw/
design.md`.

### 3. What does "flow rate" mean, and does it drive heat demand?

Flow rate × duration = volume; volume (with a delivery-temperature
assumption, which this module deliberately does not make) is what a
future energy calculation would need. The tapping-category table is
self-consistent by construction now: `volume_per_event_l` is *derived*
from `flow_rate_l_per_min * duration_min` on load, not stored as a third,
independently-editable number that could drift out of sync — see
`households/dhw.py`'s own docstring.

Where this energy would land, confirmed directly against `model_buem.py`:
nowhere in the 5R1C solve — see `docs/buem_engine_reference.md` for the
full walkthrough. This module therefore outputs liters only, never kWh.

### 4. Review of buem's model — and the reverse

Moved to its own official document: `docs/buem_engine_reference.md`. It
documents buem's engine (the 5R1C solve, the required-keys contract,
where a future DHW term would and wouldn't plug in) from occupancy's
side — the reverse of what buem's own `.claude/occupancy_module_
activities.md` does for occupancy — confirming directly against buem's
current code (not assumed) that `q_w_nd` (TABULA's DHW parameter) is
carried through buem's data model but never actually read by
`ModelBUEM.sim_model()`.

### 5. The cooking clarification — confirmed, no change needed

The user's definition: "cooking" (direct-heat/gas-relevant activity)
excludes dishwasher and washing machine even though a dishwasher
physically sits in the kitchen.

Checked directly against `households/data/equipment.json`: `dish_washer`,
`washing_machine`, `tumble_dryer`, and `washer_dryer` are all filed under
`"category": "laundry"`. Only `hob`, `oven`, `microwave`, `kettle`, and
`small_cooking_group` carry `"category": "kitchen"`. `cooking_active`
sums exactly the `"kitchen"` category — dishwasher and washing machine
were never included, matching the definition exactly, with no code
change needed. Disambiguated from Richardson et al. (2010)'s different
"cooking activity profile" concept (Part 1, source #3), which includes
the dishwasher for a *different* purpose (usage-timing correlation, not
heat-demand categorization).

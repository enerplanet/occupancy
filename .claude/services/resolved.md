# Resolved issues & settled decisions — service buildings

Do not re-raise. "BY-DESIGN" are deliberate choices.

## BY-DESIGN
- Service-building occupancy uses `fixed_schedule` (deterministic open/
  close hours + noise) by default, not the residential-style
  `binomial_independent`/`markov_chain` strategies — those model presence
  probability per person, which doesn't fit shift/opening-hours-driven
  building occupancy.
- Households and service buildings share one engine
  (`core/occupancy_engine.py` generator registry, `core/equipment.py`
  equipment registry) rather than parallel implementations — service
  buildings are just another config-driven consumer, not special-cased.
- Most service-building types never set `asleep_probabilities` (defaults
  to all-zero), so `n_asleep` stays `0` for them — deliberate, since
  supermarket/office/restaurant/school/bakery/warehouse/clinic are never
  occupied overnight. **Update (2026-07-29):** `hotel` is the first
  exception — it genuinely needs sleeping occupants, and supplies real
  `asleep_probabilities` through the exact same mechanism households use
  (see the round below). No engine change was required to support it,
  confirming the original "no engine change required" prediction here.

## buem-alignment round (2026-07-28) — fixed/settled
- **Per-building-type `heat_gain_present_kw`/`heat_gain_active_kw`** —
  `services_buildings/building_types.py`'s `ServiceBuildingTypeSpec` gained
  both fields (default 0.100/0.150 kW, matching `core/buem_adapter.py`'s
  old global constants), read from each `schedule.json` and threaded onto
  `OccupancyResult` by `ServiceBuildingProfile.to_result()`. See
  `residential/resolved.md` for the household-archetype side of the same
  change and `open.md` for the remaining calibration caveat.

## activity/equipment profiles round (2026-07-29) — fixed/settled
- **New `hourly_occupancy_curve` generator**
  (`core/occupancy_engine.py`) — an explicit 24-hour occupancy-fraction
  table, for building types whose day-shape `fixed_schedule`'s single
  open/close window + flat peak can't represent. Added because `hotel`
  needed it: near-continuous overnight guest presence plus checkout/
  check-in peaks is not a rectangle. Shaped like DOE/ASHRAE 90.1
  prototype-building `Schedule:Compact` fractional schedules.
  `ServiceBuildingTypeSpec`/`ServiceBuildingProfile` gained
  `asleep_probabilities` plumbing (mirroring households) to support it.
- **Four new building types**: `hotel`, `bakery`, `warehouse`, `clinic` —
  occupant density/operating-hours ballparks sourced from DOE/NREL
  Commercial Reference Building Models (Deru et al. 2011), ASHRAE 90.1
  Table 9.5.1 (lighting power density by building type), and ASHRAE 62.1
  Table 6-1 (occupant density) — see each type's `schedule.json`
  `_comment` for the specific citation. These are hand-interpolated
  between published reference points, not a literal reproduction of any
  single source table — same "illustrative, not survey-calibrated"
  caveat as every other schedule/equipment JSON in this repo. Web search
  for CIBSE Guide A, TABULA/EPISCOPE non-residential, and DOE's raw
  `.idf` `Schedule:Compact` blocks (the exact hour-by-hour source data)
  did not yield usable numbers this round — flagged in `open.md` as a
  concrete follow-up if someone can pull the DOE prototype `.idf` files
  directly (e.g. from `NREL/OpenStudio-Prototype-Buildings` on GitHub)
  rather than via web search.

# Open issues / TODOs — service buildings

## >>> NEXT MAJOR TASKS <<<
- [config] **Service-building capacity from scenario config file** — CLI
  `--persons`/config `num_persons` only overrides a service building's
  capacity when passed as an explicit `--persons` CLI flag; a scenario
  JSON's `num_persons` is ignored for `building_type != household` (to
  avoid the household-oriented default of 3 silently clobbering e.g. a
  supermarket's `capacity_default: 80`). Needs a dedicated `capacity`
  config field with its own resolution rule.
- [services_buildings] **More building types** — 8 exist now (supermarket,
  office, restaurant, school, hotel, bakery, warehouse, clinic — see
  `resolved.md` for the 2026-07-29 round that added the last four).
  Adding one is a config addition
  (`data/<type>/{schedule.json,equipment.json}` + a thin registration
  module) — see `CLAUDE.md` extension points. Candidates not yet covered:
  24/7 inpatient hospital (distinct from the outpatient `clinic` here —
  DOE's Hospital prototype is a separate, always-occupied reference
  building), gym/fitness, cinema/theatre, data center, light-industrial/
  factory (distinct from `warehouse`'s bulk-storage-only profile).
- [services_buildings] **Pull DOE prototype-building `.idf` files directly
  for real hour-by-hour schedules** — `hotel`/`bakery`/`warehouse`/
  `clinic`'s `occupancy_fraction`/`peak_occupancy_fraction` curves are
  this repo's own interpolation between published ASHRAE 90.1/62.1
  density figures and DOE reference-building summary stats (floor area,
  LPD), not the DOE prototypes' actual `Schedule:Compact` hour-by-hour
  fraction tables. Those exact tables exist as open `.idf` files (e.g.
  `NREL/OpenStudio-Prototype-Buildings` on GitHub, or energycodes.gov
  downloads) but weren't retrievable via web search/fetch in the
  2026-07-29 round — someone with direct file access could pull the real
  `Schedule:Compact` blocks and replace the hand-interpolated curves.
- [services_buildings] **`warehouse`/`clinic`/`hotel` are single-zone
  approximations** — real reference buildings for these types have
  distinct sub-zone schedules DOE models separately (warehouse
  office-vs-bulk-storage, hotel guest-room-vs-lobby/corridor, hospital
  inpatient-vs-outpatient), but this repo's occupancy model is one
  occupant count per building, not per zone. `clinic`'s
  `weekend_open_hour`/`weekend_close_hour` window (8-13) also only
  approximates "open shorter hours on Saturday, closed Sunday" —
  `fixed_schedule` can't distinguish Saturday from Sunday (both are
  `weekday() >= 5`), so Sunday closure is slightly understated. Documented
  in each type's `schedule.json` `_comment`; a real fix needs either
  per-building-day (not just per-weekend) schedule params, or a
  multi-zone occupancy model — bigger changes, not done here.
- [alignment] **Per-building-type `heat_gain_present_kw`/`heat_gain_active_kw`
  values are illustrative** — implemented (see `resolved.md`): each
  `schedule.json` now carries its own pair instead of sharing one global
  constant (office 0.100/0.130 kW, supermarket 0.100/0.180 kW, restaurant
  0.100/0.170 kW, school 0.085/0.120 kW). The *values themselves* are
  ISO 7730 / ASHRAE Fundamentals Ch. 18-informed ballparks by activity
  intensity, not survey-calibrated for these specific building types —
  real-data calibration is a follow-up, same caveat as the schedule/
  equipment JSON already carries.

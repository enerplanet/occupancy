# Findings for `buem` — household internal gains vs. occupant count (2026-08-28)

**Status: fixed occupancy-side, not yet raised with the buem repo/agent.**
The mirror image of buem's own
`.claude/occupancy_service_scaling_request.md` (drafted 2026-08-26, also
still unraised) — same root cause, opposite direction. Nothing here
requires a buem code change; items 1 and 2 change numbers buem already
consumes, and item 4 is a question only buem can answer.

---

## Item 1 (informational, changes buem's numbers) — household electricity now scales with `num_persons`

**What was wrong.** `num_persons` reached buem's thermal model through
exactly two terms, and only one of them responded to it.

Since buem's fix to `Q_ia` (see item 3), `model_buem.py` forms internal
air gains as `Q_ia = Q_ig + elecLoad`, with no presence rescaling. So
`occ_nothome`/`occ_sleeping` — being dimensionless fractions of occupants
— carry no headcount information by construction, and everything depends
on `Q_ig` and `elecLoad` carrying it themselves. `Q_ig` did.
`elecLoad` did not:

| N | `Q_ig` [kW] | `elecLoad` [kW] | `Q_ia` [kW] | elec kWh/yr |
|--:|------------:|----------------:|------------:|------------:|
| 1 | 0.0780 | 0.1798 | 0.2578 | 1,575 |
| 2 | 0.1540 | 0.2186 | 0.3726 | 1,915 |
| 3 | 0.2332 | 0.2369 | 0.4701 | 2,075 |
| 4 | 0.3114 | 0.2419 | 0.5533 | 2,119 |
| 5 | 0.3865 | 0.2510 | 0.6375 | 2,199 |

`Q_ig` ×4.95 across N=1→5, `elecLoad` **×1.40**. And `elecLoad` is the
dominant term — 70% of `Q_ia` at N=1 — so the combined figure buem's
5R1C actually solves against moved only ×2.47.

**Root cause.** Every one of the 29 household appliances in
`households/data/equipment.json` was household-size-blind. Their firing
probability keyed off `percent_active = n_active / n_present`, a
*fraction* that is 1.0 whether one person of one is active or five of
five, plus an `n_active > 0` gate. The `linear_in_occupants` strategy
existed in `core/equipment.py` but no household item used it: **100% of
household rated power was person-count-independent.** The residual ×1.40
came only from more occupants making `n_active > 0` true in more hours.

Note this is the same defect buem measured from the other side for
service buildings — 40× capacity moving annual electricity ×1.46
(`occupancy_service_scaling_request.md` item 1). Households: 6× persons
moving it ×1.45. One shared engine, one shared bug.

**What changed.** New per-item `occupant_scaling` exponent α in
`strategy_params`, multiplying the firing probability by
`max(gate_count, 1) ** α` (`core.equipment._occupant_multiplier`). Items
are assigned to four sharing tiers by whether an extra occupant brings
their own use of the appliance:

| α | tier | items |
|---:|---|---|
| 1.0 | per-person consumables | washing machine, washer-dryer, tumble dryer, dishwasher, kettle, PC, iron |
| 0.5 | partly-shared activities | hob, oven, microwave, small cooking, vacuum, TV 2, TV 3 |
| 0.3 | mostly shared | lighting, printer |
| 0.15 | one-per-household | TV 1, receiver box, VCR/DVD, hi-fi, cassette/CD, fax |
| — | exempt | the 7 `flat_always_on` cold appliances and standby electronics |

α defaults to `0.0`, which reproduces the previous behavior bit for bit,
so the *code* change is backward compatible — the *data* change is what
moves the numbers.

**New figures buem will see** (generic archetype, seed 42, 2023):

| N | `Q_ig` [kW] | `elecLoad` [kW] | `Q_ia` [kW] | elec kWh/yr | was |
|--:|------------:|----------------:|------------:|------------:|----:|
| 1 | 0.0780 | 0.1798 | 0.2578 | 1,575 | 1,575 |
| 2 | 0.1540 | 0.2533 | 0.4073 | 2,219 | 1,915 |
| 3 | 0.2332 | 0.3032 | 0.5365 | 2,656 | 2,075 |
| 4 | 0.3114 | 0.3489 | 0.6602 | 3,056 | 2,119 |
| 5 | 0.3865 | 0.3955 | 0.7820 | 3,464 | 2,199 |

`elecLoad` ×1.40 → **×2.20**; `Q_ia` ×2.47 → **×3.03**. N=1 is
unchanged (α only bites above one occupant), so single-occupant
buildings keep their existing results exactly.

**Direction of the effect on buem's own validation.** Every
multi-occupant residential building now receives more internal gain than
before, so modelled heating demand goes **down**. buem's known
2-7× buem-vs-CBS heating overshoot (`.claude/open.md` issue #3) should
narrow slightly, and — by the same insulation-dependence buem already
confirmed for the `Q_ia` presence-double-scaling fix — the effect should
be **larger for well-insulated archetypes than poorly-insulated ones**.
Worth re-running `validation.py` against this. This is a prediction from
the mechanism, not something measured here; occupancy has no thermal
model to check it with.

**Residual, deliberately not closed.** ×2.20 is still short of the ~×2.75
that published NL averages by household size suggest. That gap was *not*
closed by pushing exponents higher: α > 1.0 would mean an appliance's
usage grows faster than the number of people using it, which is not a
thing. The remaining shortfall is attributed to `ownership_probability`
being household-size-independent in this repo — a real five-person
household is likelier to own a dishwasher, a tumble dryer and a second TV
— which is a separate lever, tracked in `.claude/residential/open.md`.
Flagging it here so buem doesn't read ×2.20 as a calibrated endpoint.

**Caveat on the yardstick.** The ~×2.75 reference is published NL
averages by household size, used as an order-of-magnitude check only.
CBS 81528NED — the dataset already logged as occupancy's residential
validation reference — is broken down by *dwelling type*, not household
size, so it cannot validate this axis. A size-resolved NL table is still
unsourced. If buem has one, that would close a real gap here.

---

## Item 2 (bugfix, may change buem's numbers) — `gain_w_per_m2` was dropped on the household path

`ElectricityConsumptionProfile.to_result()` did not copy
`gain_w_per_m2` from the archetype spec, though
`HouseholdProfile.to_result()` did. Because `to_buem_profiles()` requires
a `total_power_kwh` column, the electricity path is the *only* household
route into it — so passing `floor_area_m2=` for a household raised
`"floor_area_m2 was given but no gain_w_per_m2 is available"` no matter
what the archetype defined. Fixed; both `to_result()` methods now carry
the same spec-derived gain fields.

**Currently latent**: all five household archetypes have
`gain_w_per_m2: null`, so this changed no output yet. That is deliberate,
and buem should know why: households already get their real equipment and
lighting gains through `elecLoad`, which buem adds to `Q_ia` directly.
Populating an area-normalized density for households on top of that would
**double-count** the same equipment. Service buildings use the area path
because their equipment model is coarser. So: keep passing `A_ref` for
service buildings; do **not** start passing `floor_area_m2` for
residential buildings expecting it to add gains — it would be additive on
top of a term that already covers it.

---

## Item 3 (closed, no action) — the `Q_ia` presence-double-scaling fix is now reflected upstream

occupancy's `core/buem_adapter.py` module docstring still documented the
superseded
`Q_ia = (Q_ig + elecLoad) * (occ * (1 - occ_sleeping) + 0.5 * occ_sleeping)`
formula. buem removed that rescaling (`model_buem.py`:
`Q_ia = Q_ig + elecLoad`); the docstring now matches, and spells out the
consequence that made item 1 matter — with no presence reweighting
downstream, `Q_ig` and `elecLoad` are the *only* carriers of headcount.

---

## Item 4 (question for buem) — is `num_persons` scaled by `residential_units`?

`buem/.claude/open.md` carries both a finding that
"`AttributeBuilder`'s live `num_persons` resolution is not scaled by
`residential_units`" and, later, that "the AB internal-gains bug is
fixed — new `residential_units` AttributeSpec scales one dwelling's
`Q_ig`/`elecLoad`/`dhw_liters` up to the whole block."

Those describe two different fixes. Scaling one dwelling's output by
`units` is right *if* `num_persons` is the per-dwelling occupancy. It is
wrong if `num_persons` was ever set to the whole block's population,
which would then be multiplied a second time. occupancy cannot see which
holds. Worth confirming buem-side, and it matters more now than it did
before item 1: `elecLoad`'s dependence on `num_persons` used to be so
weak that a mis-scaled headcount barely showed up. It now moves the
answer.

---

## Also unblocked, not done — service-building equipment scaling

`occupant_scaling` lives in `core/equipment.py`, which service buildings
share with households. buem's `occupancy_service_scaling_request.md`
item 1 is therefore now a **data** change per building type
(`services_buildings/data/<type>/equipment.json`) rather than an engine
change. Not applied here — this round was scoped to households — but the
mechanism buem asked for exists. Items 2-4 of that document
(*recreatiewoning*, sports hall, agricultural/unheated storage profiles)
are unaffected and still open.

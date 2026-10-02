# buem's thermal engine, as seen from occupancy's side

buem's own `.claude/occupancy_module_activities.md` and
`occupancy_gains_handoff.md` document *occupancy's* activities for
whoever works on buem. This is the reverse: what buem's engine actually
does with occupancy's output, written from occupancy's side, so anyone
extending occupancy's output (DHW, cooking, or anything future) can check
what the downstream consumer does with it without re-deriving it from
buem's source each time. **buem is the main engine that determines the
role of the other models, including this one** — per the user's own
framing — so this doc exists to keep that relationship legible in both
directions, not just buem→occupancy.

This is a living document tied to a specific point-in-time read of
buem's code (2026-08-17/18, `model_buem.py`, `gas_conversion.py`,
`geojson_validator.py`, `building.py`, and the v3/v4 request schemas) —
re-verify against buem's actual code before relying on a specific line
number, the same caveat buem's own hand-off docs already carry about
occupancy's code.

## What buem requires from occupancy today

`ModelBUEM` raises `ValueError` at setup if any of four keys are missing
from its config dict (`model_buem.py:844-849`):

| Key | What it is | occupancy's source |
|---|---|---|
| `Q_ig` | Internal gains profile [kW] | `to_buem_profiles()` |
| `elecLoad` | Electricity load profile [kW] | `to_buem_profiles()` |
| `occ_nothome` | Fraction of occupants away, per hour | `to_buem_profiles()` |
| `occ_sleeping` | Fraction of occupants asleep, per hour | `to_buem_profiles()` |

A 5th, **optional** key — `cooking_active` — is now also produced by
`to_buem_profiles()` when the source `OccupancyResult` carries a
`cooking_active` column (see `CHANGELOG.md` `[Unreleased]`). buem does not
read it yet; it exists so a future buem-side gas-cooking term has
something real to key off, without occupancy needing another release.

## How buem actually uses these four (`model_buem.py:1073-1099`)

```python
occ = 1 - occ_nothome[t]                     # fraction present
sleeping = occ_sleeping[t]
Q_ia = (Q_ig[t] + elecLoad[t]) * (occ * (1 - sleeping) + 0.5 * sleeping)

# ISO 13790 §C.2 gain distribution (Schütz et al. 2017 Eqs. 20-22)
phi_int = Q_ia
phi_sol = Q_sol_win + Q_sol_opaque           # solar gains, buem's own
phi_ia = 0.5 * phi_int                       # -> air node
phi_st = f_st * (0.5 * phi_int + phi_sol)    # -> surface node
phi_m  = f_Am * (0.5 * phi_int + phi_sol)    # -> mass node
```

`Q_ig + elecLoad` (occupancy's internal-gains and electricity-load output,
summed) is scaled by a presence/sleeping factor — full weight when present
and awake, half weight when asleep (occupants generate less activity heat
asleep, per the same convention this model already used for `Q_ig` itself),
zero when away — then split three ways into the ISO 13790 5R1C network's
air/surface/mass nodes. **This is the entire internal-gains pathway.**
There is no DHW term anywhere in it, at any point.

## `q_w_nd` — TABULA's DHW parameter, confirmed dead code

buem's own `Building`/`ThermalProperties` model carries a `q_w_nd` field
(`building.py:113`, "Net energy need for domestic hot water per unit
floor area per year... TABULA: q_w_nd"), and it round-trips through the
v3/v4 request schemas and `geojson_validator.py:804` (a pure pass-through
— extracted from the request into `building_attributes`, nothing else).
It is echoed into building JSON output (`building.py:222-223`,
`thermal_node["q_w_nd"]`).

**It is never read by `model_buem.py`** — grepped directly this session,
zero occurrences in `buem/thermal/`. buem's own `gas_conversion.py`
confirms this in its own words (line 26-29, quoted verbatim because it's
the most authoritative source available — buem's own code comment):

> *"`q_w_nd`, TABULA's own hot-water-demand parameter, is carried in
> `ThermalProperties` but never actually read by `model_buem.sim_model()`
> — no DHW simulation exists to compare against"*

The v4 schema's description text for `q_w_nd` — *"Added to the heating
energy need in the final energy balance"* — describes **intended future
behaviour**, not code that currently exists. Treat it as a design note
buem hasn't implemented yet, not a description of current output.

## `gas_conversion.py`'s CBS split — validation-side only, doesn't touch buem's real output

buem's `analysis/netherlands/gas_conversion.py` applies a documented
78% heating / 20% hot water / 2% cooking split to CBS's *national gas
statistics* (`cbs_reference`, total household gas, m³/year) so that
figure can be stripped down to a space-heating-only number comparable
against `ModelBUEM`'s simulated output. This is a one-way adjustment to
an external validation dataset — it never feeds anything back into
`ModelBUEM.sim_model()` itself, and it is not a DHW *model* of any kind
(no per-building variation, no thermal dynamics — a single blended
national ratio, and the module's own docstring already flags it as "the
least-verified of the three factors" for exactly that reason).

## Where a future DHW energy term would (and wouldn't) plug in

Per the user's explicit direction: DHW was never meant to be part of
buem yet, is not currently wired into it in any form, and will be added
to buem *after* this occupancy-side update lands — so this section is
forward-looking, not a description of anything implemented.

**Would NOT plug into**: `Q_ia` / `phi_int` / the ISO 13790 gain
distribution above. DHW leaves the building via the drain — it is not an
internal heat gain the way occupant metabolism or appliance waste heat
is, and none of the standards reviewed for this work (ISO 13790,
EN ISO 52016-1, EN 15316-3, NTA 8800) model it that way either. Folding
a DHW term into `Q_ig`/`elecLoad` upstream, or into `Q_ia` downstream,
would be a modelling error, not a simplification.

**Would plug in as**: a separate, additive `dhw_kWh` term, computed
independently of the 5R1C solve and added to space-heating energy need
afterward — matching both TABULA's own `q_w_nd` convention (see above)
and how every standard reviewed treats DHW. occupancy's
`generate_dhw_draws()` (`docs/dhw/design.md`) supplies the volume side of
that (liters per hour, per fixture); the energy conversion
(`V × ρ × c × ΔT`) needs a delivery-temperature assumption that belongs
on buem's side of the ownership boundary (CLAUDE.md: occupancy owns
occupant/equipment behavior — volumes and timing; buem owns
temperature/ΔT/energy math) once buem's own DHW work begins.

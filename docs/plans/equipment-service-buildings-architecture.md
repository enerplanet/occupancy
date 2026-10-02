# Superseded

This document's proposal (a flat `equipment/`/`activities/` layer) was
superseded during implementation once the household-diversity and
service-building requirements were made concrete with the user, plus a
review of six reference occupancy models (pyCREST, richardsonpy, tsorb,
StROBe, simpy, mesa).

What was actually built — `core/`, `households/`, `services_buildings/`,
the generator/equipment strategy registries, the Markov-chain generator,
and the household archetypes — is implemented in the codebase. See:

- `CLAUDE.md` — architecture overview, extension points, dev commands.
- `.claude/open.md` — active follow-ups (real regional survey data,
  service-building capacity config, more archetypes/building types).
- `.claude/resolved.md` — what was fixed/settled during the restructuring,
  including why simpy/mesa were not adopted and why no upstream repo's
  data files were copied (GPL/unlicensed provenance).
- `CHANGELOG.md` `[Unreleased]` — the full list of breaking changes and
  additions.

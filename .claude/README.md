# .claude/ — known issues & decisions log

Git-tracked log so recurring items don't need re-explaining each session.
Pattern ported from `UU-BUEM/weather`, split by domain to mirror
`src/occupancy/households/` and `src/occupancy/services_buildings/`.

## For Claude Code
- **Check the relevant `open.md` before starting** work on a module —
  top-level for `core/`/`config/`/CI/packaging, `residential/` for
  households, `services/` for service buildings. Respect RESOLVED/
  BY-DESIGN entries so you don't re-raise settled points.
- When you hit or fix something, UPDATE the matching file in the same
  change. Cross-cutting items (touch both domains, or `core/`/`config/`)
  go top-level; domain-specific items go in the matching subfolder.
- One-liners; newest at top. Keep markdownlint-clean.

## Files
- `open.md` / `resolved.md` — cross-cutting (shared `core/` engine,
  `config/`, CLI, CI, packaging, buem relationship).
- `residential/open.md` / `residential/resolved.md` — household-archetype-
  specific (occupancy generators, equipment, archetype data).
- `services/open.md` / `services/resolved.md` — service-building-specific
  (building types, schedules, equipment).

## See also
- `/CLAUDE.md` — architecture, layout, conventions, dev commands.
- `/docs/plans/equipment-service-buildings-architecture.md` — pointer to
  the restructuring's design rationale.

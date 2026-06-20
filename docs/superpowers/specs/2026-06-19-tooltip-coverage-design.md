# Effect-tooltip coverage patch — design

**Date:** 2026-06-19
**Status:** Approved design (pre-implementation)
**Branch:** `feature/tooltip-coverage`
**Follows:** `2026-06-19-in-site-effect-tooltips-design.md` (the shipped feature this improves)

## Problem

The in-site effect tooltips are live, but only **262/385 (68%)** of the distinct
entities rendered in the build detail panel resolve to a card; the rest fall back to
the "look it up ↗" link. A coverage audit (replicating the front-end `normKey` +
`effectFor` + `KIND_TO_TYPE` against the live `effects.json` + `meta-detail.json`)
pinpoints the gaps:

| Category | Resolves | Cause of misses |
|---|---|---|
| Support gems | 38/38 (100%) | — |
| Runes / soul cores | 33/33 (100%) | — |
| Skill gems | 69/74 (93%) | 5 misses are ascendancy-*granted* skills (not equippable gems) |
| Notables | 103/124 (83%) | misses are **keystones** (`isKeystone`, excluded) + a few popular "other"-flagged nodes |
| Unique items | 19/35 (54%) | popular uniques no sampled character equipped (sample-only source) |
| Anointments | **0/54 (0%)** | `"Anointment"` kind has no `KIND_TO_TYPE` mapping |
| Weapon base | **0/27 (0%)** | no mapping; but these are base-type names (self-explanatory) |

## Goals

- Raise coverage to ~90%+ by closing the **notable (keystone)**, **anointment**, and
  **unique** gaps.
- Stay **honest, additive, low-upkeep**: every change degrades to the existing link;
  no fabrication; data derived at build time, version-pinned, attributed.
- Keep the served `effects.json` lean (don't bloat it with unreferenced tree nodes).

## Non-goals

- **Weapon-base tooltips** — "Crossbow", "Quarterstaff" etc. are self-explanatory base
  types; keep the link. Out of scope.
- The **5 ascendancy-granted skill misses** — would need a granted-skill source; low
  count, out of scope for this patch.
- **100% unique coverage** — see Limitations; the newest league uniques that neither
  PoB2 nor the sample has stay on the link until PoB2's data catches up.

## Findings that shape the design (from spikes)

- **Keystones:** the GGG tree export has **33 keystones** with full `stats[]` (e.g.
  Zealot's Oath). They were excluded because `notablesFromTree` kept only `isNotable`.
- **Anointments ARE notables:** in PoE2 an anointment grants a notable passive's effect,
  and poe.ninja's `anointed` dimension uses the notable name. **11/12** tested anointment
  names are already in the current `effects.json.notables` bucket; the rest are
  tree-"other" nodes.
- **Tree size:** 4,494 named-with-stats nodes (1,187 notable + 33 keystone + 3,274
  "other"). Dumping all "other" nodes would ~4× the notables section of the served file,
  so include "other" nodes only when referenced by the meta.
- **PoB2 uniques:** `PathOfBuilding-PoE2/src/Data/Uniques/<slot>.lua` (per-slot) holds
  ~435 unique blocks. It has **7/11** of the sampled gap-uniques but **lacks the 4
  newest 0.5.0 ones** (Heart of the Well, From Nothing, Prism of Belief, Against the
  Darkness). PoB2 block format: `[[\nName\nBaseType\n<metadata lines>\n<mod lines>\n]]`,
  mods prefixed with `{tags:…}`/`{variant:N}`/`{range:N}` markup.

## Design

### 1. Notables — keystones + referenced "other" nodes (`tools/effects.cjs`)

`notablesFromTree(tree, wanted)` gains a second arg `wanted` (a `Set` of `normKey`'d
names the meta actually references). A node is included when it has a `name` and
non-empty `stats[]` **and** (`isNotable || isKeystone || wanted.has(normKey(name))`).

- Captures all 33 keystones (fixes Chaos Inoculation, Blood Magic, Ancestral Bond, …).
- Captures popular "other" nodes the meta references (Point Blank, Path of the Sorceress,
  Choice of Power) **without** the 3,274-node bloat.
- `wanted` is built in the pipeline from every `md.notables[].name` and
  `md.anointments[].name` across `meta-detail`'s `byAsc` + `global`.

### 2. Anointments — map the kind (`index.html`)

- Add `"Anointment": "notables"` to `KIND_TO_TYPE`. An anointment then resolves against
  the (now keystone+referenced-augmented) notables bucket.
- `entityCard` learns the *display kind*: `metaCol` passes the original `kind` so an
  anointment card shows an **"Anointment"** badge and a one-line "grants this passive"
  note above the notable's stats, rather than a bare "Notable" badge. Signature becomes
  `entityCard(type, entry, displayKind)`; existing callers pass the kind they already
  have. Unmatched anointments keep the link.

### 3. Uniques — hybrid PoB2 + sample (`tools/effects.cjs` + pipeline)

- New pure fn `uniquesFromPob(luaText)` parses one PoB2 `Uniques/<slot>.lua`: split on
  `[[ … ]]` blocks → `name` (line 1), `base` (line 2), skip metadata directives
  (`Variant:`/`Implicits:`/`Source:`/`League:`/`Requires`/etc.), take the **Current**
  variant's mod lines, strip `{…}` markup → `mods[]`. Returns `{ [normKey]: {name, base,
  mods} }`.
- The pipeline fetches the pinned set of `Uniques/*.lua` files (same `cached()` +
  version-pin pattern as `Gems.lua`/the tree export) and merges:
  **`effects.json.uniques` = sample-derived (from `collectFromChar`) ∪ PoB2-derived**,
  with **PoB2 mods preferred** (canonical ranges) and **sample `flavour` kept** when
  present (PoB2 blocks have no flavour text). PoB2 fills gaps the sample missed; the
  sample keeps the newest uniques PoB2 lacks.
- **Filter non-uniques:** drop entries whose name matches `^(Normal|Magic|Rare) ` (e.g.
  "Normal Body Armour" — a placeholder, not a unique).

### 4. Coverage audit tool (`tools/coverage-audit.cjs`)

Commit the audit script (used to produce the numbers above) as a re-runnable tool so
coverage is measurable before/after and over time. Reads `effects.json` +
`meta-detail.json`, prints per-category resolve rates + top misses. No deps.

## Data sources (updated attribution)

- poe.ninja public ladder data (runes/uniques/gems/flavour) — existing.
- GGG `poe2-skilltree-export` 0.5.2 (notables **+ keystones**) — existing, broadened use.
- PoB2 `PathOfBuilding-PoE2` `Gems.lua` (gem tags) — existing; **+ `Data/Uniques/*.lua`
  (unique mods), MIT, pinned** — NEW. Update the on-site + README credit to name the
  unique source.

## Error handling / fail-safe

- Every change is additive: a missing/unparseable PoB2 file, an unmatched name, or a
  malformed entry → the existing link. The unique-merge and PoB2 fetch are wrapped so a
  failure can never abort the `builds/`+`meta-detail.json`+`effects.json` commit (the
  enumerate effects block is already in a `try/catch`).
- `--effects-only` keeps its empty-output guard; it also reads `meta-detail.json` from
  the repo to build `wanted` and fetches/caches the PoB2 unique files.

## Testing

Extend `tools/test-effects.cjs` (`node --test`):
- `notablesFromTree` includes a keystone, includes a `wanted` "other" node, and excludes
  an unreferenced "other" node.
- `uniquesFromPob` parses a representative multi-variant block (name/base/mods, markup
  stripped, current-variant selection, metadata lines skipped).
- unique merge prefers PoB2 mods, keeps sample flavour, fills sample-only gaps, and drops
  `^(Normal|Magic|Rare) ` names.
- Front-end (`index.html`) has no JS test harness — verified in the local preview
  (anointment card shows the granted notable + "Anointment" badge; a keystone and a
  previously-missing unique now render). Before/after coverage measured with
  `tools/coverage-audit.cjs`.

## CI

- `builds.yml` + `test.yml` already run the effects unit tests and commit `effects.json`;
  no workflow change needed beyond the version-pinned PoB2 unique fetch happening inside
  the enumerate pass. Pin bumps are deliberate PRs (same posture as the tree-export pin).

## Limitations (honest)

- Uniques won't reach 100%: the newest 0.5.0 uniques absent from both PoB2 and the
  sample stay on the link. They resolve automatically once PoB2's community data adds
  them (weekly rebuild) or a sampled character equips them.
- A handful of notables/anointments genuinely absent from the tree export (Path Seeker,
  Lucid Dreaming, …) keep the link.

## Expected outcome

~68% → **~90%+** coverage: notables ~83%→~98%, anointments 0%→~90%, uniques 54%→~80%,
with PoB2 touching only uniques and everything else derived from data already pulled.

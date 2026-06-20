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
- **Literal 100% unique coverage** — a unique worn by no sampled character stays on the
  link (see Limitations); in practice this only affects uniques outside the meta's
  top-uniques list.

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
- **Uniques root cause = unread arrays:** the unique misses are almost all **jewels and
  flasks**. `collectFromChar` only reads `char.items`, but poe.ninja characters carry
  unique jewels in `char.jewels` and unique flasks/charms in `char.flasks` (same item
  shape: `frameType:3`, `name`, `baseType`, `explicitMods`, `flavourText`). The gap
  uniques are already in the sample we pull — Heart of the Well in **182/262** cached
  characters, Nascent Hope 127, From Nothing 119, Prism of Belief 66. They were simply
  never harvested. (Checked alternatives: repoe-fork `uniques.json` is metadata-only — no
  mods; poe2db has mods but only via fragile HTML scraping — both unnecessary since the
  data is already ours.)

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

### 3. Uniques — harvest jewels + flasks (`tools/effects.cjs`)

The whole fix is reading the arrays we skipped. `collectFromChar` iterates a combined
list `[...(char.items||[]), ...(char.jewels||[]), ...(char.flasks||[])]` for the unique
(and rune) harvest instead of `char.items` alone. Jewels/flasks carry no socketed runes,
so the rune harvest is unaffected; the unique harvest now captures unique jewels and
flasks/charms with their real mods + flavour, straight from the live ladder.

- **No new dependency, no scraping, no PoB2 Data.** The newest 0.5.0 uniques PoB2 lacks
  (Heart of the Well, From Nothing, …) are filled "by other means" = the players wearing
  them in the sample we already pull; they resolve automatically and stay current.
- **Filter non-uniques:** in the unique capture, skip names matching
  `^(Normal|Magic|Rare) ` (e.g. "Normal Body Armour" — a placeholder that leaked into the
  meta's top-uniques list).
- This modifies the shipped `collectFromChar`; its existing tests stay green and a new
  test covers jewel/flask harvest + the junk-name filter.

### 4. Coverage audit tool (`tools/coverage-audit.cjs`)

Commit the audit script (used to produce the numbers above) as a re-runnable tool so
coverage is measurable before/after and over time. Reads `effects.json` +
`meta-detail.json`, prints per-category resolve rates + top misses. No deps.

## Data sources (updated attribution)

- poe.ninja public ladder data (runes/uniques/gems/flavour) — existing.
- GGG `poe2-skilltree-export` 0.5.2 (notables **+ keystones**) — existing, broadened use.
- PoB2 `PathOfBuilding-PoE2` `Gems.lua` (gem tags) — existing, unchanged.

**No new data source is introduced.** Uniques now come from the `char.jewels` /
`char.flasks` arrays of the poe.ninja sample we already pull; on-site + README
attribution is unchanged.

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
- `collectFromChar` harvests unique jewels (from `char.jewels`) and flasks (from
  `char.flasks`), not just `char.items`; drops `^(Normal|Magic|Rare) ` names; the rune
  harvest is unaffected (jewels/flasks have no socketed runes).
- Front-end (`index.html`) has no JS test harness — verified in the local preview
  (anointment card shows the granted notable + "Anointment" badge; a keystone and a
  previously-missing unique now render). Before/after coverage measured with
  `tools/coverage-audit.cjs`.

## CI

- `builds.yml` + `test.yml` already run the effects unit tests and commit `effects.json`;
  no workflow change needed beyond the version-pinned PoB2 unique fetch happening inside
  the enumerate pass. Pin bumps are deliberate PRs (same posture as the tree-export pin).

## Limitations (honest)

- A unique worn by **zero** sampled characters keeps the link — vanishingly rare for
  anything in the meta's top-uniques list (those are popular by definition), and it
  resolves the moment a sampled player equips it.
- A handful of notables/anointments genuinely absent from the tree export (Path Seeker,
  Lucid Dreaming, …) keep the link.

## Expected outcome

~68% → **~95%** coverage: notables ~83%→~98%, anointments 0%→~90%, uniques 54%→~95%,
with **no new data source** — everything derived from data already pulled (the GGG tree
export + the poe.ninja sample's items, jewels, and flasks).

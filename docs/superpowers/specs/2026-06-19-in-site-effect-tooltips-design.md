# In-site effect tooltips — design

**Date:** 2026-06-19
**Status:** Approved design (pre-implementation)
**Branch:** `feature/in-site-effect-tooltips`

## Problem

When a user inspects a build in Tincture's detail panel, they can see *what* a build
runs but not *what those things do*. Today:

- **Rare/magic items** already show their full mod text (parsed from each `.build`
  file's `additional_text`). ✅
- **Unique items** show the name only — no effect text.
- **Runes / Soul Cores** (the "Weapon augments" section) show name + adoption % only.
- **Skill gems, support gems, passive notables** show a `data-tip` that just says
  "look it up ↗" and links out to **Google Search**.

So to learn what an augment, rune, unique, gem, or notable actually does, the user has
to leave the site. We want that knowledge available **in-window**.

## Goals

- Hover (desktop) / tap (mobile) any **rune, soul core, unique, skill gem, support gem,
  or notable** in the build detail panel and see exactly what it does, without leaving
  the site.
- Source the effect text **honestly and with near-zero upkeep**, consistent with
  Tincture's existing "derive, attribute, pin — don't scrape or hand-maintain" posture.
- **Strictly additive**: the feature can only add information. If data is missing for
  any entity, the UI shows exactly today's "look it up ↗" link. It can never regress.

## Non-goals

- No change to rare/magic item display (already complete).
- No live network calls at runtime; no backend; no database. (Tincture stays static +
  scheduled jobs.)
- Not a full game-data compendium. We cover the entities that appear in build detail,
  not every item/mod in the game.
- The ascendancy "how it plays" primers are a **separate** evergreen/editorial effort
  (extending `ASC_TAGS`); out of scope here.

## Decisions (locked with owner)

1. **Scope:** full coverage — runes/soul cores, uniques, skill gems, support gems, and
   passive notables.
2. **Interaction:** hybrid — hover/focus on desktop, tap-to-open on touch.
3. **Data source:** derive a compiled `effects.json` at build time, version-pinned,
   attributed, CI-refreshed, failing safe to the existing link. (See refinement below.)

## Post-spike refinement (2026-06-19)

A data-shape spike during planning improved the data source. The effect text we need is
**already present in the poe.ninja character data the `build-from-ninja.cjs --enumerate`
pass pulls every week**, so we derive it there instead of adding a new PoB2 `Data/`
dependency:

- **Runes / soul cores:** `socketedItems[].explicitMods` on equipped gear — slot-prefixed,
  self-describing (e.g. `"Boots: 5% increased Movement Speed"`). Accumulate the union of
  distinct lines per rune across sampled characters.
- **Uniques:** the unique item's own `name` / `baseType` / `explicitMods` / `flavourText`.
- **Skill / support gems:** the gem `itemData.secDescrText || descrText` (in-game text);
  gem **kind + tags** come from the already-fetched PoB2 `Gems.lua` (MIT).
- **Notables:** the GGG `poe2-skilltree-export` (pinned `0.5.2`) node `stats[]`.

So the only PoB2 use is `Gems.lua` (which the pipeline already downloads). Generation
folds into the existing weekly enumerate pass via a new pure module `tools/effects.cjs`
(unit-tested with `node --test`) rather than a separate PoB2-Lua-uniques parser. Same
honesty / fail-safe / attribution posture, **fewer dependencies and lower upkeep**. The
implementation plan (`docs/superpowers/plans/2026-06-19-in-site-effect-tooltips.md`)
follows this refinement.

## Architecture

Four independently testable pieces:

### 1. Build-time compiler — `tools/build-effects.cjs`
- Node, sibling to `tools/build-from-ninja.cjs`. **Off the hourly path** — runs in
  `builds.yml` (weekly) and on demand, never in the hourly `distill.yml`.
- Inputs (both **version-pinned**):
  - **PoB2 `Data/`** (MIT) — unique mod text, gem descriptions, rune/soul-core effects.
    The Lua-in-Node parsing path already exists here (we parse PoB2 `Gems.lua` for gem
    IDs in `build-from-ninja.cjs`).
  - **GGG passive-tree export** (pinned 0.5.x, already fetched by `scripts/treedata.py`)
    — notable stat lines.
- Output: `data/effects.json` (see schema below) + a printed **coverage report**
  (which entities resolved vs. fell back), so we never silently over-claim.
- Fails safe: a bad/again-unavailable source leaves the committed `effects.json`
  untouched and exits non-zero in CI (so a bad refresh is visible but never ships
  garbage).

### 2. Data contract — `data/effects.json`
One small file fetched once by the front end (like `data.json`), keyed by type +
normalized name, with a provenance/attribution header:

```json
{
  "meta": {
    "generated": "2026-06-19T00:00:00Z",
    "sources": [
      {"name": "PathOfBuilding-PoE2", "ref": "<tag/commit>", "license": "MIT", "url": "https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2"},
      {"name": "poe2-skilltree-export", "ref": "0.5.x", "url": "https://github.com/grindinggear/poe2-skilltree-export"}
    ]
  },
  "runes":     { "<norm>": { "name": "Saqawal's Rune of the Sky", "weapon": "…", "armour": "…" } },
  "soulcores": { "<norm>": { "name": "Soul Core of Quipolatl",   "weapon": "…", "armour": "…" } },
  "uniques":   { "<norm>": { "name": "Shavronne's Satchel", "base": "…", "mods": ["…"], "flavour": "…" } },
  "gems":      { "<norm>": { "name": "Lightning Arrow", "kind": "skill", "desc": "…", "tags": ["bow","lightning"] } },
  "notables":  { "<norm>": { "name": "…", "stats": ["…"] } }
}
```

Notes:
- `runes`/`soulcores` carry **separate `weapon` and `armour` text** because a rune grants
  different mods depending on what it is socketed into. The card shows both.
- `gems.kind` is `"skill"` or `"support"`.
- `flavour` on uniques is optional.

### 3. Matching / normalization layer (the trickiest honest detail)
The names that appear in the UI do not exactly equal PoB2's keys:
- Rune names in `meta-detail.json` come **tiered** ("**Perfect** Iron Rune",
  "**Greater** …"); the base effect scales by tier.
- Uniques are matched by name from `.build` text; apostrophes/casing vary.
- Soul cores vs. runes are different item classes but display together.

Approach:
- The compiler emits **normalized keys** (lowercase, strip punctuation/apostrophes) and
  records tier handling. A small **alias map** covers tier prefixes
  (`Lesser|Greater|Perfect|…`) and known display-name quirks.
- The front-end lookup `effectFor(type, name)` applies the **same** normalization +
  alias rules before lookup.
- Any unmatched name → **fallback link** (no fabrication, no wrong text).
- The naming rule from prior work stands: `.build` gem IDs are verbatim from PoB2
  `Gems.lua` and must never be normalized; normalization here applies only to the
  **glossary lookup key**, not to anything written into a `.build` file.

### 4. Front-end glossary + card — in `index.html`
- `EFFECTS` global loaded like `data.json` (same try/catch fail-safe).
- `effectFor(type, name)` → entry or `null`.
- `entityCard(entry, kind)` → themed card HTML using existing design tokens
  (`--ink-2` bg, `--hair-strong` border, Cinzel header, Spectral body, IBM Plex Mono
  labels, gold/verdigris accents). Card contents by kind:
  - **Rune / Soul Core:** name + badge; "In weapons" mods; "In armour" mods; source footer.
  - **Unique:** name (gold) + base; mod list; optional flavour (italic); source footer.
  - **Skill / Support gem:** name + kind badge + tag chips; concise description; footer.
  - **Notable:** name + stat lines; footer ("via passive tree").
- **Hybrid interaction controller** (`tipController`): on `(hover: hover)` devices,
  open on hover/focus (keyboard accessible); on `(hover: none)` devices, tap opens a
  pinned card, with tap-outside / Esc / second-tap to close, **one open at a time**.

## Integration points (verified anchors)

- **Runes / soul cores:** `metaGearGrid()` "Weapon augments" section, ~`index.html:1757`
  — replace the Google-link `data-tip` with a card when data exists.
- **Skills / supports / notables:** the `.meta-item.tip-row` entities rendered in
  `metaCoreGrid()`, ~`index.html:637` — attach cards.
- **Uniques:** enrich `itemTip(it)`, ~`index.html:1765` — a unique currently renders
  name only; pull its mod list/flavour from the glossary into the existing item tooltip.
- **Rares:** unchanged — they already carry full mod text from `additional_text`.

## Error handling / fail-safe

- `effects.json` 404 or parse error → `EFFECTS` stays empty → every entity falls back to
  today's link. No console errors.
- Per-entity miss → that one entity falls back; the rest still render cards.
- This honors the project rule: never let an upstream/data issue break the deployed site.

## Accessibility

- Cards keyboard-focusable; `role="tooltip"` + `aria-describedby`; Esc closes; visible
  focus ring (`:focus-visible`). Extends the behavior `.bv-tip` already has.

## Testing (honesty invariants)

- **Schema test:** `effects.json` is well-formed; required keys present; rune/soulcore
  entries have both `weapon` and `armour`.
- **Coverage test:** the top-N runes/uniques/gems by adoption in `meta-detail.json`
  resolve via `effectFor`; **misses are warn-listed on stderr**, never silently passed.
  We do not claim coverage we lack.
- **Normalization unit tests:** tier prefixes (Lesser/Greater/Perfect), apostrophes,
  casing, weapon-vs-armour split.
- **Fallback test:** unknown name returns `null` and renders the link without throwing.

## CI

- `builds.yml` gains a pinned `build-effects` step that runs `build-effects.cjs`,
  validates the output (schema + coverage), and commits `data/effects.json`.
- `test.yml` runs the new tests on code changes.
- A source **version bump** (PoB2 tag / tree-export version) is a deliberate PR — same
  posture as the existing tree-export pin.

## Attribution / legal posture

- Card footer credits the source ("via Path of Building 2" / "via passive tree").
- Add a line to the open-data/credits section and `README` crediting PoB2 (MIT) and the
  GGG export.
- Consistent with the existing posture: derive at build time, attribute, pin a version;
  never vendor a wholesale copy of upstream data.

## Risks & first step

- **Risk:** PoB2's rune/soul-core coverage may be less complete than its uniques/gems.
  **Mitigation / first implementation task:** a ~30-minute spike that loads pinned PoB2
  `Data/` and reports rune/soul-core/unique/gem coverage against the entities actually
  present in `meta-detail.json` + the `builds/*.build` files. Whatever PoB2 doesn't cover
  simply keeps the link. This decision is data-driven, not assumed.
- **Risk:** name-matching gaps. **Mitigation:** the coverage report + warn-list make gaps
  visible; alias map closes the common ones; everything else falls back safely.

## Rollout

1. Spike (coverage check) → confirm/adjust scope per real coverage.
2. Compiler + `effects.json` + tests (data backbone, no UI yet).
3. Front-end glossary + `entityCard` + hybrid controller, wired at the three integration
   points, with fallbacks.
4. CI wiring + attribution.
5. Verify in local preview (hover + simulated touch), confirm zero console errors, ship.

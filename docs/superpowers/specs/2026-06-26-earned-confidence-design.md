# Earned Confidence — true, proven build-quality signals

**Status:** approved design · **Date:** 2026-06-26 · **Type:** pipeline + front-end feature
**Branch:** `feature/earned-confidence`

## Overview

Make every confidence signal Tincture shows about a Decanted build **true and earned** instead of
implied. Today the build view shows the **ladder median** EHP/DPS for the ascendancy (which diverges
30–300% from the character the user actually downloads), and the green "QA" chip green-checks builds
with real holes (the #1 pick — 24% of the ladder — ships at uncapped lightning resistance with an
unqualified ✓). This workstream:

1. Reads the featured character's **own** numbers from the cached poe.ninja payload's
   `defensiveStats` block (already fetched, never used).
2. Adds **real quality checks** — resistances capped (against the game's own max-res), fully
   ascended, main skill fully linked — and persists them honestly.
3. **Curates selection** by preferring the genuinely sound, complete real build, then **discloses any
   remaining gap** rather than hiding it (the chosen `Prefer, then disclose` policy).
4. Surfaces the build's **own** stats + a transparent **"Reconstruction checks"** chip + honest
   provenance + true build age.

Every new signal is read from data we already fetch, or omitted. **Nothing is fabricated.** No change
to `pop`/`rank`/`tier`/the ledger — the honesty invariants stay intact; we just make the confidence
justified.

## Goals

- The EHP/resists/survivability shown for a build are **that exact build's**, matching the `.build` the
  user Decants — never a population median presented as the build.
- A user can see, truthfully, that the featured build is **sound**: resistances capped, fully ascended,
  main skill linked — and where it isn't, see the honest gap and the fix ("cap this before you map").
- The featured character per ascendancy is **selected for genuine soundness**, not pool-relative balance.
- The trust chip states **what was actually verified**, never implies power beyond it.
- Coverage stays **23/23** (prefer-then-disclose never drops a real build to template).
- Stays on-ethos: additive `meta-detail.json` fields (old readers ignore them), fail-safe, no new deps,
  no new data source.

## Non-goals (YAGNI)

- **No** separate "Tincture's Pick" editorial layer (the `earn-it` path was chosen, not the opinion layer).
- **No** hand-ranking, re-tiering, or reordering of the ledger; **no** edits to `pop`/`n`/`delta`/`tier`.
- **No** scraped or fabricated clearance tiers / boss-kill flags — only signals literally present in the
  payload (`defensiveStats`, `passiveCounts`, `level`). If the payload doesn't prove it, we don't claim it.
- **No** per-build budget bands (separate future workstream).
- **No** prominent precise DPS headline (see §6 — PoE2 per-build DPS is config-dependent and coarse).

## Honesty guardrails (load-bearing — do not cross)

- A check renders ✓ **only** when its underlying field proves it true. A failing/unknown check renders a
  neutral ⚠ note or is omitted — **never a green check over a hole.**
- "Capped" means `resistance ≥ resistanceMax` (the game's own cap, which gear can raise above 75) — we
  always show the actual value and the cap, so the claim is auditable.
- Snapshot age is disclosed: a stat is the character's value **as of its last poe.ninja snapshot**; we show
  that date so "capped" can't silently mean "capped three weeks ago."
- We never present a derived/median number as the build's own; the median, when shown, is explicitly
  labelled "typical for this ascendancy."

## Data source — `parseDefensiveStats(char)` (new, in `tools/build-from-ninja.cjs`)

The cached character JSON (`tools/.cache/c-*.json`) carries a `defensiveStats` object the pipeline
currently ignores (it decodes the PoB XML via `parsePobDefence` at `build-from-ninja.cjs:63` instead).
`defensiveStats` is richer and decode-failure-proof. Confirmed fields (sample: martial-artist L100):

| Field | Meaning | Use |
|---|---|---|
| `effectiveHealthPool` | the build's own EHP (e.g. 31555) | headline "this build" EHP |
| `life`, `energyShield`, `ward` | pool split | defence panel |
| `fireResistance` + `fireResistanceMax` + `fireResistanceOverCap` | current / cap / surplus | capped check + display |
| `coldResistance` + `…Max` + `…OverCap` | " | " |
| `lightningResistance` + `…Max` + `…OverCap` | " | " |
| `chaosResistance` + `…Max` + `…OverCap` | " | shown, **not** required to be capped |
| `lowestMaximumHitTaken` | biggest single hit the build survives | "survives a hit up to {n}" |
| `physical/fire/cold/lightning/chaosMaximumHitTaken` | per-element max hit | optional detail/tooltip |
| `evadeChance`, `armour`, `blockChance`, `deflectChance` | layers | defence panel (existing-ish) |

Plus, top-level on the character: `passiveCounts` (`{passives, anoints, ascendancy, bonusPassives}`),
`level`, `keystones[]`, `updatedUtc` (snapshot age).

`parseDefensiveStats(char)` returns a compact object (all fields optional / fail-safe — a missing field is
omitted, never defaulted to a fake number):

```js
{
  ehp, life, es, ward,
  resists: { fire, cold, lightning, chaos },          // current values (numbers)
  resistMax: { fire, cold, lightning, chaos },         // the game's caps
  capped:   { fire: bool, cold: bool, lightning: bool },// resist >= resistMax
  biggestHit,                                          // lowestMaximumHitTaken
  evade, armour, block,
}
```

`parsePobDefence` (the existing PoB-XML decoder) is kept as a **fallback** merged under
`parseDefensiveStats` — if `defensiveStats` is absent on an older cached payload, we still get a defence
layer (without the new `resistMax`/`capped`/`biggestHit`, which then simply don't render).

## Persisted schema — additive `meta-detail.json` fields

`build-from-ninja.cjs` already persists `meta.byAsc[slug].build = { passives, skills, items, defence,
quality }` (line ~732). This workstream **adds** fields; nothing is renamed or removed, so a deployed
older `index.html` keeps working.

**`build.defence`** (now sourced from `parseDefensiveStats`, fallback `parsePobDefence`) gains:
- `biggestHit` — `lowestMaximumHitTaken`
- `resistMax: { fire, cold, lightning, chaos }`
- `capped: { fire, cold, lightning }` (booleans)
- existing `ehp/life/es/resists/evade/...` keep their names and meaning (already the character's own).

**`build.quality`** (currently `{ level, sample, onMetaWeapon, gemsValid, treeConnected, warnings }`) gains:
- `resistsCapped` — `capped.fire && capped.cold && capped.lightning`
- `ascendancyPoints` — `passiveCounts.ascendancy` (e.g. 8)
- `fullyAscended` — `ascendancyPoints >= 8`
- `mainSkillSupports` — support-gem count on the main active skill group (the `/SkillGem` group with the
  most supports)
- `mainSkillLinked` — `mainSkillSupports >= 3`
- `selectedFrom` — number of candidates the pick was chosen from (`cands.length`)
- `snapshotUtc` — `char.updatedUtc` (the source character's snapshot time, for honest stat-age display)

`buildsUpdated` (already written at `build-from-ninja.cjs:~656`, currently unused by the front end)
becomes the build view's freshness source (§5).

## Quality checks — new, in `qa()` (`build-from-ninja.cjs:282`)

Add **warn-level** checks (the existing hard-fails — empty/broken tree, off-meta weapon, unresolved
active gem — are unchanged; a real ladder build is never hard-failed for these new soft signals):

- **Resistances capped** — warn if any of fire/cold/lightning `< resistMax`. Drives `quality.resistsCapped`.
- **Fully ascended** — warn if `passiveCounts.ascendancy < 8`. Drives `quality.fullyAscended`.
- **Main skill linked** — warn if the main active skill group has `< 3` supports. Drives
  `quality.mainSkillLinked` / `mainSkillSupports`.

The checks feed the persisted `quality` verdict and the front-end chip; they **do not** change which
builds are loadable (QA's `ok` still gates on hard-fails only).

## Selection — prefer, then disclose (`build-from-ninja.cjs:712-724`)

Replace the pool-relative `min(EHP,DPS)` scorer with a soundness preorder over the existing
candidate set (after the current `level >= 85` and on-meta-weapon narrowing at lines 712–719). Sort
**descending, lexicographically**:

1. `allResistsCapped(p)` — boolean (from `defensiveStats`), capped builds first.
2. `fullyAscended(p)` — `passiveCounts.ascendancy >= 8`.
3. `balance(p)` — `min(ehp/maxE, dps/maxD)`, where **`ehp` is the real `effectiveHealthPool`**
   (fallback to the value-list `ehp`), `dps` the value-list dps — as the tiebreak.

Keys 1–2 are computed cheaply from `defensiveStats` + `passiveCounts` (**no `buildOne` needed**), so the
scan stays inexpensive. `mainSkillLinked` is **not** a selection key (computing it per candidate would
require building each); it is checked on the chosen build and disclosed in the chip — main-skill links
rarely differ across the top candidates, so it's not worth N× the build cost to sort on.

The soundest real build wins. **If none in the pool is flawless, the best one still ships, with the gap
disclosed** (`quality.resistsCapped:false` etc. flow to the chip's honest ⚠ line). Coverage is never
lost. Fail-safe: a candidate with no `defensiveStats` is treated as not-capped/unknown (so a candidate
with data outranks one without), but remains selectable as a last resort.

> Selection change ⇒ the featured character changes for some ascendancies ⇒ `meta-detail.json` is
> regenerated (see §7). QA still gates loadability; variants are unaffected.

## Front end — surface the truth (`index.html`)

1. **Stat panel** (`metaDetailHTML`, ~line 2176): show the build's **own** EHP from
   `md.build.defence.ehp` (today it shows `md.stats.ehp`, the median). Add
   *"survives a hit up to {biggestHit}"* from `defence.biggestHit`. Keep the ascendancy **median** as a
   clearly-labelled secondary line: *"typical for this ascendancy: ~{median} EHP (median of {sample})."*
2. **Trust chip → "Reconstruction checks"** (`qualityChip`, ~line 2003): a transparent checklist, each
   line truthful:
   - `ascendancy valid` · `gems resolve in-game` · `runs the dominant meta weapon` ·
     `all resistances capped` · `fully ascended` · `main skill fully linked`
   - Each renders ✓ when its `quality` field is true; a false check renders a neutral ⚠ with the honest
     fix, e.g. *"Lightning resistance 60% / 75% — cap this before you map."*
   - `onMetaWeapon === null` → honest neutral line: *"no single dominant weapon for this ascendancy — any
     popular weapon is representative"* (today it's silently omitted).
   - Rename the section from the implied "QA ✓" to **"Reconstruction checks — what we verified."**
3. **Defence panel** (`defenceHTML`, ~line 2031): add a capped ✓ / ⚠ mark beside each elemental resist
   pill (using `defence.capped`), and surface `biggestHit`.
4. **Provenance**: *"Selected as the best-rounded of {quality.selectedFrom} level-85+ ladder characters
   running the dominant weapon."* (from `quality.selectedFrom`).
5. **True build age**: drive the build-view freshness line from `META.buildsUpdated` (not `META.updated`),
   and add a staleness flag when builds are older than ~8 days (cadence + grace), reusing the existing
   `is-stale` pattern (~line 2379). Show the source character's `snapshotUtc` where stats are displayed.

All injected values `esc()`-d; numbers coerced (`+x`) at the boundary. Front end renders gracefully
whether or not the regen has run yet (every new field is optional; absent ⇒ that row simply doesn't show).

## DPS handling (confirmed)

Lead with the **rock-solid survivability proof** — own EHP + "largest hit survived" + capped resists.
Show DPS only as labelled context: *"~{n} (approx. tooltip DPS)"*, never a precise headline number.
PoE2 per-build DPS is skill-configuration dependent and the poe.ninja value is coarse; presenting it as
precise would overclaim. The ascendancy median DPS stays as secondary context, labelled.

## Testing

**Node (`tools/test-build-from-ninja.cjs`, `node --test`):**
- `parseDefensiveStats` — returns ehp/resists/resistMax/capped/biggestHit from a fixture payload; omits
  missing fields; returns null-safe on absent `defensiveStats` (falls back to `parsePobDefence`).
- **capped logic** — `res >= max` ⇒ capped; `res < max` ⇒ not capped; over-cap (`res == max`, positive
  overCap) ⇒ capped.
- **selection** — a fixture pool where a capped+ascended candidate has *lower* balance than an
  uncapped one: the capped one is chosen (preorder beats balance).
- **disclosure path** — a pool with no fully-capped candidate: the best is still chosen and
  `quality.resistsCapped === false` (no coverage loss, gap recorded).
- **quality shape** — chosen build's `quality` includes the new fields with correct values.
- **honesty invariant** — a build with an uncapped resist must **never** yield `resistsCapped: true`
  (the check can't green-check a hole); `mainSkillLinked` false when supports < 3.

**Python (`scripts/test_distill.py`):** confirm no existing honesty invariant regresses (data.json schema,
no inflated totals, curated-carries-no-stats). `meta-detail.json` is produced by the Node tool, so its
new-field assertions live in the Node suite.

**Front-end (live preview, `--cache-only` regen):** on ≥3 ascendancies, the displayed EHP equals the
featured character's own EHP (cross-check the `.build`/`.pob`); a build with an uncapped resist shows the
honest ⚠ + fix, not a green check; the chip lines are all true; 0 console errors; renders correctly both
before and after a regen (additive-field fail-safe).

## Rollout / verification

1. **Local, no network** — regenerate `meta-detail.json` from the **existing character cache** with
   `--cache-only` (no poe.ninja calls; the local IP gets throttled, per project ops notes), proving the
   new parse/selection/persisted fields against real cached characters. Run the Node + Python suites.
   Verify the build view in the browser preview.
2. **CI regen** — the real network refresh runs in `.github/workflows/builds.yml` (weekly / manual
   dispatch) to re-pull and re-select from the **live** ladder. The coverage gate (23/23) and QA gate
   guard the committed output.
3. The front-end change deploys independently and is **additive-safe** — it renders correctly against
   both old and freshly-regenerated `meta-detail.json`.

## Risks & mitigations

- **Selection shifts featured characters** → some builds change. *Mitigation:* coverage gate stays 23/23;
  QA still gates loadability; variants untouched; the change is the point (sounder builds surface).
- **`defensiveStats` field names vary by patch/payload.** *Mitigation:* fail-safe parse, fallback to
  `parsePobDefence`, omit anything missing — never fabricate.
- **"Capped" from a stale snapshot.** *Mitigation:* show `snapshotUtc` next to the stats; the build-age
  staleness flag covers the file-level age.
- **DPS coarseness.** *Mitigation:* labelled approximate, never a headline.

## Success criteria

- Displayed build EHP == the featured character's own EHP on ≥3 spot-checked ascendancies (no more
  median-as-build mismatch).
- The #1 pick, if its resistances are uncapped, shows the honest gap + "cap this before you map" — **not**
  an unqualified green check.
- The trust chip is a transparent checklist; every ✓ is provably true and every gap is disclosed.
- All test suites green; coverage 23/23; existing honesty invariants intact (no `pop`/`rank`/`tier` change).

## Integration points (file:line)

- `tools/build-from-ninja.cjs`: new `parseDefensiveStats` (near `parsePobDefence` ~63); new soft checks in
  `qa()` (~282); selection preorder (~712–724); extended `quality`/`defence` persistence (~732–741);
  `buildsUpdated` already written (~656).
- `index.html`: `qualityChip` (~2003), `metaDetailHTML` stat panel (~2176), `defenceHTML` (~2031),
  build-view freshness line (~2181) → `buildsUpdated` + staleness (pattern ~2379).
- `tools/test-build-from-ninja.cjs`: new cases (above).
- `.github/workflows/builds.yml`: unchanged mechanism; used to run the live regen.

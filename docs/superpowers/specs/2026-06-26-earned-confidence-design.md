# Earned Confidence — true, proven build-quality signals

**Status:** approved design (rev. 2, post adversarial verification) · **Date:** 2026-06-26 · **Type:** pipeline + front-end feature
**Branch:** `feature/earned-confidence`

## Overview

Make every confidence signal Tincture shows about a Decanted build **true and earned** instead of
implied. Today the build view headlines the **ladder median** EHP/DPS for the ascendancy (which diverges
30–300% from the character the user actually downloads — verified: martial-artist `stats.ehp` = 45,000
median vs `build.defence.ehp` = 31,671 own), and the green "QA" chip green-checks builds with real holes
(the #1 pick — 24% of the ladder — ships at uncapped lightning resistance with an unqualified ✓). This
workstream:

1. Reads the featured character's **own** numbers from the cached poe.ninja payload's `defensiveStats`
   block (already fetched, never used — `grep` finds zero references in `tools/`, `scripts/`, `index.html`).
2. Adds **real quality checks** — resistances capped (against the game's 75% baseline), fully ascended,
   main skill fully linked — and persists them honestly.
3. **Curates selection** by preferring the genuinely sound, complete real build, then **discloses any
   remaining gap** rather than hiding it (the chosen `Prefer, then disclose` policy).
4. Surfaces the build's **own** stats + a transparent **"Reconstruction checks"** chip + honest
   provenance + true build age — **at every render site** (build view, defence panel, the Counterpoise
   compare table, and variant cards), so no two surfaces contradict each other.

Every new signal is read from data we already fetch, or omitted. **Nothing is fabricated.** No change to
`pop`/`rank`/`tier`/the ledger — the honesty invariants stay intact; we just make the confidence justified.

### Verified premises (from the adversarial spec review)

- `defensiveStats.effectiveHealthPool` **== PoB `TotalEHP` to within 1 for all 23 classes** (ratio 1.00),
  so it is genuinely the build's own EHP; switching the source is exact, and PoB stays a valid fallback.
- Every one of the 262 cached characters carries a `defensiveStats` block (100% coverage per ascendancy);
  `resistance` is the **current clamped** value, `…ResistanceMax` the cap, `…ResistanceOverCap` the surplus
  (never negative). Uncapped resists are plentiful (146 elemental instances `< 75`), so the disclosure path
  genuinely fires.
- `passiveCounts.ascendancy` is reliably 8 on featured chars; `updatedUtc`, `keystones[]`,
  `lowestMaximumHitTaken`, and the per-element resistance fields all exist verbatim.

## Goals

- The EHP/resists/survivability shown for a build are **that exact build's**, matching the `.build` the
  user Decants — never a population median presented as the build — **on every surface that shows them.**
- A user can see, truthfully, that the featured build is **sound**: resistances capped, fully ascended,
  main skill linked — and where it isn't, see the honest gap and the fix ("cap this before you map").
- The featured character per ascendancy is **selected for genuine soundness**, not pool-relative balance.
- The trust chip states **what was actually verified**, never implies power beyond it, and **never green-
  checks a hole** (including chaos resistance and sub-75 caps).
- Coverage stays **23/23** (prefer-then-disclose never drops a real build to template).
- Stays on-ethos: additive `meta-detail.json` fields (old readers ignore them), fail-safe, no new deps,
  no new data source.

## Non-goals (YAGNI)

- **No** separate "Tincture's Pick" editorial layer (the `earn-it` path was chosen, not the opinion layer).
- **No** hand-ranking, re-tiering, or reordering of the ledger; **no** edits to `pop`/`n`/`delta`/`tier`.
- **No** scraped or fabricated clearance tiers / boss-kill flags — only signals literally in the payload
  (`defensiveStats`, `passiveCounts`, `keystones`, `level`, `updatedUtc`). If the payload doesn't prove it,
  we don't claim it.
- **No** change to the **ledger EHP/DPS sort** or the **Prescription quiz ranking** — both rank an
  *ascendancy* by its *typical* (median) character and are already labelled "median"; they stay median (see
  §6, explicit). They are population shortlists, not per-build claims.
- **No** per-build budget bands (separate future workstream).
- **No** prominent precise DPS headline (PoE2 per-build DPS is config-dependent and coarse; §7).

## Honesty guardrails (load-bearing — do not cross)

- A check renders ✓ **only** when its underlying field proves it true. A failing/unknown check renders a
  neutral ⚠ note or is omitted — **never a green check over a hole.**
- **"Capped" means `resistance ≥ 75`** — PoE2's base maximum resistance and the universally-meaningful
  survivability floor. This is deliberately **not** `resistance ≥ resistanceMax`: a map/penalty-lowered cap
  (e.g. 74/74) must read **not** capped (it's under the floor), and a gear-raised cap with the build above
  75 but below its personal max (e.g. 78/80) must read capped (it's safe — the unfilled headroom to 80 is a
  bonus, not a hole). We always display the actual value (and the personal `resistanceMax` when ≠ 75, plus
  overcap headroom), so the claim is auditable at the point it's made.
- **Chaos counts.** The aggregate "all resistances capped" claim requires fire/cold/lightning **and** chaos
  to be capped **unless** the build is Chaos-immune (`keystones[]` contains "Chaos Inoculation"). When chaos
  is uncapped and the build isn't CI-immune, an explicit neutral chaos line is shown — the word "all" is
  never emitted while any resistance (including chaos) is a real hole.
- Snapshot age is disclosed **at the point of claim**: the source character's `updatedUtc` is shown on both
  the stat panel **and** the Reconstruction-checks chip (the capped claim is the one that can go stale), so
  "capped ✓" can't silently mean "capped three weeks ago."
- We never present a derived/median number as the build's own; the median, when shown, is explicitly
  labelled "typical for this ascendancy."

## Data source — `parseDefensiveStats(char)` (new, in `tools/build-from-ninja.cjs`)

The cached character JSON (`tools/.cache/c-*.json`) carries a `defensiveStats` object the pipeline ignores
(it decodes the PoB XML via `parsePobDefence` at `build-from-ninja.cjs:63`). `defensiveStats` is richer and
decode-failure-proof. Confirmed fields:

| Field | Meaning | Use |
|---|---|---|
| `effectiveHealthPool` | the build's own EHP (== PoB TotalEHP) | headline "this build" EHP |
| `life`, `energyShield`, `ward` | pool split | defence panel |
| `{fire,cold,lightning,chaos}Resistance` | **current clamped** resist value | capped check + display |
| `{…}ResistanceMax` | the build's personal cap (75 baseline; gear can raise, penalties lower) | display when ≠ 75 |
| `{…}ResistanceOverCap` | surplus above the personal cap (≥ 0) | "headroom" display |
| `lowestMaximumHitTaken` | biggest single hit the build survives | "survives a hit up to {n}" |
| `armour`, `evadeChance`, `blockChance` | layers | defence panel |

Plus, top-level on the character: `passiveCounts` (`{passives, anoints, ascendancy, bonusPassives}`),
`level`, `keystones[]` (each `{name, …}` — used for Chaos Inoculation detection), `updatedUtc` (snapshot age).

**`parseDefensiveStats(char)` return shape** (all fields optional / fail-safe — a missing field is omitted,
never defaulted to a fake number):

```js
{
  ehp, life, es, ward, armour,
  resists:    { fire, cold, lightning, chaos },   // current clamped values (numbers)
  resistMax:  { fire, cold, lightning, chaos },   // personal caps
  overcap:    { fire, cold, lightning, chaos },   // surplus above cap (>= 0)
  capped:     { fire, cold, lightning, chaos },   // bool: resists[el] >= 75
  chaosImmune,                                    // bool: keystones[] has "Chaos Inoculation"
  biggestHit,                                     // lowestMaximumHitTaken
  evade, block,
}
```

**Merge precedence (field-by-field).** Both decoders run on the same character; the persisted `defence` is
`{ ...parsePobDefence(char.pathOfBuildingExport), ...parseDefensiveStats(char) }` — `defensiveStats` wins for
overlapping fields (`ehp`, `life`, `es`, `resists`, `evade`, `block`), and **`pdr`/`crit` are retained from
the PoB fallback** (they are rendered by `defenceHTML` and `defensiveStats` doesn't carry a single scalar for
them). `resistMax`, `overcap`, `capped`, `chaosImmune`, `biggestHit`, `armour` come only from
`parseDefensiveStats`. When `defensiveStats` is absent (older snapshot — the currently-featured **invoker**
`klfz-7690/ZZZZZZKLF` has no cache file and exercises this path), `defence` is just `parsePobDefence`'s output
and the new fields are absent ⇒ their UI rows simply don't render. **This fallback is load-bearing and must
be tested**, not just asserted (selection runs against the live ladder in CI; the local cache is a
`--cache-only` artifact, so the featured set there is illustrative).

## Persisted schema — additive `meta-detail.json` fields

`build-from-ninja.cjs` already persists `meta.byAsc[slug].build = { passives, skills, items, defence,
quality }` (line ~732). This workstream **adds** fields; nothing is renamed or removed, so a deployed older
`index.html` keeps working.

**`build.defence`** (now the merged object above) gains: `resistMax`, `overcap`, `capped`, `chaosImmune`,
`biggestHit`, `armour`. Existing `ehp/life/es/resists/evade/pdr/crit/block` keep their names and meaning
(already the character's own; `ehp` now from `effectiveHealthPool`, numerically identical to the prior
`TotalEHP`).

**`build.quality`** (currently `{ level, sample, onMetaWeapon, gemsValid, treeConnected, warnings }`) gains:
- `resistsCapped` — `capped.fire && capped.cold && capped.lightning && (capped.chaos || chaosImmune)` — the
  predicate for the aggregate "all resistances capped" ✓.
- `ascendancyPoints` — `passiveCounts.ascendancy`; `fullyAscended` — `ascendancyPoints >= 8`.
- `mainSkillSupports` — support count on the **main** active skill group (the highest-DPS group, i.e. the
  one already chosen as `mainSkillName` via `bestDps` at `build-from-ninja.cjs:~247` — **not** "the group
  with the most supports"); `mainSkillLinked` — `mainSkillSupports >= 3`.
- `selectedFrom` — `cands.length` (the candidate pool the pick won, after the L85+/on-meta narrowing).
- `snapshotUtc` — `char.updatedUtc` (the source character's snapshot time).

`buildsUpdated` (already written at `build-from-ninja.cjs:657`, currently unread by the front end) becomes
the build view's freshness source (§5.5).

**Variants** (`build-from-ninja.cjs:761-768`) get the **same** `defence` treatment: their `defence` is routed
through the merged `parseDefensiveStats(cand.char)` (the char is already in hand), persisting variant
`capped`/`resistMax`/`biggestHit`/`snapshotUtc`, so variant cards can show honest cap marks too.

## Quality checks — new, in `qa()` (`build-from-ninja.cjs:282`)

Add **warn-level** checks (the existing hard-fails — empty/broken tree, off-meta weapon, unresolved active
gem — are unchanged; a real ladder build is never hard-failed for these soft signals):
- **Resistances capped** — warn if `!resistsCapped` (any of fire/cold/lightning `< 75`, or chaos `< 75`
  without Chaos Inoculation).
- **Fully ascended** — warn if `passiveCounts.ascendancy < 8`.
- **Main skill linked** — warn if the main (highest-DPS) active skill group has `< 3` supports.

The checks feed the persisted `quality` verdict and the front-end chip; they **do not** change which builds
are loadable (QA's `ok` still gates on hard-fails only).

## Selection — prefer, then disclose (`build-from-ninja.cjs:712-724`)

Replace the pool-relative `min(EHP,DPS)` scorer with a soundness preorder over the existing candidate set
(after the current `level >= 85` and on-meta-weapon narrowing at lines 712–719). Sort **descending,
lexicographically**:

1. `allResistsCapped(p)` — `capped.fire && capped.cold && capped.lightning && (capped.chaos || chaosImmune)`,
   from `defensiveStats`. Capped builds first.
2. `fullyAscended(p)` — `passiveCounts.ascendancy >= 8`.
3. `balance(p)` — `min(ehp/maxE, dps/maxD)`, where **`ehp` is the real `effectiveHealthPool`** (fallback to
   the value-list `ehp`), `dps` the value-list dps — the tiebreak.

Keys 1–2 are computed cheaply from `defensiveStats` + `passiveCounts` (**no `buildOne` needed**), so the scan
stays inexpensive. `mainSkillLinked` is **not** a selection key (computing it per candidate would require
building each); it's checked on the chosen build and disclosed in the chip.

The soundest real build wins. **If none in the pool is flawless, the best one still ships, with the gap
disclosed** (`quality.resistsCapped:false` etc. flow to the chip's honest ⚠ line). Coverage is never lost.
Fail-safe: a candidate with no `defensiveStats` is treated as not-capped/unknown (so a data-bearing capped
candidate outranks it) but remains selectable as a last resort.

> Selection change ⇒ the featured character changes for some ascendancies ⇒ `meta-detail.json` is
> regenerated (§8). QA still gates loadability; variants are unaffected by the *ordering* (they're still the
> next-best distinct builds), but now carry the new defence fields.

## Front end — surface the truth, everywhere (`index.html`)

1. **Stat panel** (`metaDetailHTML`, line ~2176): headline the build's **own** EHP via
   `(md.build && md.build.defence && md.build.defence.ehp) ?? md.stats.ehp` — **the `?? md.stats.ehp`
   fallback is mandatory**: template-only ascendancies (no `md.build`) and pre-regen `meta-detail.json` lack
   `build.defence.ehp`, and must not lose their EHP line. Label by source: the build's own EHP vs *"typical
   for this ascendancy: ~{median} EHP (median across {sample} sampled characters)"* (reuse the existing
   phrasing at line ~2180; `md.stats.sample` is available). Add *"survives a hit up to {biggestHit}"* from
   `defence.biggestHit`. (Note: the own-EHP is already shown in the defence panel today — this change is
   **headline prominence + the fallback**, not first-time exposure; `md.stats.ehp` is *correctly* labelled
   "median" today, it is not mislabelled.)
2. **Trust chip → "Reconstruction checks"** (`qualityChip`, line ~2007): a transparent checklist. The
   current `qualityChip` only emits positive ✓ items and has **no ⚠/negative branch or CSS** — this adds one
   (a `bvq warn` class is in scope). Lines, each truthful:
   - `ascendancy valid` · `gems resolve in-game` · `runs the dominant meta weapon` ·
     `all resistances capped` · `fully ascended` · `main skill fully linked`
   - Each renders ✓ when its `quality` field is true; a false check renders a neutral ⚠ with the honest fix.
     The ⚠ pulls the failing element's value from `md.build.defence.resists[el]` against the 75 floor, e.g.
     *"Lightning resistance 60% — cap it to 75% before you map."* A capped line shows the values inline so a
     sub-75/penalized case can't read as a bare ✓.
   - **Chaos:** when `chaosImmune` is false and `capped.chaos` is false, a dedicated neutral line:
     *"Chaos resistance {v}% — uncapped (no Chaos Inoculation)."* The aggregate "all resistances capped ✓"
     is shown only when `quality.resistsCapped` is true.
   - `onMetaWeapon === null` → honest neutral line: *"no single dominant weapon for this ascendancy — any
     popular weapon is representative"* (today it's silently omitted).
   - The chip carries an *"as of {snapshotUtc}"* qualifier so every ✓ is time-stamped at the point of claim.
   - Rename the section from the implied "QA ✓" to **"Reconstruction checks — what we verified."**
3. **Defence panel** (`defenceHTML`, line ~2019; resist pills built by `resPill` at ~2023): **replace the
   hardcoded `v>=75` capped class** with `defence.capped[el]` (fall back to `v>=75` on the displayed value
   when `capped` is absent, i.e. PoB-fallback builds), show `resistMax` when ≠ 75 and overcap headroom, and
   surface `biggestHit`.
4. **The Counterpoise compare table** (`ascForCompare` ~2056-2057; `compareTableHTML` rows ~2108-2109; `resRow`
   ~2092-2094): switch the EHP source to `(md.build && md.build.defence && md.build.defence.ehp) ?? md.stats.ehp`,
   **relabel the rows "EHP"/"DPS" (drop "Median")**, and **replace `resRow`'s hardcoded `v>=75`** with
   `defence.capped[el]`. Without this, the compare table shows the median + a wrong cap tick while the build
   panel for the same slug shows the own number — a contradiction on adjacent screens.
5. **Variant cards** (`variantsHTML` ~2146-2149): surface the same capped ✓/⚠ marks from the variant's
   persisted `defence.capped`, so a variant can't ship uncapped with no honesty signal.
6. **Provenance** (stat panel): *"Selected as the **soundest** (resists capped, fully ascended) of
   {quality.selectedFrom} level-85+ ladder characters running the dominant weapon."* — wording matches the
   selection key (capped+ascended first, **not** "best-rounded"). The "running the dominant weapon" clause is
   included only when `onMetaWeapon !== null` (the cohort was weapon-narrowed).
7. **True build age**: drive the build-view freshness line from `META.buildsUpdated` (line ~2181 currently
   uses `META.updated`); add a **new** per-build-view staleness flag — stale when
   `Date.now() - new Date(META.buildsUpdated) > 8*86400e3` (~weekly cadence + 1-day grace). Only the
   `.is-stale` CSS visual is reused from the page-global pattern (line ~2379/2384, which keys off
   `DATA.updated` at a 3-hour threshold — a separate computation); the build view needs its own freshness node.

**Explicitly unchanged (population shortlists, stay median, already labelled):**
- **Ledger EHP/DPS sort** (`statOf` ~1819-1822; buttons ~1127-1129; status line ~2333) — ranks ascendancies
  by their typical character; tooltips/status already say "median". No change.
- **Prescription quiz** ranking (`rxCandidates` ~2976; `rxScore` ~2986/2999-3000; footnote ~1114) — a
  population match shortlist; keeps the median for ranking and the "median" label. No change.

All injected values `esc()`-d; numbers coerced (`+x`) at the boundary. Every new field is optional; absent ⇒
that row simply doesn't render (the one *changed* read — headline EHP — has the mandatory `?? md.stats.ehp`
fallback above).

## DPS handling (confirmed)

Lead with the **rock-solid survivability proof** — own EHP + "largest hit survived" + capped resists. Show
DPS only as labelled context: *"~{n} (approx. tooltip DPS)"*, never a precise headline number. PoE2 per-build
DPS is skill-configuration dependent and the poe.ninja value is a coarse median; presenting it as precise
would overclaim. The ascendancy median DPS stays as secondary context, labelled.

## Testing

**Node (`tools/test-build-from-ninja.cjs`, `node --test`):**
- `parseDefensiveStats` — returns ehp/resists/resistMax/overcap/capped/chaosImmune/biggestHit/armour from a
  fixture; omits missing fields; returns null-safe on absent `defensiveStats`.
- **merge precedence** — `defence` keeps `pdr`/`crit` from the PoB fallback while taking ehp/resists/capped
  from `defensiveStats`; absent-`defensiveStats` path yields a PoB-only object with no `capped` (the
  invoker-style fallback).
- **capped predicate (honesty)** — `res >= 75` ⇒ capped; a **74/74** penalized-cap build ⇒ **not** capped
  (must not green-check); a **78/80** raised-cap build ⇒ capped (must not false-negative).
- **chaos honesty** — fire/cold/lightning capped + chaos `0%` + no CI ⇒ `resistsCapped === false`; same with
  a "Chaos Inoculation" keystone ⇒ `resistsCapped === true`.
- **selection** — a capped+ascended candidate with *lower* balance beats an uncapped higher-balance one.
- **disclosure path** — a pool with no fully-capped candidate still selects the best and records
  `quality.resistsCapped === false` (no coverage loss).
- **main skill** — `mainSkillSupports` is counted on the highest-DPS group; `< 3` ⇒ `mainSkillLinked:false`.
- **quality shape** — chosen build's `quality` includes all new fields with correct values.

**Python (`scripts/test_distill.py`):** confirm no existing honesty invariant regresses (data.json schema,
no inflated totals, curated-carries-no-stats). `meta-detail.json` is produced by the Node tool, so its
new-field assertions live in the Node suite.

**Front-end (live preview, `--cache-only` regen):** on ≥3 ascendancies, the displayed EHP equals the
featured character's own EHP (cross-check the `.build`/`.pob`); a build with an uncapped resist (e.g. the
Gemling chaos case or a sub-75 elemental) shows the honest ⚠ + fix, **not** a green check; the chip,
defence pills, compare table, and variant cards **agree** for the same slug; a **template-only** ascendancy
still shows its (median, labelled) EHP line; 0 console errors; renders correctly both before and after a regen.

## Rollout / verification

1. **Local, no network** — regenerate `meta-detail.json` from the **existing character cache** with
   `--cache-only` (no poe.ninja calls; the local IP gets throttled), proving the new parse/selection/persisted
   fields against real cached characters. Run the Node + Python suites. Verify all four render sites in the
   browser preview.
2. **CI regen** — the real network refresh runs in `.github/workflows/builds.yml` (weekly / manual dispatch)
   to re-pull and re-select from the **live** ladder. The coverage gate (23/23) and QA gate guard the output.
3. The front-end change deploys independently and is **additive-safe** for the new fields; the one changed
   read (headline EHP) has the mandatory `?? md.stats.ehp` fallback, so it is safe against old/template data.

## Risks & mitigations

- **Selection shifts featured characters** → some builds change. *Mitigation:* coverage gate stays 23/23; QA
  still gates loadability; the change is the point (sounder builds surface).
- **`defensiveStats` absent on an older snapshot** (e.g. featured invoker). *Mitigation:* `parsePobDefence`
  fallback (tested); new fields omit; EHP falls back to PoB TotalEHP then median.
- **`resistanceMax` field names vary by patch.** *Mitigation:* fail-safe parse, omit anything missing.
- **"Capped" from a stale snapshot.** *Mitigation:* `snapshotUtc` shown on both the stat panel and the chip;
  the build-age staleness flag covers file-level age.
- **DPS coarseness.** *Mitigation:* labelled approximate, never a headline.

## Success criteria

- Displayed build EHP == the featured character's own EHP on ≥3 spot-checked ascendancies (no median-as-build
  mismatch), **on the build panel and the Counterpoise compare table alike**.
- A featured build with any uncapped resistance (incl. chaos without CI, or a sub-75 penalized cap) shows the
  honest gap + fix — **not** an unqualified green check — and the chip, pills, compare, and variant cards
  never contradict each other.
- The trust chip is a transparent, time-stamped checklist; every ✓ is provably true and every gap disclosed.
- All test suites green; coverage 23/23; existing honesty invariants intact (no `pop`/`rank`/`tier` change).

## Integration points (file:line — verified)

- `tools/build-from-ninja.cjs`: new `parseDefensiveStats` (near `parsePobDefence` :63); main-skill identity
  reuse (`mainSkillName`/`bestDps` ~:247); new soft checks in `qa()` (:282); selection preorder (:712-724);
  extended `quality`/`defence` persistence (:732-741); **variant** defence persistence (:761-768);
  `buildsUpdated` already written (:657).
- `index.html`: `qualityChip` (:2007), `metaDetailHTML` stat panel (:2176, freshness :2181), `defenceHTML` /
  `resPill` (:2019/:2023), `ascForCompare` (:2056-2057) + `compareTableHTML`/`resRow` (:2092-2094, :2108-2109),
  `variantsHTML` (:2146-2149), page-global is-stale pattern reused for CSS only (:2379/:2384). Explicitly
  unchanged: ledger sort `statOf` (:1819-1822, :2333), quiz `rxCandidates`/`rxScore` (:2976, :2986-3000, :1114).
- `tools/test-build-from-ninja.cjs`: new cases (above).
- `.github/workflows/builds.yml`: unchanged mechanism; used to run the live regen.

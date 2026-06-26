# Earned Confidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every confidence signal on a Decanted build true and earned — show the featured character's own EHP/resists, add real quality checks (resists capped, fully ascended, main skill linked), select the soundest real build, and surface an honest "Reconstruction checks" chip — with no two render sites contradicting each other.

**Architecture:** Pipeline (`tools/build-from-ninja.cjs`) reads the cached poe.ninja `defensiveStats` block for the build's own numbers, computes honest quality booleans, and persists them additively in `meta-detail.json`. The front end (`index.html`) renders those fields at every site (build panel, defence pills, Counterpoise compare, variants), falling back gracefully when absent. Pure functions are unit-tested with `node --test`; the front end is preview-verified (no JS unit harness exists) because the honesty invariants are enforced and tested in the pipeline.

**Tech Stack:** Node.js (stdlib only, `.cjs`), `node:test`; vanilla inline JS/CSS in a single `index.html`; Python stdlib tests (`scripts/test_distill.py`) unchanged but re-run for regression.

## Global Constraints

- **Honesty — "capped" means `resistance >= 75`** (PoE2 base max-res floor). NOT `>= resistanceMax`: a penalty-lowered 74/74 must read NOT capped; a gear-raised 78/80 must read capped. Always display the actual value so the claim is auditable.
- **Chaos counts.** "All resistances capped" requires fire/cold/lightning AND chaos capped, UNLESS the build is Chaos-immune (`char.keystones[]` contains an entry with `name === 'Chaos Inoculation'`). Otherwise show an explicit neutral chaos line. Never emit "all …capped" while any resistance (incl. chaos) is a real hole.
- **A check renders ✓ only when its field proves it true.** A failing check renders a neutral note, never a green ✓. The ✓/⚠ on the chip, the pills, the compare table, and the variant cards must never contradict each other for the same slug.
- **Never present a derived/median number as the build's own.** Medians, when shown, are labelled "typical for this ascendancy". DPS is always labelled approximate (`~`).
- **No edits to `pop`/`rank`/`tier`/`n`/`delta` or the ledger.** This workstream touches only the *featured character* selection and the build-view presentation.
- **Additive `meta-detail.json` only** — new fields; nothing renamed/removed. Old front ends ignore them; the one changed read (headline EHP) MUST keep a `?? md.stats.ehp` fallback.
- **Pipeline stays stdlib-only, fail-safe** — a missing field is omitted, never defaulted to a fake number; a bad upstream value never breaks the deployed site.
- **Branch:** `feature/earned-confidence`. Commit after every task.
- **Verified anchors:** `parsePobDefence` cjs:63 · `convert` skill loop cjs:227-247 · `qa()` cjs:282 · `buildOne` cjs:576-580 · selection cjs:712-724 · primary persist cjs:732-745 · variant persist cjs:761-768 · `module.exports` cjs:843 · `qualityChip` html:2007 · `defenceHTML`/`resPill` html:2019/2023 · `metaDetailHTML` html:2176 (stats 2178, src 2181) · `ascForCompare` html:2043 (ehp/dps 2056-2057) · `compareTableHTML` resRow html:2092-2094, EHP/DPS rows 2108-2109, foot 2122 · `variantsHTML` html:2140 (resStr 2148-2149) · page is-stale html:2379-2384.

---

### Task 1: `parseDefensiveStats(char)` + `mergeDefence(char)`

**Files:**
- Modify: `tools/build-from-ninja.cjs` (add both functions just after `parsePobDefence`, ~line 77; extend `module.exports` at :843)
- Test: `tools/test-build-from-ninja.cjs`

**Interfaces:**
- Produces: `parseDefensiveStats(char) -> { ehp, life, es, ward, armour, resists:{fire,cold,lightning,chaos}, resistMax:{…}, overcap:{…}, capped:{fire,cold,lightning,chaos}, chaosImmune, biggestHit, evade, block } | null` (each numeric field `null` when absent). `mergeDefence(char) -> object | null` = `parsePobDefence` output with `parseDefensiveStats`'s non-null fields layered over it (defensiveStats wins; `pdr`/`crit` retained from PoB).

- [ ] **Step 1: Write the failing tests**

Add to `tools/test-build-from-ninja.cjs`:

```js
test('parseDefensiveStats: capped is resistance>=75 (penalty-proof, raised-cap-proof)', () => {
  const mk = (f, fm) => ({ defensiveStats: {
    effectiveHealthPool: 31555, life: 1497, energyShield: 2379, lowestMaximumHitTaken: 7188,
    fireResistance: f, fireResistanceMax: fm, fireResistanceOverCap: Math.max(0, f - fm),
    coldResistance: 76, coldResistanceMax: 75, lightningResistance: 75, lightningResistanceMax: 75,
    chaosResistance: 0, chaosResistanceMax: 75 } });
  // penalised cap 74/74 -> NOT capped (under the 75 floor)
  assert.equal(T.parseDefensiveStats(mk(74, 74)).capped.fire, false);
  // gear-raised cap, at 78/80 -> capped (>=75, safe)
  assert.equal(T.parseDefensiveStats(mk(78, 80)).capped.fire, true);
  // exactly 75/75 -> capped
  assert.equal(T.parseDefensiveStats(mk(75, 75)).capped.fire, true);
  const d = T.parseDefensiveStats(mk(76, 75));
  assert.equal(d.ehp, 31555);
  assert.equal(d.biggestHit, 7188);
  assert.equal(d.capped.cold, true);     // 76 >= 75
  assert.equal(d.capped.chaos, false);   // 0 < 75
});

test('parseDefensiveStats: chaosImmune from a Chaos Inoculation keystone', () => {
  const base = { defensiveStats: { effectiveHealthPool: 1, fireResistance: 75, fireResistanceMax: 75 } };
  assert.equal(T.parseDefensiveStats(base).chaosImmune, false);
  const ci = { ...base, keystones: [{ name: 'Chaos Inoculation' }] };
  assert.equal(T.parseDefensiveStats(ci).chaosImmune, true);
  assert.equal(T.parseDefensiveStats({}), null);            // no defensiveStats -> null
  assert.equal(T.parseDefensiveStats(null), null);
});

test('mergeDefence: defensiveStats wins, PoB pdr/crit retained, null ds fields do not clobber', () => {
  // a char with NO pathOfBuildingExport but a defensiveStats block -> ds-only object
  const dsOnly = T.mergeDefence({ defensiveStats: { effectiveHealthPool: 4200, fireResistance: 75, fireResistanceMax: 75 } });
  assert.equal(dsOnly.ehp, 4200);
  assert.equal(dsOnly.capped.fire, true);
  assert.equal(dsOnly.pdr, undefined);                      // no PoB -> no pdr key
  // a char with NEITHER -> null
  assert.equal(T.mergeDefence({}), null);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test tools/test-build-from-ninja.cjs`
Expected: FAIL — `T.parseDefensiveStats is not a function`.

- [ ] **Step 3: Implement both functions**

Insert after `parsePobDefence` (after cjs:77) in `tools/build-from-ninja.cjs`:

```js
// ---- defence profile from poe.ninja's defensiveStats (richer + decode-proof; superset of the PoB layer) ----
// effectiveHealthPool == PoB TotalEHP to within 1 across all classes. "capped" is resistance>=75
// (PoE2 base max-res floor): penalty-lowered caps read uncapped, gear-raised-but-above-75 read capped.
function parseDefensiveStats(char) {
  const ds = char && char.defensiveStats;
  if (!ds || typeof ds !== 'object') return null;
  const num = v => (typeof v === 'number' && isFinite(v)) ? v : null;
  const els = ['fire', 'cold', 'lightning', 'chaos'];
  const resists = {}, resistMax = {}, overcap = {}, capped = {};
  for (const el of els) {
    const r = num(ds[el + 'Resistance']), m = num(ds[el + 'ResistanceMax']), o = num(ds[el + 'ResistanceOverCap']);
    if (r != null) { resists[el] = r; capped[el] = r >= 75; }
    if (m != null) resistMax[el] = m;
    if (o != null) overcap[el] = o;
  }
  const chaosImmune = Array.isArray(char.keystones) && char.keystones.some(k => k && k.name === 'Chaos Inoculation');
  return {
    ehp: num(ds.effectiveHealthPool), life: num(ds.life), es: num(ds.energyShield), ward: num(ds.ward),
    armour: num(ds.armour), resists, resistMax, overcap, capped, chaosImmune,
    biggestHit: num(ds.lowestMaximumHitTaken), evade: num(ds.evadeChance), block: num(ds.blockChance),
  };
}
// merge: PoB layer (keeps pdr/crit) with the richer defensiveStats layered over its non-null fields.
function mergeDefence(char) {
  const pob = parsePobDefence(char && char.pathOfBuildingExport);
  const ds = parseDefensiveStats(char);
  if (!pob && !ds) return null;
  const out = Object.assign({}, pob || {});
  if (ds) for (const k of Object.keys(ds)) { if (ds[k] != null) out[k] = ds[k]; }
  return out;
}
```

Extend `module.exports` (cjs:843) to add `parseDefensiveStats, mergeDefence`:

```js
module.exports = { weaponFamily, metaWeaponFamily, charWeaponFamily, convert, qa, gemMapFromLua, slugMapFromTree, parsePobDefence, parseDefensiveStats, mergeDefence, variantIsDistinct, coverageOk, slugify, ASCENDANCY_CODES };
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test tools/test-build-from-ninja.cjs`
Expected: PASS (all three new tests green; existing tests still green).

- [ ] **Step 5: Commit**

```bash
git add tools/build-from-ninja.cjs tools/test-build-from-ninja.cjs
git commit -m "feat(reconstructor): parseDefensiveStats + mergeDefence (own-build EHP/resists, capped>=75, chaos immunity)"
```

---

### Task 2: `mainSkillSupportCount(char, gem)`

**Files:**
- Modify: `tools/build-from-ninja.cjs` (add after `mergeDefence`; extend `module.exports`)
- Test: `tools/test-build-from-ninja.cjs`

**Interfaces:**
- Produces: `mainSkillSupportCount(char, gem) -> integer` — the support-gem count of the **highest-DPS** active skill group (the same group `convert` names as the main skill via `bestDps`). `0` when no resolvable active skill. `gem` is the name→id map (`gem[gemName] = "Metadata/Items/Gems/SkillGem…"`).

- [ ] **Step 1: Write the failing test**

```js
test('mainSkillSupportCount counts supports on the highest-DPS active group', () => {
  const gem = { Spark: 'Metadata/Items/Gems/SkillGemSpark', Comet: 'Metadata/Items/Gems/SkillGemComet',
    A: 'Metadata/Items/Gems/SupportGemA', B: 'Metadata/Items/Gems/SupportGemB',
    C: 'Metadata/Items/Gems/SupportGemC', D: 'Metadata/Items/Gems/SupportGemD' };
  const char = { skills: [
    { dps: [{ dps: 100 }], allGems: [{ name: 'Spark' }, { name: 'A' }, { name: 'B' }] },         // lower dps, 2 supports
    { dps: [{ dps: 900 }], allGems: [{ name: 'Comet' }, { name: 'A' }, { name: 'B' }, { name: 'C' }, { name: 'D' }] }, // main, 4 supports
  ] };
  assert.equal(T.mainSkillSupportCount(char, gem), 4);
  assert.equal(T.mainSkillSupportCount({ skills: [] }, gem), 0);
  assert.equal(T.mainSkillSupportCount(null, gem), 0);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test tools/test-build-from-ninja.cjs`
Expected: FAIL — `T.mainSkillSupportCount is not a function`.

- [ ] **Step 3: Implement (mirrors the `convert` bestDps loop, cjs:228-247)**

```js
// support count of the main (highest-DPS) active skill group — mirrors convert()'s main-skill pick.
function mainSkillSupportCount(char, gem) {
  let best = -1, bestSup = 0;
  ((char && char.skills) || []).forEach(group => {
    const gems = ((group.allGems) || []).map(g => ({ name: g.name, id: gem && gem[g.name] })).filter(g => g.id);
    const active = gems.find(g => /\/SkillGem/i.test(g.id));
    if (!active || /PlayerDefault/i.test(active.id)) return;
    const supports = gems.filter(g => g !== active && /\/SupportGem/i.test(g.id));
    const dps = Array.isArray(group.dps) ? Math.max(0, ...group.dps.map(d => Number(d && d.dps) || 0)) : (Number(group.dps) || 0);
    if (dps > best) { best = dps; bestSup = supports.length; }
  });
  return best < 0 ? 0 : bestSup;
}
```

Add `mainSkillSupportCount` to `module.exports`.

- [ ] **Step 4: Run to verify it passes**

Run: `node --test tools/test-build-from-ninja.cjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/build-from-ninja.cjs tools/test-build-from-ninja.cjs
git commit -m "feat(reconstructor): mainSkillSupportCount (links on the highest-DPS skill group)"
```

---

### Task 3: Soundness checks in `qa()` → `report.quality`

**Files:**
- Modify: `tools/build-from-ninja.cjs` — `qa()` signature + body (:282), `buildOne` call (:578)
- Test: `tools/test-build-from-ninja.cjs`

**Interfaces:**
- Consumes: `parseDefensiveStats`, `mainSkillSupportCount` (Tasks 1-2).
- Produces: `qa(build, char, { slug, tree, baseItems, md, weaponClass, gem })` now returns an additional `quality` field: `{ resistsCapped, ascendancyPoints, fullyAscended, mainSkillSupports, mainSkillLinked, snapshotUtc }`. `resistsCapped = capped.fire && capped.cold && capped.lightning && (capped.chaos || chaosImmune)`.

- [ ] **Step 1: Write the failing test**

```js
test('qa returns a soundness quality verdict; uncapped resist is NOT marked capped', () => {
  const gem = { Comet: 'Metadata/Items/Gems/SkillGemComet', A: 'Metadata/Items/Gems/SupportGemA',
    B: 'Metadata/Items/Gems/SupportGemB', C: 'Metadata/Items/Gems/SupportGemC' };
  const char = {
    level: 95, updatedUtc: '2026-06-19T07:23:51Z',
    passiveCounts: { ascendancy: 8 },
    defensiveStats: { effectiveHealthPool: 50000,
      fireResistance: 75, fireResistanceMax: 75, coldResistance: 75, coldResistanceMax: 75,
      lightningResistance: 60, lightningResistanceMax: 75, chaosResistance: 30, chaosResistanceMax: 75 },
    skills: [{ dps: [{ dps: 500 }], allGems: [{ name: 'Comet' }, { name: 'A' }, { name: 'B' }, { name: 'C' }] }],
  };
  // minimal build so qa's other checks don't throw; we only assert .quality here
  const build = { name: 'x', ascendancy: 'Sorceress1', passives: [{ id: 'AscendancySorceress1Start' }],
    skills: [{ id: 'Metadata/Items/Gems/SkillGemComet' }], inventory_slots: [] };
  const r = T.qa(build, char, { slug: {}, tree: null, baseItems: null, md: null, weaponClass: null, gem });
  assert.equal(r.quality.resistsCapped, false);          // lightning 60 < 75
  assert.equal(r.quality.fullyAscended, true);           // 8 points
  assert.equal(r.quality.mainSkillSupports, 3);
  assert.equal(r.quality.mainSkillLinked, true);
  assert.equal(r.quality.snapshotUtc, '2026-06-19T07:23:51Z');
});

test('qa resistsCapped honours Chaos Inoculation but flags a real chaos hole', () => {
  const cap = v => ({ fireResistance: 75, fireResistanceMax: 75, coldResistance: 75, coldResistanceMax: 75,
    lightningResistance: 75, lightningResistanceMax: 75, chaosResistance: v, chaosResistanceMax: 75, effectiveHealthPool: 1 });
  const build = { name: 'x', ascendancy: 'Witch1', passives: [], skills: [{ id: 'Metadata/Items/Gems/SkillGemX' }], inventory_slots: [] };
  const o = { slug: {}, tree: null, baseItems: null, md: null, weaponClass: null, gem: {} };
  assert.equal(T.qa(build, { defensiveStats: cap(0), passiveCounts: { ascendancy: 8 } }, o).quality.resistsCapped, false); // chaos 0, no CI
  assert.equal(T.qa(build, { defensiveStats: cap(0), passiveCounts: { ascendancy: 8 }, keystones: [{ name: 'Chaos Inoculation' }] }, o).quality.resistsCapped, true);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test tools/test-build-from-ninja.cjs`
Expected: FAIL — `Cannot read properties of undefined (reading 'resistsCapped')` (no `quality` on the report yet).

- [ ] **Step 3: Add the checks to `qa()`**

Change the signature (cjs:282) to include `gem`:

```js
function qa(build, char, { slug, tree, baseItems, md, weaponClass, gem }) {
```

Just before the existing `return { ok: ... }` (cjs:367), insert:

```js
  // ---- soundness signals (warn-level; never hard-fail a real ladder build) ----
  const def = parseDefensiveStats(char);
  const cap = (def && def.capped) || {};
  const resistsCapped = !!(def && cap.fire && cap.cold && cap.lightning && (cap.chaos || def.chaosImmune));
  if (def && !resistsCapped) warn('one or more resistances below the 75% cap');
  const ascendancyPoints = (char.passiveCounts && char.passiveCounts.ascendancy) || 0;
  const fullyAscended = ascendancyPoints >= 8;
  if (!fullyAscended) warn(`only ${ascendancyPoints}/8 ascendancy points`);
  const mainSkillSupports = mainSkillSupportCount(char, gem);
  const mainSkillLinked = mainSkillSupports >= 3;
  if (!mainSkillLinked) warn(`main skill has ${mainSkillSupports} support(s) (<3)`);
```

Add `quality` to the return object (cjs:367):

```js
  return { ok: !issues.some(i => i.sev === 'fail'), issues,
    stats: { sharedUnique, ws1: ws1.length, ws2: ws2.length, ascUnique, skills: build.skills.length, items: build.inventory_slots.length },
    quality: { resistsCapped, ascendancyPoints, fullyAscended, mainSkillSupports, mainSkillLinked, snapshotUtc: char.updatedUtc || null } };
```

Update the `buildOne` qa call (cjs:578) to thread `gem`:

```js
  const report = qa(build, char, { slug: slugMap, tree, baseItems, md, weaponClass, gem });
```

- [ ] **Step 4: Run to verify it passes**

Run: `node --test tools/test-build-from-ninja.cjs`
Expected: PASS (both new tests + existing suite green).

- [ ] **Step 5: Commit**

```bash
git add tools/build-from-ninja.cjs tools/test-build-from-ninja.cjs
git commit -m "feat(reconstructor): qa() emits an honest soundness verdict (capped/ascended/linked)"
```

---

### Task 4: Soundness-first selection (`sortBySoundness`)

**Files:**
- Modify: `tools/build-from-ninja.cjs` — new helper + selection block (:722-724)
- Test: `tools/test-build-from-ninja.cjs`

**Interfaces:**
- Consumes: `parseDefensiveStats` (Task 1).
- Produces: `sortBySoundness(cands)` — sorts the candidate array **in place** (and returns it) by `[allResistsCapped, fullyAscended, balance]` descending, where `balance = min(ehp/maxE, dps/maxD)` and `ehp` is the real `effectiveHealthPool` (fallback `cand.ehp`). Each candidate is `{ char, ehp, dps, account, name }`.

- [ ] **Step 1: Write the failing test**

```js
test('sortBySoundness puts the capped+ascended build first even at lower balance', () => {
  const capped = { passiveCounts: { ascendancy: 8 }, defensiveStats: {
    effectiveHealthPool: 30000, fireResistance: 75, fireResistanceMax: 75, coldResistance: 75, coldResistanceMax: 75,
    lightningResistance: 75, lightningResistanceMax: 75, chaosResistance: 75, chaosResistanceMax: 75 } };
  const glassUncapped = { passiveCounts: { ascendancy: 8 }, defensiveStats: {
    effectiveHealthPool: 90000, fireResistance: 40, fireResistanceMax: 75, coldResistance: 75, coldResistanceMax: 75,
    lightningResistance: 75, lightningResistanceMax: 75, chaosResistance: 75, chaosResistanceMax: 75 } };
  const cands = [
    { name: 'glass', char: glassUncapped, ehp: 90000, dps: 9000 },   // higher balance, uncapped fire
    { name: 'tank', char: capped, ehp: 30000, dps: 8000 },           // lower balance, fully capped
  ];
  T.sortBySoundness(cands);
  assert.equal(cands[0].name, 'tank');     // capped wins the preorder
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test tools/test-build-from-ninja.cjs`
Expected: FAIL — `T.sortBySoundness is not a function`.

- [ ] **Step 3: Implement the helper and wire it in**

Add near the other helpers (e.g. after `mainSkillSupportCount`):

```js
// prefer the soundest REAL build: capped resistances, then fully ascended, then EHP/DPS balance.
// Sorts in place so cands[0] is the featured pick and cands.slice(1) feeds the variant loop.
function sortBySoundness(cands) {
  const info = cands.map(p => {
    const def = parseDefensiveStats(p.char), cap = (def && def.capped) || {};
    const capped = !!(def && cap.fire && cap.cold && cap.lightning && (cap.chaos || def.chaosImmune));
    const ascended = ((p.char && p.char.passiveCounts && p.char.passiveCounts.ascendancy) || 0) >= 8;
    const ehp = (def && def.ehp) || p.ehp || 0;
    return { p, capped, ascended, ehp, dps: p.dps || 0 };
  });
  const maxE = Math.max(1, ...info.map(x => x.ehp)), maxD = Math.max(1, ...info.map(x => x.dps));
  info.forEach(x => { x.balance = Math.min(x.ehp / maxE, x.dps / maxD); });
  info.sort((a, b) => (b.capped - a.capped) || (b.ascended - a.ascended) || (b.balance - a.balance));
  cands.length = 0; info.forEach(x => cands.push(x.p));
  return cands;
}
```

Add `sortBySoundness` to `module.exports`. Then replace the inline scorer (cjs:722-723):

```js
          const maxE = Math.max(1, ...cands.map(p => p.ehp || 0)), maxD = Math.max(1, ...cands.map(p => p.dps || 0));
          cands.sort((a, b) => Math.min((b.ehp || 0) / maxE, (b.dps || 0) / maxD) - Math.min((a.ehp || 0) / maxE, (a.dps || 0) / maxD));
```

with:

```js
          sortBySoundness(cands);   // capped resists, then fully ascended, then EHP/DPS balance — cands[0] is featured
```

- [ ] **Step 4: Run to verify it passes**

Run: `node --test tools/test-build-from-ninja.cjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/build-from-ninja.cjs tools/test-build-from-ninja.cjs
git commit -m "feat(reconstructor): select the soundest real build (capped > ascended > balance)"
```

---

### Task 5: Persist the new verdict + own-defence (primary & variants)

**Files:**
- Modify: `tools/build-from-ninja.cjs` — primary persist (:732-741), variant persist (:761-768)

**Interfaces:**
- Consumes: `mergeDefence` (Task 1), `report.quality` (Task 3), `cands` (Task 4).
- Produces: persisted `meta.byAsc[slug].build.defence` = `mergeDefence(char)` (now carries `resistMax/overcap/capped/chaosImmune/biggestHit/armour`); `…build.quality` gains `selectedFrom` + the six `report.quality` fields; each variant's `defence` = `mergeDefence(cand.char)` plus `snapshotUtc`.

- [ ] **Step 1: Replace the primary persistence block (cjs:732-741)**

```js
              meta.byAsc[slug].build = { passives: build.passives.length, skills: report.stats.skills, items: report.stats.items,
                defence: mergeDefence(char),
                quality: {
                  level: char.level || null,
                  sample: pulled.length,
                  selectedFrom: cands.length,
                  onMetaWeapon: metaFam ? onMetaWeapon(char) : null,
                  gemsValid: !report.issues.some(i => i.sev === 'fail' && /BaseItemTypes/.test(i.m)),
                  treeConnected: !report.issues.some(i => /orphan/.test(i.m)),
                  warnings: report.issues.filter(i => i.sev === 'warn').length,
                  resistsCapped: report.quality.resistsCapped,
                  ascendancyPoints: report.quality.ascendancyPoints,
                  fullyAscended: report.quality.fullyAscended,
                  mainSkillSupports: report.quality.mainSkillSupports,
                  mainSkillLinked: report.quality.mainSkillLinked,
                  snapshotUtc: report.quality.snapshotUtc,
                } };
```

- [ ] **Step 2: Update the variant record (cjs:761-768)**

Change the variant's `defence` source and add `snapshotUtc`:

```js
                  variants.push({
                    slug: vslug, name: r.build.name,
                    source: { account: cand.account, name: cand.name, level: cand.char.level || null },
                    ehp: cand.ehp || null, dps: cand.dps || null,
                    defence: mergeDefence(cand.char),
                    snapshotUtc: cand.char.updatedUtc || null,
                    pob: !!cand.char.pathOfBuildingExport,
                    skillSetups: readableSkills(cand.char).slice(0, 4),
                  });
```

- [ ] **Step 3: Verify the wiring by reconstructing one cached character**

Run (proves `buildOne` → persisted shape end-to-end without a full regen):

```bash
node -e '
const T=require("./tools/build-from-ninja.cjs"), fs=require("fs"), path=require("path");
const dir="tools/.cache";
const f=fs.readdirSync(dir).find(n=>/^c-.*\.json$/.test(n));
const char=JSON.parse(fs.readFileSync(path.join(dir,f),"utf8"));
const d=T.mergeDefence(char);
console.log("defence has capped?", !!(d&&d.capped), "biggestHit?", d&&d.biggestHit!=null, "resistMax?", !!(d&&d.resistMax));
'
```

Expected: `defence has capped? true biggestHit? true resistMax? true` (a cached char carries `defensiveStats`).

- [ ] **Step 4: Run the full suites for regression**

Run: `node --test tools/test-build-from-ninja.cjs`
Expected: PASS (no regression; existing weapon/gem/variant tests still green).

- [ ] **Step 5: Commit**

```bash
git add tools/build-from-ninja.cjs
git commit -m "feat(reconstructor): persist own-defence + soundness verdict (primary + variants)"
```

---

### Task 6: Front end — "Reconstruction checks" chip (`qualityChip` + CSS)

**Files:**
- Modify: `index.html` — `qualityChip` (:2007); add `.bvq.warn` / `.bvq.note` / `.bvq-asof` CSS next to the existing `.bvq.ok` rule (search `.bvq.ok` in the `<style>` block)

**Interfaces:**
- Consumes: `md.build.quality` (`resistsCapped, fullyAscended, ascendancyPoints, mainSkillSupports, mainSkillLinked, onMetaWeapon, level, snapshotUtc`), `md.build.defence` (`resists`, `capped`, `chaosImmune`). Existing helpers `esc`, `relTime`.

> No JS unit harness exists for `index.html`; this task is preview-verified. The honesty invariant (never green-check a hole) is already enforced and unit-tested in the pipeline (Task 3 `resistsCapped`), so the chip only renders booleans.

- [ ] **Step 1: Replace `qualityChip` (index.html:2007-2016)**

```js
function qualityChip(md){
  const q = md.build && md.build.quality;
  if (!q) return "";
  const d = (md.build && md.build.defence) || {};
  const res = d.resists || {}, cap = d.capped || {};
  const ok = [], warn = [], note = [];
  if (q.onMetaWeapon === true) ok.push("runs the dominant meta weapon");
  else if (q.onMetaWeapon === null) note.push("no single dominant weapon — any popular weapon is representative");
  if (q.gemsValid) ok.push("all gems resolve in-game");
  if (q.resistsCapped){
    const vals = ["fire","cold","lightning"].map(k=>res[k]).filter(v=>v!=null);
    ok.push("all resistances capped"+(vals.length?` (${vals.join("/")}%)`:""));
  } else {
    ["fire","cold","lightning"].forEach(k=>{ if (cap[k]===false && res[k]!=null) warn.push(`${k[0].toUpperCase()+k.slice(1)} resistance ${res[k]}% — cap it to 75% before you map`); });
    if (cap.chaos===false && res.chaos!=null && !d.chaosImmune) warn.push(`Chaos resistance ${res.chaos}% — uncapped (no Chaos Inoculation)`);
  }
  if (q.fullyAscended) ok.push("fully ascended (8 points)");
  else if (q.ascendancyPoints!=null) warn.push(`only ${q.ascendancyPoints}/8 ascendancy points allocated`);
  if (q.mainSkillLinked) ok.push(`main skill fully linked (${q.mainSkillSupports} supports)`);
  else if (q.mainSkillSupports!=null) warn.push(`main skill has ${q.mainSkillSupports} support${q.mainSkillSupports===1?"":"s"} (under 3)`);
  if (q.level) ok.push(`level&nbsp;${q.level} ladder character`);
  if (!ok.length && !warn.length && !note.length) return "";
  const asOf = q.snapshotUtc ? `<span class="bvq-asof">as of ${esc(relTime(q.snapshotUtc))}</span>` : "";
  return `<div class="bv-quality"><span class="bvq-h">Reconstruction checks</span>`
    + ok.map(t=>`<span class="bvq ok">✓ ${t}</span>`).join("")
    + warn.map(t=>`<span class="bvq warn">⚠ ${esc(t)}</span>`).join("")
    + note.map(t=>`<span class="bvq note">${esc(t)}</span>`).join("")
    + asOf + `</div>`;
}
```

- [ ] **Step 2: Add the CSS (immediately after the existing `.bvq.ok { … }` rule)**

```css
.bvq.warn{ color:var(--bone-dim); border-color:var(--hair-strong); background:rgba(200,162,74,.06); }
.bvq.note{ color:var(--muted); }
.bvq-asof{ color:var(--muted); font-size:9px; letter-spacing:.05em; align-self:center; margin-left:4px; }
```

- [ ] **Step 3: Verify in the browser preview**

Start the server (`preview_start`, or `python -m http.server 8099`), open a build with a known uncapped resist (the Gemling/chaos or a sub-75 elemental case after Task 11's regen; before regen, the old chip data still renders without ⚠). Confirm: the header reads "Reconstruction checks"; an uncapped build shows a `⚠` line with the value and "cap it to 75% before you map", NOT a green "all resistances capped"; the "as of …" stamp appears. Check `preview_console_logs` for 0 errors.

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat(ui): honest Reconstruction-checks chip (capped/ascended/linked, ⚠ on gaps, chaos line)"
```

---

### Task 7: Front end — defence pills (capped from data, max, headroom, biggest hit)

**Files:**
- Modify: `index.html` — `defenceHTML` / `resPill` (:2019-2040)

**Interfaces:**
- Consumes: `md.build.defence` now with `capped`, `resistMax`, `overcap`, `biggestHit`. Falls back to `v>=75` when `capped` is absent (PoB-only builds).

- [ ] **Step 1: Replace the resist-pill + extras logic in `defenceHTML` (index.html:2022-2034)**

Replace the `const res = …` line and the `resPill` definition (2022-2023), and the `extra` block + `resRow` (2029-2034), with:

```js
  const res = d.resists || {}, cap = d.capped || {}, rmax = d.resistMax || {}, over = d.overcap || {};
  const resPill = (lab,v,css,el) => {
    if (v==null) return "";
    const isCap = (cap[el]!=null) ? !!cap[el] : (v>=75);   // data-driven; PoB-only fallback to >=75
    const maxTxt = (rmax[el]!=null && rmax[el]!==75) ? `/${rmax[el]}` : "";
    const title = (isCap && over[el]===0) ? ' title="capped, no headroom"' : "";
    return `<span class="def-res ${css}${isCap?' capped':(v<0?' neg':'')}"${title}>${lab} <b>${v}%${maxTxt}</b></span>`;
  };
  const pools=[];
  if (d.life!=null && d.life>1) pools.push(`Life <b>${fmt(d.life)}</b>`);
  if (d.es!=null && d.es>0) pools.push(`ES <b>${fmt(d.es)}</b>`);
  if (d.ward!=null && d.ward>0) pools.push(`Ward <b>${fmt(d.ward)}</b>`);
  if (!pools.length && d.ehp!=null) pools.push(`EHP <b>${fmt(d.ehp)}</b>`);
  const extra=[];
  if (d.biggestHit) extra.push(`Largest hit survived ${fmt(d.biggestHit)}`);
  if (d.evade) extra.push(`Evade ${d.evade}%`);
  if (d.block) extra.push(`Block ${d.block}%`);
  if (d.pdr) extra.push(`Phys&nbsp;reduc ${d.pdr}%`);
  if (d.crit!=null) extra.push(`Crit ${d.crit}%`);
  const resRow = resPill('Fire',res.fire,'fire','fire')+resPill('Cold',res.cold,'cold','cold')+resPill('Lightning',res.lightning,'lit','lightning')+resPill('Chaos',res.chaos,'chaos','chaos');
```

(Leave the surrounding `const d = …`, the `if (!d) return "";`, and the final `return` template at 2035-2040 unchanged.)

- [ ] **Step 2: Verify in the preview**

Reload a build view. Confirm: a capped resist shows the `capped` style; an uncapped one does not; a penalised cap (e.g. 74/74 after regen) shows "74%/74" and is NOT marked capped; "Largest hit survived N" appears. 0 console errors.

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat(ui): defence pills use real capped(>=75)+max+headroom and show largest hit survived"
```

---

### Task 8: Front end — stat panel own-EHP headline, median secondary, provenance, build-age

**Files:**
- Modify: `index.html` — `metaDetailHTML` stats + src (:2176-2182)

**Interfaces:**
- Consumes: `md.build.defence.ehp` (own EHP, with `?? md.stats.ehp` fallback), `md.build.defence.biggestHit`, `md.build.quality.selectedFrom`/`onMetaWeapon`, `md.stats.{ehp,dps,sample,level}`, `META.buildsUpdated` (falls back to `META.updated`).

- [ ] **Step 1: Replace the `stats` + `src` construction (index.html:2177-2181)**

```js
  const st = md.stats||{};
  const dfn = (md.build && md.build.defence) || {};
  const ownEhp = dfn.ehp!=null ? dfn.ehp : null;
  const headEhp = ownEhp!=null ? ownEhp : (st.ehp||null);
  const bits = [ st.level?`Level <b>${st.level}</b>`:null,
    headEhp?`EHP <b>${fmt(headEhp)}</b>`:null,
    dfn.biggestHit?`Largest hit survived <b>${fmt(dfn.biggestHit)}</b>`:null,
    st.dps?`DPS <b>~${fmt(st.dps)}</b>`:null ].filter(Boolean);
  const ss = md.stats && md.stats.sample;
  const medCaption = `median across ${ss?fmt(ss)+" sampled":"the sampled"} ${esc(md.asc)} characters`;
  const smp = ownEhp!=null
    ? `<span class="smp">EHP &amp; defences are this build's own; DPS is the ascendancy ${medCaption}</span>`
    : `<span class="smp">${medCaption}</span>`;
  const stats = bits.length ? `<div class="meta-stats">${bits.join("")}${smp}</div>` : "";
  const q = md.build && md.build.quality;
  const prov = (q && q.selectedFrom) ? ` · selected as the soundest of ${q.selectedFrom} level-85+ ladder characters${q.onMetaWeapon!==null?" running the dominant weapon":""}` : "";
  const bstamp = (META && META.buildsUpdated) || (META && META.updated) || null;
  const bstale = bstamp && (Date.now() - new Date(bstamp).getTime()) > 8*86400e3;
  const src = md.source ? `<div class="meta-src">Build reconstructed from public-ladder character <b>${esc(md.source.name)}</b> (${esc(md.source.account)})${md.source.level?`, level ${md.source.level}`:""}${prov} · <a href="https://poe.ninja/poe2/builds/${encodeURIComponent(META.league||"")}/character/${encodeURIComponent(md.source.account)}/${encodeURIComponent(md.source.name)}" target="_blank" rel="noopener noreferrer">view on poe.ninja ↗</a>${bstamp ? ` · reconstructed ${esc(relTime(bstamp))}${bstale?" (refresh overdue)":""}` : ""}</div>` : "";
```

(Leave the `return metaCoreGrid(md) + … + stats + src;` line unchanged.)

- [ ] **Step 2: Verify in the preview**

Reload several build views. Confirm: the headline EHP equals the build's own number (cross-check against the value in the Defences panel — they should match); the DPS shows a `~`; the caption reads "EHP & defences are this build's own; DPS is the ascendancy median across N…"; the provenance reads "selected as the soundest of N…"; the freshness reads "reconstructed … (refresh overdue)" only when `buildsUpdated` is >8 days old. Then open a **template-only** league/ascendancy (no `md.build`) — its EHP line must still render from the median with the plain median caption (fallback works). 0 console errors.

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat(ui): headline the build's own EHP + largest hit, soundest-of-N provenance, true build age"
```

---

### Task 9: Front end — The Counterpoise compare table (own EHP, real capped, relabel)

**Files:**
- Modify: `index.html` — `ascForCompare` (:2056-2057), `compareTableHTML` resRow (:2092-2094), EHP/DPS rows (:2108-2109), foot (:2122)

**Interfaces:**
- Consumes: `md.build.defence.ehp` (with `?? md.stats.ehp`), `c.def.capped`. The column view-model already carries `def = md.build.defence`, so `capped` rides along.

- [ ] **Step 1: Switch the compare EHP source (index.html:2056-2057)**

```js
    ehp: (md.build && md.build.defence && md.build.defence.ehp) != null ? md.build.defence.ehp : ((md.stats && md.stats.ehp) || d.ehp || null),
    dps: (md.stats && md.stats.dps) || null,
```

- [ ] **Step 2: Replace `resRow` to use real capped (index.html:2092-2094)**

```js
  const resRow = key => {
    const vals = cols.map(c => c.def && c.def.resists ? c.def.resists[key] : null);
    const mi = maxIdx(vals);
    const tds = cols.map((c,i) => {
      const v = vals[i];
      const isCap = (c.def && c.def.capped && c.def.capped[key]!=null) ? !!c.def.capped[key] : (v!=null && v>=75);
      return `<td class="${i===mi?'cmp-best':''}">${v==null?'—':`${v}%${isCap?' ✓':''}`}</td>`;
    }).join("");
    return `<tr><th scope="row">${key[0].toUpperCase()+key.slice(1)} res</th>${tds}</tr>`;
  };
```

- [ ] **Step 3: Relabel the EHP/DPS rows (index.html:2108-2109)**

```js
      ${numRow('EHP', cols.map(c=>c.ehp))}
      ${numRow('DPS', cols.map(c=>c.dps), v=>`~${fmt(v)}`)}
```

- [ ] **Step 4: Update the foot to be honest about the mix (index.html:2122)**

```js
  <p class="cmp-foot">EHP &amp; defences are each featured build's own (from its Path of Building export); DPS is the ascendancy median (~). Same ladder data as the ledger — nothing fabricated. The accent marks the higher number in a row, not a better build.</p>`;
```

- [ ] **Step 5: Verify in the preview**

Open The Counterpoise, pick two ascendancies. Confirm: the EHP row matches each build panel's own EHP (not the old median); the row labels read "EHP"/"DPS" (no "Median"); a sub-75 resistance shows no ✓ while a capped one does; the foot text reflects the EHP-own / DPS-median split. 0 console errors.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "feat(ui): Counterpoise shows each build's own EHP + real capped marks (no median/75 contradiction)"
```

---

### Task 10: Front end — variant cards show honest capped marks

**Files:**
- Modify: `index.html` — `variantsHTML` resStr (:2148-2149)

**Interfaces:**
- Consumes: `v.defence.resists`, `v.defence.capped` (persisted in Task 5).

- [ ] **Step 1: Replace the variant resist string (index.html:2148-2149)**

```js
    const res = v.defence && v.defence.resists, cap = v.defence && v.defence.capped;
    const resStr = res ? `${["fire","cold","lightning","chaos"].map(k=>res[k]==null?"–":`${res[k]}${(cap&&cap[k])?"✓":""}`).join("/")} res` : "";
```

- [ ] **Step 2: Verify in the preview**

Open a build with variants (after Task 11's regen). Confirm each variant's resist string shows a ✓ on capped elements and none on uncapped — consistent with the primary panel. 0 console errors.

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat(ui): variant cards mark capped resistances (parity with the primary build)"
```

---

### Task 11: Regenerate `meta-detail.json` from cache + full verification

**Files:**
- Regenerate (committed outputs): `meta-detail.json`, `effects.json`, `builds/*.build`, `builds/*.pob`, `builds/index.json`

> Local regen uses `--cache-only` (zero network — the local IP gets throttled by poe.ninja). It replays the cached characters through the new selection + persistence, so the committed data exercises the feature end-to-end. The weekly CI job (`.github/workflows/builds.yml`) later refreshes from the live ladder; until it runs, the cache-only data is real, QA'd, and additive-safe.

- [ ] **Step 1: Regenerate from the cache**

Run: `node tools/build-from-ninja.cjs --enumerate --cache-only`
Expected: it prints per-ascendancy `+ <asc> … build <- <name>` lines and `N builds · meta-detail.json for 23 ascendancies · manifest (…)` with no coverage refusal (cache-only is exempt).

- [ ] **Step 2: Assert the new fields landed (and the disclosure path is real)**

Run:

```bash
node -e '
const md=require("./meta-detail.json").byAsc; let withCap=0, uncapped=[];
for (const [slug,m] of Object.entries(md)){
  const q=m.build&&m.build.quality, d=m.build&&m.build.defence;
  if (q && "resistsCapped" in q){ withCap++; if (q.resistsCapped===false) uncapped.push(slug); }
  if (q && d){ if (typeof q.selectedFrom!=="number") throw new Error("no selectedFrom: "+slug);
    if (d.capped===undefined && d!==null) console.log("note: no capped (PoB fallback):",slug); }
}
console.log("builds with resistsCapped field:",withCap);
console.log("builds disclosing an uncapped resist:",uncapped.join(", ")||"(none)");
'
```

Expected: most/all 23 builds carry `resistsCapped`; the uncapped list is non-empty (proves the honest ⚠ path is exercised, e.g. a chaos or sub-75 case). If the list is empty, that is acceptable only if every cached featured char is genuinely fully capped — note it and continue.

- [ ] **Step 3: Run every test suite**

Run: `node --test tools/test-build-from-ninja.cjs && python scripts/test_distill.py && python scripts/buildfile.py --selftest`
Expected: all PASS. (If `python` is unavailable locally, note it — the Python suites run in CI `test.yml`; the Node suite is the gate for this workstream.)

- [ ] **Step 4: Full preview pass across the render sites**

Serve and verify on ≥3 ascendancies that the chip, defence pills, stat-panel headline, Counterpoise, and variants all agree for the same slug (own EHP matches across panel + compare; capped ✓/⚠ identical across chip + pills + compare + variants); a disclosed build shows the ⚠ + fix, never a green "all capped"; a template-only ascendancy still shows a (median, labelled) EHP line. Capture `preview_screenshot` of one disclosed build for the PR. 0 console errors.

- [ ] **Step 5: Commit the regenerated data**

```bash
git add meta-detail.json effects.json builds
git commit -m "data(earned-confidence): regenerate from cache — own-defence + soundness verdict + soundest picks"
```

---

## Self-Review

**Spec coverage** (each spec section → task):
- §Data source `parseDefensiveStats` + merge → **Task 1**. `mainSkillSupportCount` → **Task 2**.
- §Quality checks in `qa()` → **Task 3**. §Selection prefer-then-disclose → **Task 4**.
- §Persisted schema (primary + variants) → **Task 5**.
- §Front end #2 chip → **Task 6**; #3 defence pills → **Task 7**; #1 headline EHP + #5 freshness + #6 provenance → **Task 8**; #4 Counterpoise → **Task 9**; #5 variants → **Task 10**.
- §DPS handling (`~`, median labelled) → Tasks 8, 9. §Honesty guardrails (capped>=75, chaos, never green-check) → Tasks 1, 3, 6 (enforced in data, rendered in UI). §Rollout/`--cache-only` regen + suites → **Task 11**.
- §Explicitly unchanged (ledger sort, quiz) → no task touches `statOf`/`rxScore` (verified by omission; constraint stated in Global Constraints).

**Placeholder scan:** none — every code step shows complete code; every run step shows the command + expected output.

**Type consistency:** `quality.{resistsCapped,ascendancyPoints,fullyAscended,mainSkillSupports,mainSkillLinked,snapshotUtc,selectedFrom}` defined in Tasks 3/5 and consumed in Tasks 6/8 with identical names; `defence.{capped,resistMax,overcap,biggestHit,chaosImmune}` defined in Task 1, persisted in Task 5, consumed in Tasks 6/7/9/10 with identical names; `sortBySoundness`/`mergeDefence`/`parseDefensiveStats`/`mainSkillSupportCount` exported in Tasks 1-4 and used in Task 5 and tests. Consistent.

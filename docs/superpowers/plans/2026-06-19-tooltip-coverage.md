# Effect-tooltip Coverage Patch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise in-site effect-tooltip coverage from ~68% to ~95% by harvesting unique jewels/flasks, including passive keystones, and mapping anointments to notables — with no new data source.

**Architecture:** Three small changes to the shipped `tools/effects.cjs` pure functions + their pipeline wiring, plus a front-end `KIND_TO_TYPE`/`entityCard` change, plus a committed coverage-audit tool. Everything derives from data already pulled (the GGG tree export + the poe.ninja sample's items, **jewels, and flasks**).

**Tech Stack:** Node 22 (CommonJS `.cjs`, `node --test`), vanilla browser JS/CSS in a single `index.html`.

## Global Constraints

- **Strictly additive / fail-safe:** an unmatched name, a malformed entry, or a missing `char.jewels`/`char.flasks` array → the existing "look it up ↗" link. The effects build stays inside the existing `try/catch` so a failure can never abort the `builds/`+`meta-detail.json`+`effects.json` commit.
- **No new data source, no scraping, no new dependency.**
- **`normKey` (effects.cjs) and `normKeyFE` (index.html) must stay byte-identical** in behavior.
- **Keep `effects.json` lean:** include notable/keystone nodes + only the "other" tree nodes the meta references (never all ~3,300 small named nodes).
- **All dynamic front-end text is `esc()`-escaped.**
- `effects.json` lives at repo ROOT.

---

### Task 1: Coverage-audit tool (baseline)

**Files:**
- Create: `tools/coverage-audit.cjs`

**Interfaces:**
- Produces: a runnable script `node tools/coverage-audit.cjs` printing per-category resolve rates. No exports.

- [ ] **Step 1: Create the tool**

Create `tools/coverage-audit.cjs`:

```js
'use strict';
// Audit which entities rendered by metaCol() resolve to an effects.json card vs fall back
// to the lookup link. Replicates the front-end normKey + effectFor + KIND_TO_TYPE.
// Run: node tools/coverage-audit.cjs
const fs = require('fs');
const path = require('path');
const REPO = path.resolve(__dirname, '..');
const EFF = JSON.parse(fs.readFileSync(path.join(REPO, 'effects.json'), 'utf8'));
const MD = JSON.parse(fs.readFileSync(path.join(REPO, 'meta-detail.json'), 'utf8'));
const cleanMarkup = s => String(s == null ? '' : s).replace(/\[[^\]|]+\|([^\]]+)\]/g, '$1').replace(/\[([^\]]+)\]/g, '$1').replace(/\s+/g, ' ').trim();
const normKey = s => cleanMarkup(s).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
const KIND_TO_TYPE = { 'Skill gem': 'gems', 'Support gem': 'gems', 'Passive notable': 'notables', 'Anointment': 'notables', 'Unique item': 'uniques', 'Rune / soul core': 'runes' };
function effectFor(kind, name) {
  const type = KIND_TO_TYPE[kind]; const map = type && EFF[type]; if (!map) return false;
  const k = normKey(name); if (map[k]) return true;
  if (type === 'runes') { const k2 = k.replace(/^(lesser|greater|grand|perfect|superior|exceptional)\s+/, ''); if (k2 !== k && map[k2]) return true; }
  return false;
}
const COLS = [['skills', 'Skill gem'], ['supports', 'Support gem'], ['notables', 'Passive notable'], ['uniques', 'Unique item'], ['runes', 'Rune / soul core'], ['anointments', 'Anointment'], ['weapons', 'Weapon base']];
const cats = {}; for (const [, kind] of COLS) cats[kind] = new Map();
for (const md of [MD.global, ...Object.values(MD.byAsc || {})].filter(Boolean)) {
  for (const [col, kind] of COLS) for (const x of (md[col] || [])) {
    if (!x || !x.name) continue;
    const k = normKey(x.name), hit = effectFor(kind, x.name), prev = cats[kind].get(k);
    if (!prev) cats[kind].set(k, { name: x.name, hit, maxpct: x.pct || 0 });
    else { prev.maxpct = Math.max(prev.maxpct, x.pct || 0); prev.hit = prev.hit || hit; }
  }
}
let totEnt = 0, totHit = 0;
console.log('=== TOOLTIP COVERAGE AUDIT (deduped across all ascendancies + global) ===\n');
for (const [col, kind] of COLS) {
  const arr = [...cats[kind].values()], hits = arr.filter(e => e.hit).length;
  totEnt += arr.length; totHit += hits;
  console.log(`${kind.padEnd(16)} (md.${col.padEnd(11)}): ${String(hits).padStart(4)}/${String(arr.length).padStart(4)}  (${arr.length ? Math.round(hits / arr.length * 100) : 0}%)`);
  const misses = arr.filter(e => !e.hit).sort((a, b) => b.maxpct - a.maxpct).slice(0, 10).map(m => `${m.name} [${m.maxpct}%]`);
  if (misses.length) console.log('   top misses: ' + misses.join(' · '));
}
console.log(`\nOVERALL: ${totHit}/${totEnt} resolve (${Math.round(totHit / totEnt * 100)}%)`);
```

- [ ] **Step 2: Run it to capture the baseline**

Run: `node tools/coverage-audit.cjs`
Expected: prints per-category rates and an `OVERALL: …` line in the ~70% range (uniques ~54%, notables ~83%, anointments partial). This is the BEFORE baseline; later tasks raise it.

- [ ] **Step 3: Commit**

```bash
git add tools/coverage-audit.cjs
git commit -m "Tools: coverage-audit for effect-tooltip resolve rates"
```

---

### Task 2: `collectFromChar` — harvest jewels + flasks, filter non-uniques

**Files:**
- Modify: `tools/effects.cjs:52` and `tools/effects.cjs:66`
- Test: `tools/test-effects.cjs`

**Interfaces:**
- Consumes: `normKey`, `cleanMarkup`.
- Produces: `collectFromChar(char, acc)` now also reads `char.jewels` and `char.flasks` for the unique (and rune) harvest, and skips frameType-3 items whose name starts with `Normal `/`Magic `/`Rare `.

- [ ] **Step 1: Write the failing tests**

Append to `tools/test-effects.cjs`:

```js
test('collectFromChar harvests unique jewels and flasks, not just items', () => {
  const acc = { runes: {}, uniques: {}, gems: {} };
  const char = {
    items: [{ itemData: { inventoryId: 'Ring', frameType: 3, name: "Kalandra's Touch", baseType: 'Ring', explicitMods: ['Reflects opposite Ring'] } }],
    jewels: [{ itemData: { frameType: 3, name: 'From Nothing', baseType: 'Sapphire', explicitMods: ['Allocates a Jewel socket'], flavourText: ['x'] } }],
    flasks: [{ itemData: { frameType: 3, name: 'The Fall of the Axe', baseType: 'Silver Charm', implicitMods: ['Used when you are Slowed'], explicitMods: ['Grants Onslaught during effect'] } }],
    skills: [],
  };
  E.collectFromChar(char, acc);
  assert.ok(acc.uniques['kalandra s touch'], 'item unique still harvested');
  assert.ok(acc.uniques['from nothing'], 'jewel unique harvested');
  assert.strictEqual(acc.uniques['the fall of the axe'].base, 'Silver Charm', 'flask unique harvested');
  assert.deepStrictEqual(acc.uniques['the fall of the axe'].mods, ['Used when you are Slowed', 'Grants Onslaught during effect']);
});

test('collectFromChar skips frameType-3 items named Normal/Magic/Rare (meta noise)', () => {
  const acc = { runes: {}, uniques: {}, gems: {} };
  E.collectFromChar({ items: [{ itemData: { frameType: 3, name: 'Rare Amulet of Doom' } }], skills: [] }, acc);
  assert.strictEqual(acc.uniques['rare amulet of doom'], undefined);
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `node --test tools/test-effects.cjs`
Expected: the jewel/flask test FAILS (`acc.uniques['from nothing']` is undefined — jewels not read).

- [ ] **Step 3: Apply the implementation**

In `tools/effects.cjs`, replace the line (currently line 52):

```js
  for (const it of (char.items || [])) {
```

with:

```js
  // uniques live in items, but unique JEWELS are in char.jewels and unique FLASKS/charms
  // in char.flasks — same item shape. Harvest all three. (Jewels/flasks carry no socketed
  // runes, so the rune loop below is a harmless no-op for them.)
  for (const it of [].concat(char.items || [], char.jewels || [], char.flasks || [])) {
```

Then replace the unique guard (currently line 66):

```js
    if (d.frameType === 3 && d.name) {
```

with:

```js
    if (d.frameType === 3 && d.name && !/^(Normal|Magic|Rare) /.test(d.name)) {
```

- [ ] **Step 4: Run to verify all pass**

Run: `node --test tools/test-effects.cjs`
Expected: all tests PASS (the 7 existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add tools/effects.cjs tools/test-effects.cjs
git commit -m "Effects: harvest unique jewels + flasks, filter meta noise"
```

---

### Task 3: `notablesFromTree(tree, wanted)` + `wantedFromMeta(meta)`

**Files:**
- Modify: `tools/effects.cjs:19-30` (replace `notablesFromTree`, add `wantedFromMeta`) and `tools/effects.cjs:113` (exports)
- Test: `tools/test-effects.cjs`

**Interfaces:**
- Consumes: `normKey`, `cleanMarkup`.
- Produces:
  - `wantedFromMeta(meta): Set<string>` — normalized names from every `md.notables[].name` + `md.anointments[].name` across `meta.global` and `meta.byAsc`.
  - `notablesFromTree(tree, wanted): {[key]:{name,stats}}` — keeps a node when it has a `name` + non-empty `stats[]` and (`isNotable || isKeystone || wanted.has(normKey(name))`). `wanted` is optional (defaults to empty set → keystone-inclusive but no "other" nodes).

- [ ] **Step 1: Write the failing tests**

Append to `tools/test-effects.cjs`:

```js
test('notablesFromTree includes keystones + meta-referenced other nodes, excludes unreferenced others', () => {
  const tree = { nodes: {
    root: { out: [] },
    a: { isNotable: true, name: 'Gathering Winds', stats: ['Gain Tailwind on Skill use'] },
    k: { isKeystone: true, name: 'Chaos Inoculation', stats: ['Maximum Life becomes 1'] },
    o1: { name: 'Point Blank', stats: ['More damage at close range'] },
    o2: { name: 'Tiny Passive', stats: ['+10 to Strength'] },
  }};
  const out = E.notablesFromTree(tree, new Set([E.normKey('Point Blank')]));
  assert.ok(out['gathering winds'], 'notable kept');
  assert.ok(out['chaos inoculation'], 'keystone kept');
  assert.ok(out['point blank'], 'referenced other node kept');
  assert.strictEqual(out['tiny passive'], undefined, 'unreferenced other node dropped');
});

test('notablesFromTree without wanted still keeps notables and keystones', () => {
  const tree = { nodes: { k: { isKeystone: true, name: 'Blood Magic', stats: ['Removes all Mana'] }, o: { name: 'Nope', stats: ['x'] } } };
  const out = E.notablesFromTree(tree);
  assert.ok(out['blood magic']);
  assert.strictEqual(out['nope'], undefined);
});

test('wantedFromMeta collects normalized notable + anointment names from global and byAsc', () => {
  const meta = {
    global: { notables: [{ name: 'Point Blank' }], anointments: [{ name: 'Well of Power' }] },
    byAsc: { x: { notables: [{ name: 'Choice of Power' }], anointments: [] } },
  };
  const w = E.wantedFromMeta(meta);
  assert.ok(w.has('point blank') && w.has('well of power') && w.has('choice of power'));
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `node --test tools/test-effects.cjs`
Expected: FAIL — `E.wantedFromMeta is not a function`, and the keystone/other tests fail (current `notablesFromTree` only keeps `isNotable`).

- [ ] **Step 3: Apply the implementation**

In `tools/effects.cjs`, replace the whole `notablesFromTree` function (currently lines 19-30):

```js
function notablesFromTree(tree) {
  const out = {};
  const nodes = (tree && tree.nodes) || {};
  for (const [k, n] of Object.entries(nodes)) {
    if (k === 'root' || !n || !n.isNotable || !n.name) continue;
    if (!Array.isArray(n.stats) || !n.stats.length) continue;
    const key = normKey(n.name);
    if (out[key]) continue;
    out[key] = { name: cleanMarkup(n.name), stats: n.stats.map(cleanMarkup).filter(Boolean) };
  }
  return out;
}
```

with:

```js
// Names the meta actually references (notables + anointments, across all ascendancies +
// global), normalized. Used to pull in popular "other"-flagged tree nodes without bloat.
function wantedFromMeta(meta) {
  const out = new Set();
  if (!meta) return out;
  const add = md => { if (!md) return; for (const col of ['notables', 'anointments']) for (const x of (md[col] || [])) if (x && x.name) out.add(normKey(x.name)); };
  add(meta.global);
  for (const md of Object.values(meta.byAsc || {})) add(md);
  return out;
}

// Keep notables AND keystones, plus any named-with-stats node the meta references
// (popular "other"-flagged passives + anointments) — never the ~3,300 small named nodes.
function notablesFromTree(tree, wanted) {
  const want = wanted instanceof Set ? wanted : new Set();
  const out = {};
  const nodes = (tree && tree.nodes) || {};
  for (const [k, n] of Object.entries(nodes)) {
    if (k === 'root' || !n || !n.name) continue;
    if (!Array.isArray(n.stats) || !n.stats.length) continue;
    if (!(n.isNotable || n.isKeystone || want.has(normKey(n.name)))) continue;
    const key = normKey(n.name);
    if (out[key]) continue;
    out[key] = { name: cleanMarkup(n.name), stats: n.stats.map(cleanMarkup).filter(Boolean) };
  }
  return out;
}
```

Then update the exports line (currently line 113):

```js
module.exports = { normKey, cleanMarkup, notablesFromTree, gemInfoFromLua, collectFromChar, buildEffectsJson };
```

to:

```js
module.exports = { normKey, cleanMarkup, notablesFromTree, wantedFromMeta, gemInfoFromLua, collectFromChar, buildEffectsJson };
```

- [ ] **Step 4: Run to verify all pass**

Run: `node --test tools/test-effects.cjs`
Expected: all PASS (existing + 3 new). The existing `notablesFromTree keeps isNotable nodes…` test still passes (its tree has no keystone/other-referenced nodes).

- [ ] **Step 5: Commit**

```bash
git add tools/effects.cjs tools/test-effects.cjs
git commit -m "Effects: notablesFromTree keeps keystones + meta-referenced nodes; wantedFromMeta"
```

---

### Task 4: `buildEffectsJson` forwards `wanted`

**Files:**
- Modify: `tools/effects.cjs:109`
- Test: `tools/test-effects.cjs`

**Interfaces:**
- Consumes: `notablesFromTree`, `wantedFromMeta`.
- Produces: `buildEffectsJson(acc, opts)` now reads `opts.wanted` (a `Set`, optional) and forwards it to `notablesFromTree`.

- [ ] **Step 1: Write the failing test**

Append to `tools/test-effects.cjs`:

```js
test('buildEffectsJson forwards opts.wanted to notablesFromTree', () => {
  const tree = { nodes: { o: { name: 'Point Blank', stats: ['close-range damage'] } } };
  const out = E.buildEffectsJson({ runes: {}, uniques: {}, gems: {} }, { tree, wanted: new Set([E.normKey('Point Blank')]), generated: 't', sources: [] });
  assert.ok(out.notables['point blank'], 'wanted other-node resolves through buildEffectsJson');
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test tools/test-effects.cjs`
Expected: FAIL — `out.notables['point blank']` is undefined (wanted not forwarded; "Point Blank" is an unreferenced "other" node).

- [ ] **Step 3: Apply the implementation**

In `tools/effects.cjs`, replace the line (currently line 109):

```js
    notables: notablesFromTree(opts.tree || {}),
```

with:

```js
    notables: notablesFromTree(opts.tree || {}, opts.wanted),
```

- [ ] **Step 4: Run to verify all pass**

Run: `node --test tools/test-effects.cjs`
Expected: all PASS (existing `buildEffectsJson assembles…` test still passes — it passes no `wanted`, so `notablesFromTree` defaults to keystone-inclusive).

- [ ] **Step 5: Commit**

```bash
git add tools/effects.cjs tools/test-effects.cjs
git commit -m "Effects: buildEffectsJson forwards wanted to notablesFromTree"
```

---

### Task 5: Wire `wanted` into the pipeline + regenerate `effects.json`

**Files:**
- Modify: `tools/build-from-ninja.cjs:588` (`--effects-only`) and `tools/build-from-ninja.cjs:780` (enumerate effects write)
- Regenerate: `effects.json`

**Interfaces:**
- Consumes: `EFFECTS.wantedFromMeta`, the existing `meta` (enumerate) / `meta-detail.json` (effects-only).
- Produces: a regenerated `effects.json` with jewel/flask uniques, keystones, and meta-referenced notables.

- [ ] **Step 1: Pass `wanted` in `--effects-only`**

In `tools/build-from-ninja.cjs`, replace the line (currently line 588):

```js
    const out = EFFECTS.buildEffectsJson(acc, { tree, gemInfo, generated: new Date().toISOString(), sources: EFFECT_SOURCES });
```

with:

```js
    let wanted = new Set();
    try { wanted = EFFECTS.wantedFromMeta(JSON.parse(fs.readFileSync(path.join(REPO, 'meta-detail.json'), 'utf8'))); } catch (_) {}
    const out = EFFECTS.buildEffectsJson(acc, { tree, gemInfo, generated: new Date().toISOString(), sources: EFFECT_SOURCES, wanted });
```

- [ ] **Step 2: Pass `wanted` in the enumerate effects write**

In `tools/build-from-ninja.cjs`, replace the line (currently line 780):

```js
      const effects = EFFECTS.buildEffectsJson(effAcc, { tree, gemInfo, generated: nowIso, sources: EFFECT_SOURCES });
```

with:

```js
      const effects = EFFECTS.buildEffectsJson(effAcc, { tree, gemInfo, generated: nowIso, sources: EFFECT_SOURCES, wanted: EFFECTS.wantedFromMeta(meta) });
```

- [ ] **Step 3: Verify syntax + existing reconstructor tests**

Run:
```bash
node --check tools/build-from-ninja.cjs
node --test tools/test-build-from-ninja.cjs tools/test-effects.cjs
```
Expected: no syntax error; all tests PASS.

- [ ] **Step 4: Regenerate effects.json from the local cache**

Run: `node tools/build-from-ninja.cjs --effects-only`
Expected: prints counts with **uniques up from 95 to ~110+** and **notables up from 1185 to ~1220+** (e.g. `… ~115 uniques, … ~1230 notables …`).

- [ ] **Step 5: Confirm coverage jumped**

Run: `node tools/coverage-audit.cjs`
Expected: `OVERALL` now ~**95%** — uniques ~95%, notables ~98%, anointments ~90%. Specifically confirm Heart of the Well and Chaos Inoculation are no longer in the miss lists.

- [ ] **Step 6: Commit code + regenerated data**

```bash
git add tools/build-from-ninja.cjs effects.json
git commit -m "Effects: wire wanted-notables; regenerate effects.json (jewels/flasks/keystones)"
```

---

### Task 6: Front end — anointment mapping + anointment-badged card

**Files:**
- Modify: `index.html:1752` (`KIND_TO_TYPE`), `index.html:1779` + `index.html:1795` (`entityCard`), `index.html:1810` (`metaCol` call)

**Interfaces:**
- Consumes: the regenerated `effects.json`, existing `effectFor`/`metaCol`.
- Produces: anointments resolve to notable cards badged "Anointment"; the keystone/jewel data now renders.

- [ ] **Step 1: Map the Anointment kind**

In `index.html`, replace the line (currently line 1752):

```js
const KIND_TO_TYPE = { "Skill gem":"gems", "Support gem":"gems", "Passive notable":"notables", "Unique item":"uniques", "Rune / soul core":"runes" };
```

with:

```js
const KIND_TO_TYPE = { "Skill gem":"gems", "Support gem":"gems", "Passive notable":"notables", "Anointment":"notables", "Unique item":"uniques", "Rune / soul core":"runes" };
```

- [ ] **Step 2: Give `entityCard` an anointment display mode**

In `index.html`, change the signature (currently line 1779):

```js
function entityCard(type, entry){
```

to:

```js
function entityCard(type, entry, displayKind){
```

Then, in the same function, replace the line (currently line 1795):

```js
  const foot = `<div class="ent-foot">derived from public ladder data · <a href="${esc(lookupUrl(entry.name))}" target="_blank" rel="noopener noreferrer">look it up ↗</a></div>`;
```

with:

```js
  if (displayKind === "Anointment"){   // an anointment grants this notable's effect
    badge = "Anointment";
    body = `<div class="ent-base">Anoints an amulet to grant this passive:</div>` + body;
  }
  const foot = `<div class="ent-foot">derived from public ladder data · <a href="${esc(lookupUrl(entry.name))}" target="_blank" rel="noopener noreferrer">look it up ↗</a></div>`;
```

- [ ] **Step 3: Pass the kind from `metaCol`**

In `index.html`, replace the line (currently line 1810):

```js
        card = entityCard(hit.type, hit.entry);
```

with:

```js
        card = entityCard(hit.type, hit.entry, kind);
```

- [ ] **Step 4: Verify JS syntax**

Run from the repo root:
```bash
node -e "const fs=require('fs'),vm=require('vm');const h=fs.readFileSync('index.html','utf8');const re=/<script\b([^>]*)>([\s\S]*?)<\/script>/g;let m,ok=true,n=0;while((m=re.exec(h))){const a=m[1]||'';if(/src=|ld\+json|application\/json/.test(a))continue;n++;try{new vm.Script(m[2]);}catch(e){ok=false;console.log('SYNTAX ERROR:',e.message.split('\n')[0]);}}console.log(ok?('OK '+n):'PARSE ERR');"
```
Expected: `OK 1`.

- [ ] **Step 5: Verify in the local preview**

Start the server (`preview_start` "tincture") and open a build row's detail. Confirm:
- An **anointment** entity (e.g. "Well of Power") now shows a card badged **"Anointment"** with "Anoints an amulet to grant this passive:" above the notable's stats.
- A **keystone** notable (e.g. "Chaos Inoculation") now shows a card instead of the link.
- A previously-missing **unique jewel** (e.g. "Heart of the Well") now shows a card.
- `preview_console_logs` shows no errors.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "Build view: map anointments to notable cards (Anointment badge)"
```

---

## Self-Review

**Spec coverage:**
- Keystones (notables) → Task 3 (`isNotable || isKeystone`) + Task 5 (regen). ✓
- Referenced "other" notables (Point Blank…) → Task 3 (`wanted`) + Task 5 (`wantedFromMeta(meta)`). ✓
- Anointments → Task 3/5 (in notables bucket via `wanted`) + Task 6 (`KIND_TO_TYPE` + badge). ✓
- Uniques (jewels/flasks) + junk filter → Task 2 + Task 5 regen. ✓
- Coverage-audit tool → Task 1. ✓
- Fail-safe/additive, no new source, lean bucket → enforced by the edits (existing `try/catch`, `wanted`-gated tree inclusion). ✓
- Honest limitation (uniques worn by zero sampled chars, tree-absent notables) → unchanged; those fall back to the link. ✓

**Placeholder scan:** No TBD/TODO/"similar to"/vague steps; every code step shows complete code. Task 5 Steps 4-5 use "~" ranges for regenerated counts (real numbers depend on the live cache) — acceptable; the assertions are directional ("up from 95", "no longer in miss list").

**Type consistency:** `wantedFromMeta` returns a `Set`; `notablesFromTree(tree, wanted)` accepts a `Set` (defaults to empty); `buildEffectsJson` forwards `opts.wanted`; the pipeline passes `EFFECTS.wantedFromMeta(meta)` / a `Set` from `meta-detail.json`. `collectFromChar` keeps the same `acc` shape. `entityCard(type, entry, displayKind)` — the only caller (`metaCol`) passes `kind`; the front-end `normKeyFE` is unchanged and still mirrors `normKey`. ✓

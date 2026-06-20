# In-site Effect Tooltips Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hover (desktop) / tap (mobile) any rune, soul core, unique, skill/support gem, or passive notable in Tincture's build detail panel and see exactly what it does, without leaving the site.

**Architecture:** A new pure-function module `tools/effects.cjs` extracts display-ready effect text from data the weekly `build-from-ninja.cjs --enumerate` pass already pulls (poe.ninja character items for runes/uniques/gems) plus the GGG passive-tree export (notables) and the already-fetched PoB2 `Gems.lua` (gem kind + tags). It writes a single root-level `effects.json`. The front end loads it like `meta-detail.json` and, in the one `metaCol()` render chokepoint, swaps the existing Google-link tooltip for a rich card whenever an entry matches — falling back to the existing link otherwise.

**Tech Stack:** Node 22 (CommonJS `.cjs`, `node --test` built-in runner), vanilla browser JS/CSS in a single `index.html`, GitHub Actions.

## Global Constraints

- **Strictly additive / fail-safe:** a missing `effects.json` or an unmatched name MUST fall back to today's exact "look it up ↗" behavior. Never break the deployed site. (Project rule: never let upstream data break the page.)
- **No fabrication:** only ship effect text derived from real public data. An entity with no derivable text is simply absent from `effects.json` and falls back to the link.
- **No new runtime deps, no backend, no browser storage.** Pipeline stays Node for tools, stdlib-Python elsewhere; front end has no JS libraries.
- **`effects.json` lives at repo ROOT** (fetched by bare name like `data.json`, `meta-detail.json`).
- **Data sources to attribute:** poe.ninja (public ladder character data), GGG `poe2-skilltree-export` (pinned `0.5.2`), PoB2 `PathOfBuilding-PoE2` `Gems.lua` (MIT).
- **Names are matched by `normKey`** (lowercase; strip `[Tag|Disp]`/`[Tag]` markup; non-alphanumeric → single space; trim). The SAME normalization runs in the compiler and the front end.
- **Mod/stat strings are cleaned of `[...]` markup at compile time** so the front end only HTML-escapes.

---

### Task 1: `tools/effects.cjs` — normalization core

**Files:**
- Create: `tools/effects.cjs`
- Test: `tools/test-effects.cjs`

**Interfaces:**
- Produces: `normKey(s: string): string`, `cleanMarkup(s: string): string` (both exported on `module.exports`).

- [ ] **Step 1: Write the failing test**

Create `tools/test-effects.cjs`:

```js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const E = require('./effects.cjs');

test('normKey lowercases, strips markup and punctuation', () => {
  assert.strictEqual(E.normKey("Farrul's Rune of the Chase"), 'farrul s rune of the chase');
  assert.strictEqual(E.normKey('[Resistances|Fire Resistance]'), 'fire resistance');
  assert.strictEqual(E.normKey('  Soul Core  of  Quipolatl '), 'soul core of quipolatl');
  assert.strictEqual(E.normKey(null), '');
});

test('cleanMarkup unwraps tags and collapses whitespace, preserving case', () => {
  assert.strictEqual(E.cleanMarkup('Gain [Tailwind] on Skill use'), 'Gain Tailwind on Skill use');
  assert.strictEqual(E.cleanMarkup('[HitDamage|Hit]'), 'Hit');
  assert.strictEqual(E.cleanMarkup('Body Armours:   15% of   Damage'), 'Body Armours: 15% of Damage');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tools/test-effects.cjs`
Expected: FAIL — `Cannot find module './effects.cjs'`.

- [ ] **Step 3: Write minimal implementation**

Create `tools/effects.cjs`:

```js
'use strict';
// Pure extractors that turn data the enumerate pass already pulls (poe.ninja character
// items, the GGG tree export, PoB2 Gems.lua) into display-ready effect text for the
// in-site tooltips. No network, no fs — callers pass parsed inputs. Unit-tested in
// tools/test-effects.cjs; imported by tools/build-from-ninja.cjs.

function cleanMarkup(s) {
  return String(s == null ? '' : s)
    .replace(/\[[^\]|]+\|([^\]]+)\]/g, '$1') // [Tag|Display] -> Display
    .replace(/\[([^\]]+)\]/g, '$1')          // [Tag] -> Tag
    .replace(/\s+/g, ' ')
    .trim();
}

function normKey(s) {
  return cleanMarkup(s).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

module.exports = { normKey, cleanMarkup };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tools/test-effects.cjs`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add tools/effects.cjs tools/test-effects.cjs
git commit -m "Effects: normKey + cleanMarkup core for in-site tooltips"
```

---

### Task 2: tree notables + gem info extractors

**Files:**
- Modify: `tools/effects.cjs`
- Test: `tools/test-effects.cjs`

**Interfaces:**
- Consumes: `normKey`, `cleanMarkup` from Task 1.
- Produces:
  - `notablesFromTree(tree: object): { [key]: { name, stats: string[] } }` — `tree.nodes` is the GGG export shape (`node.isNotable`, `node.name`, `node.stats[]`).
  - `gemInfoFromLua(lua: string): { [key]: { kind: 'skill'|'support'|null, tags: string[] } }` — parses PoB2 `Gems.lua` entry blocks.

- [ ] **Step 1: Write the failing test**

Append to `tools/test-effects.cjs`:

```js
test('notablesFromTree keeps isNotable nodes with stats, cleaned', () => {
  const tree = { nodes: {
    root: { out: [] },
    a: { isNotable: true, name: 'Gathering Winds', stats: ['Gain [Tailwind] on Skill use', 'Lose all [Tailwind] when [HitDamage|Hit]'] },
    b: { isNotable: false, name: 'Small Node', stats: ['+10 to Dexterity'] },
    c: { isNotable: true, name: 'No Stats', stats: [] },
  }};
  const out = E.notablesFromTree(tree);
  assert.deepStrictEqual(Object.keys(out), ['gathering winds']);
  assert.strictEqual(out['gathering winds'].name, 'Gathering Winds');
  assert.deepStrictEqual(out['gathering winds'].stats, ['Gain Tailwind on Skill use', 'Lose all Tailwind when Hit']);
});

test('gemInfoFromLua parses kind from gameId and display tags', () => {
  const lua = [
    '\t["Metadata/Items/Gems/SkillGemIceNova"] = {',
    '\t\tname = "Ice Nova",',
    '\t\tgameId = "Metadata/Items/Gems/SkillGemIceNova",',
    '\t\ttags = {',
    '\t\t\tintelligence = true,',
    '\t\t\tgrants_active_skill = true,',
    '\t\t\tspell = true,',
    '\t\t\tcold = true,',
    '\t\t},',
    '\t},',
    '\t["Metadata/Items/Gems/SupportGemInspiration"] = {',
    '\t\tname = "Inspiration",',
    '\t\tgameId = "Metadata/Items/Gems/SupportGemInspiration",',
    '\t\ttags = {',
    '\t\t\tsupport = true,',
    '\t\t},',
    '\t},',
  ].join('\n');
  const out = E.gemInfoFromLua(lua);
  assert.strictEqual(out['ice nova'].kind, 'skill');
  assert.deepStrictEqual(out['ice nova'].tags, ['spell', 'cold']);
  assert.strictEqual(out['inspiration'].kind, 'support');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tools/test-effects.cjs`
Expected: FAIL — `E.notablesFromTree is not a function`.

- [ ] **Step 3: Write minimal implementation**

In `tools/effects.cjs`, add before `module.exports` and extend the exports:

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

// tags that describe the gem's category for chips; drop attribute/plumbing tags
const TAG_SKIP = new Set(['strength', 'dexterity', 'intelligence', 'grants_active_skill', 'grants_active_skill_or_minion', 'support']);

function gemInfoFromLua(lua) {
  const out = {};
  const re = /\[\s*"([^"]+)"\s*\]\s*=\s*\{([\s\S]*?)\n\t\},/g; // tab-indented entry close (mirrors gemMapFromLua)
  let x;
  while ((x = re.exec(lua))) {
    const gameId = x[1], body = x[2];
    const name = (body.match(/name\s*=\s*"([^"]*)"/) || [])[1];
    if (!name) continue;
    const kind = /\/SupportGem/i.test(gameId) ? 'support' : /\/SkillGem/i.test(gameId) ? 'skill' : null;
    const tagsBlock = (body.match(/tags\s*=\s*\{([\s\S]*?)\}/) || [])[1] || '';
    const tags = [...tagsBlock.matchAll(/(\w+)\s*=\s*true/g)].map(m => m[1]).filter(t => !TAG_SKIP.has(t));
    out[normKey(name)] = { kind, tags };
  }
  return out;
}
```

Update the export line:

```js
module.exports = { normKey, cleanMarkup, notablesFromTree, gemInfoFromLua };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tools/test-effects.cjs`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add tools/effects.cjs tools/test-effects.cjs
git commit -m "Effects: notablesFromTree + gemInfoFromLua extractors"
```

---

### Task 3: `collectFromChar` — runes, uniques, gems from poe.ninja characters

**Files:**
- Modify: `tools/effects.cjs`
- Test: `tools/test-effects.cjs`

**Interfaces:**
- Consumes: `normKey`, `cleanMarkup`.
- Produces: `collectFromChar(char: object, acc: {runes,uniques,gems}): void` — mutates `acc` in place. `char` is a poe.ninja character object: `char.items[]` (each may be `{itemData}` or the item; has `frameType`, `name`, `baseType`, `socketedItems[]`, `explicitMods`, `implicitMods`, `flavourText`), `char.skills[].allGems[]` (`{name, itemData:{descrText, secDescrText, typeLine}}`). Rune effect mods carry slot-prefixed text e.g. `"Boots: 5% increased Movement Speed"`. Accumulates the UNION of distinct rune lines across characters/slots.

- [ ] **Step 1: Write the failing test**

Append to `tools/test-effects.cjs`:

```js
test('collectFromChar gathers runes (union of slot lines), uniques, gems', () => {
  const acc = { runes: {}, uniques: {}, gems: {} };
  const charA = {
    items: [
      { itemData: { inventoryId: 'Boots', frameType: 2, socketedItems: [
        { typeLine: "Farrul's Rune of the Chase", explicitMods: ['Boots: 5% increased Movement Speed'] } ] } },
      { itemData: { inventoryId: 'Ring', frameType: 3, name: "Kalandra's Touch", baseType: 'Ring',
        implicitMods: [], explicitMods: ['Reflects opposite Ring'], flavourText: ['Power is a matter of perspective.'] } },
    ],
    skills: [ { allGems: [
      { name: 'Ice Nova', itemData: { typeLine: 'Ice Nova', secDescrText: 'Creates a ring of [Cold] damage.' } } ] } ],
  };
  const charB = {
    items: [
      { itemData: { inventoryId: 'BodyArmour', frameType: 2, socketedItems: [
        { typeLine: "Farrul's Rune of the Chase", explicitMods: ['Body Armours: +10 to Spirit'] } ] } },
    ], skills: [],
  };
  E.collectFromChar(charA, acc);
  E.collectFromChar(charB, acc);

  assert.deepStrictEqual(acc.runes['farrul s rune of the chase'].lines,
    ['Boots: 5% increased Movement Speed', 'Body Armours: +10 to Spirit']);
  assert.strictEqual(acc.uniques['kalandra s touch'].base, 'Ring');
  assert.deepStrictEqual(acc.uniques['kalandra s touch'].mods, ['Reflects opposite Ring']);
  assert.strictEqual(acc.uniques['kalandra s touch'].flavour, 'Power is a matter of perspective.');
  assert.strictEqual(acc.gems['ice nova'].desc, 'Creates a ring of Cold damage.');
});

test('collectFromChar skips gems with no description text', () => {
  const acc = { runes: {}, uniques: {}, gems: {} };
  E.collectFromChar({ items: [], skills: [ { allGems: [ { name: 'Mystery', itemData: {} } ] } ] }, acc);
  assert.strictEqual(acc.gems['mystery'], undefined);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tools/test-effects.cjs`
Expected: FAIL — `E.collectFromChar is not a function`.

- [ ] **Step 3: Write minimal implementation**

Add to `tools/effects.cjs` before `module.exports`:

```js
function collectFromChar(char, acc) {
  for (const it of (char.items || [])) {
    const d = it.itemData || it;
    // runes / soul cores socketed into gear — mod text is slot-prefixed and self-describing
    for (const s of (d.socketedItems || [])) {
      const nm = s.typeLine || s.baseType || s.name || '';
      if (!nm || !/\bRune\b|Soul Core/i.test(nm)) continue;
      const key = normKey(nm);
      const e = acc.runes[key] || (acc.runes[key] = { name: cleanMarkup(nm), lines: [] });
      for (const m of (s.explicitMods || [])) {
        const line = cleanMarkup(m);
        if (line && !e.lines.includes(line)) e.lines.push(line);
      }
    }
    // uniques — first seen wins (a representative real item)
    if (d.frameType === 3 && d.name) {
      const key = normKey(d.name);
      if (!acc.uniques[key]) {
        acc.uniques[key] = {
          name: cleanMarkup(d.name),
          base: cleanMarkup(d.baseType || d.typeLine || ''),
          mods: [].concat(d.implicitMods || [], d.explicitMods || []).map(cleanMarkup).filter(Boolean),
          flavour: cleanMarkup((d.flavourText || []).join(' ')),
        };
      }
    }
  }
  // skill + support gems — description from the in-game gem text
  for (const g of (char.skills || [])) {
    for (const gm of (g.allGems || [])) {
      const d = gm.itemData || {};
      const nm = gm.name || d.typeLine || d.baseType;
      if (!nm) continue;
      const key = normKey(nm);
      if (acc.gems[key]) continue;
      const desc = cleanMarkup(d.secDescrText || d.descrText || '');
      if (!desc) continue; // no description -> omit (front end falls back to link)
      acc.gems[key] = { name: cleanMarkup(nm), desc };
    }
  }
}
```

Update exports:

```js
module.exports = { normKey, cleanMarkup, notablesFromTree, gemInfoFromLua, collectFromChar };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tools/test-effects.cjs`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add tools/effects.cjs tools/test-effects.cjs
git commit -m "Effects: collectFromChar extracts runes/uniques/gems"
```

---

### Task 4: `buildEffectsJson` — assemble the final document

**Files:**
- Modify: `tools/effects.cjs`
- Test: `tools/test-effects.cjs`

**Interfaces:**
- Consumes: `notablesFromTree`, `gemInfoFromLua` outputs, plus an `acc` from `collectFromChar`.
- Produces: `buildEffectsJson(acc, opts): object` where `opts = { tree, gemInfo, generated: string, sources: object[] }`. Returns `{ meta:{generated,sources}, runes, uniques, gems, notables }`. Gems are merged with `gemInfo` (kind + tags); runes with no lines are dropped.

- [ ] **Step 1: Write the failing test**

Append to `tools/test-effects.cjs`:

```js
test('buildEffectsJson assembles all maps and merges gem kind+tags', () => {
  const acc = {
    runes: { 'a rune': { name: 'A Rune', lines: ['Boots: +1'] }, 'empty': { name: 'Empty', lines: [] } },
    uniques: { 'x': { name: 'X', base: 'Ring', mods: ['m'], flavour: '' } },
    gems: { 'ice nova': { name: 'Ice Nova', desc: 'cold ring' } },
  };
  const tree = { nodes: { n: { isNotable: true, name: 'Notable One', stats: ['+5 life'] } } };
  const gemInfo = { 'ice nova': { kind: 'skill', tags: ['cold', 'spell'] } };
  const out = E.buildEffectsJson(acc, { tree, gemInfo, generated: '2026-06-19T00:00:00Z', sources: [{ name: 'poe.ninja' }] });

  assert.strictEqual(out.meta.generated, '2026-06-19T00:00:00Z');
  assert.strictEqual(out.meta.sources[0].name, 'poe.ninja');
  assert.deepStrictEqual(Object.keys(out.runes), ['a rune']); // empty-lines rune dropped
  assert.strictEqual(out.gems['ice nova'].kind, 'skill');
  assert.deepStrictEqual(out.gems['ice nova'].tags, ['cold', 'spell']);
  assert.strictEqual(out.notables['notable one'].stats[0], '+5 life');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tools/test-effects.cjs`
Expected: FAIL — `E.buildEffectsJson is not a function`.

- [ ] **Step 3: Write minimal implementation**

Add to `tools/effects.cjs` before `module.exports`:

```js
function buildEffectsJson(acc, opts) {
  const gemInfo = (opts && opts.gemInfo) || {};
  const gems = {};
  for (const [key, g] of Object.entries(acc.gems || {})) {
    const info = gemInfo[key] || {};
    gems[key] = { name: g.name, kind: g.kind || info.kind || 'skill', desc: g.desc, tags: info.tags || [] };
  }
  const runes = {};
  for (const [key, r] of Object.entries(acc.runes || {})) {
    if (r.lines && r.lines.length) runes[key] = { name: r.name, lines: r.lines };
  }
  return {
    meta: { generated: opts.generated, sources: opts.sources || [] },
    runes,
    uniques: acc.uniques || {},
    gems,
    notables: notablesFromTree(opts.tree || {}),
  };
}
```

Update exports:

```js
module.exports = { normKey, cleanMarkup, notablesFromTree, gemInfoFromLua, collectFromChar, buildEffectsJson };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tools/test-effects.cjs`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add tools/effects.cjs tools/test-effects.cjs
git commit -m "Effects: buildEffectsJson assembles effects.json document"
```

---

### Task 5: Wire into `build-from-ninja.cjs` (+ `--effects-only` generator)

**Files:**
- Modify: `tools/build-from-ninja.cjs` (imports near line 30; `EFFECT_SOURCES` const near line 36; capture Lua text near line 581; accumulate + write in `--enumerate` near lines 619/749; add `--effects-only` branch in `main()` near line 567)
- Modify: `.gitignore` check (none needed — `effects.json` is at repo root, committed)

**Interfaces:**
- Consumes: `effects.cjs` exports.
- Produces: a root `effects.json`; a new CLI mode `node tools/build-from-ninja.cjs --effects-only` that builds `effects.json` from the existing `tools/.cache/c-*.json` characters + tree + `Gems.lua` (no rate-limited poe.ninja build calls).

- [ ] **Step 1: Add the import and sources constant**

In `tools/build-from-ninja.cjs`, after the existing `const zlib = require('zlib');` (line 30) add:

```js
const EFFECTS = require('./effects.cjs');
```

After the `CACHE_DIR` definition (line 37) add:

```js
// Attribution for effects.json (in-site effect tooltips). All public, derived at build time.
const EFFECT_SOURCES = [
  { name: 'poe.ninja', what: 'public ladder character data (rune/unique/gem text)', url: 'https://poe.ninja/poe2/builds' },
  { name: 'poe2-skilltree-export', ref: '0.5.2', what: 'passive notable stats', url: 'https://github.com/grindinggear/poe2-skilltree-export' },
  { name: 'PathOfBuilding-PoE2', license: 'MIT', what: 'gem kind + tags (Gems.lua)', url: 'https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2' },
];
```

- [ ] **Step 2: Capture the Lua text and build gemInfo in `main()`**

Find (line ~581):

```js
  const gem = gemMapFromLua(await cached('Gems.lua', GEMS_URL));
```

Replace with:

```js
  const luaText = await cached('Gems.lua', GEMS_URL);
  const gem = gemMapFromLua(luaText);
  const gemInfo = EFFECTS.gemInfoFromLua(luaText);
```

- [ ] **Step 3: Add the `--effects-only` branch**

In `main()`, immediately after the line `const league = opt.league || 'runesofaldur';` (line 571), add:

```js
  if (opt['effects-only']) {
    const luaText = await diskCached('Gems.lua', () => get(GEMS_URL));
    const tree = JSON.parse(await diskCached('tree.json', () => get(TREE_URL)));
    const gemInfo = EFFECTS.gemInfoFromLua(luaText);
    const acc = { runes: {}, uniques: {}, gems: {} };
    const files = fs.readdirSync(CACHE_DIR).filter(f => /^c-.*\.json$/.test(f));
    for (const f of files) { try { EFFECTS.collectFromChar(JSON.parse(fs.readFileSync(path.join(CACHE_DIR, f), 'utf8')), acc); } catch (_) {} }
    const out = EFFECTS.buildEffectsJson(acc, { tree, gemInfo, generated: new Date().toISOString(), sources: EFFECT_SOURCES });
    fs.writeFileSync(path.join(REPO, 'effects.json'), JSON.stringify(out, null, 2) + '\n');
    console.log(`effects.json: ${Object.keys(out.runes).length} runes, ${Object.keys(out.uniques).length} uniques, ${Object.keys(out.gems).length} gems, ${Object.keys(out.notables).length} notables (from ${files.length} cached chars)`);
    return;
  }
```

- [ ] **Step 4: Accumulate + write effects.json inside `--enumerate`**

Find (line ~628) `let builds = 0;` and the next line `const globalChars = [];`. After `const globalChars = [];` add:

```js
    const effAcc = { runes: {}, uniques: {}, gems: {} };
```

Then find the block (line ~747):

```js
    if (globalChars.length && meta.global) { const gg = aggregateGear(globalChars); meta.global.gear = gg.gear; meta.global.runes = gg.runes; }
```

Immediately AFTER it, add:

```js
    // effect-text glossary for the in-site tooltips — derived from the same pulled characters,
    // the tree export, and Gems.lua. Fail-safe: a problem here must never abort the build/meta commit.
    try {
      globalChars.forEach(c => EFFECTS.collectFromChar(c, effAcc));
      const effects = EFFECTS.buildEffectsJson(effAcc, { tree, gemInfo, generated: nowIso, sources: EFFECT_SOURCES });
      fs.writeFileSync(path.join(REPO, 'effects.json'), JSON.stringify(effects, null, 2) + '\n');
      console.log(`effects.json: ${Object.keys(effects.runes).length} runes, ${Object.keys(effects.uniques).length} uniques, ${Object.keys(effects.gems).length} gems, ${Object.keys(effects.notables).length} notables`);
    } catch (e) { console.log('effects.json skipped:', e.message); }
```

(`nowIso` is already defined at line ~618; `gemInfo` from Step 2; `tree` from line ~579.)

- [ ] **Step 5: Verify syntax + existing unit tests still pass**

Run:
```bash
node --check tools/build-from-ninja.cjs
node --test tools/test-build-from-ninja.cjs
```
Expected: no syntax error; existing reconstructor tests PASS.

- [ ] **Step 6: Generate a real effects.json from the local cache**

Run: `node tools/build-from-ninja.cjs --effects-only`
Expected: writes `effects.json`; prints non-zero counts, e.g. `effects.json: NN runes, NN uniques, NN gems, 1192 notables (from 100+ cached chars)`. (First run fetches `tree.json` once into `tools/.cache`.)

Confirm shape:
```bash
node -e "const e=require('./effects.json'); console.log(Object.keys(e), e.meta.sources.length, Object.keys(e.notables).length>0)"
```
Expected: prints `[ 'meta', 'runes', 'uniques', 'gems', 'notables' ] 3 true`.

- [ ] **Step 7: Commit**

```bash
git add tools/build-from-ninja.cjs effects.json
git commit -m "Effects: generate effects.json in enumerate + --effects-only mode"
```

---

### Task 6: Front end — load `effects.json` and `effectFor()` lookup

**Files:**
- Modify: `index.html` (global near line 1338; boot `Promise.all` near line 2858; add `effectFor`/`KIND_TO_TYPE`/`normKeyFE` near `lookupUrl` at line 1722)

**Interfaces:**
- Consumes: `effects.json` shape from Task 4.
- Produces: global `EFFECTS`; `effectFor(kind, name) -> { type, entry } | null`. `kind` is the `metaCol` category string ("Skill gem", "Support gem", "Passive notable", "Unique item", "Rune / soul core").

- [ ] **Step 1: Add the global**

Find (line ~1338) `let META = null;` and add directly below:

```js
let EFFECTS = null;        // effects.json: in-site effect text for runes/uniques/gems/notables
```

- [ ] **Step 2: Fetch effects.json in boot**

Find (lines ~2858-2866):

```js
  const [m, h, ec] = await Promise.all([
    fetchJSON("meta-detail.json", 8000),
    fetchJSON("history.json", 8000),
    fetchJSON("economy.json", 8000),
    buildsManifest().catch(() => null),
  ]);
  if (m && m.byAsc) META = m;   // validate shape before promoting (never enrich from garbage)
  if (h && Array.isArray(h.points)) HISTORY = h;
  if (ec && Array.isArray(ec.currencies)) ECONOMY = ec;
```

Replace with:

```js
  const [m, h, ec, ef] = await Promise.all([
    fetchJSON("meta-detail.json", 8000),
    fetchJSON("history.json", 8000),
    fetchJSON("economy.json", 8000),
    fetchJSON("effects.json", 8000),
    buildsManifest().catch(() => null),
  ]);
  if (m && m.byAsc) META = m;   // validate shape before promoting (never enrich from garbage)
  if (h && Array.isArray(h.points)) HISTORY = h;
  if (ec && Array.isArray(ec.currencies)) ECONOMY = ec;
  if (ef && (ef.runes || ef.uniques || ef.gems || ef.notables)) EFFECTS = ef;   // shape-gate before promoting
```

- [ ] **Step 3: Add the lookup helpers**

Find `function lookupUrl(name){` (line ~1724). Directly ABOVE it, add:

```js
// map a metaCol category label -> effects.json bucket
const KIND_TO_TYPE = { "Skill gem":"gems", "Support gem":"gems", "Passive notable":"notables", "Unique item":"uniques", "Rune / soul core":"runes" };
// SAME normalization as tools/effects.cjs normKey — strip markup, lowercase, punctuation -> space.
function normKeyFE(s){
  return String(s==null?"":s)
    .replace(/\[[^\]|]+\|([^\]]+)\]/g,"$1").replace(/\[([^\]]+)\]/g,"$1")
    .toLowerCase().replace(/[^a-z0-9]+/g," ").trim();
}
// resolve an entity to its effect entry, or null (caller then falls back to the lookup link).
function effectFor(kind, name){
  if (!EFFECTS) return null;
  const type = KIND_TO_TYPE[kind];
  const map = type && EFFECTS[type];
  if (!map) return null;
  const k = normKeyFE(name);
  if (map[k]) return { type, entry: map[k] };
  if (type === "runes"){   // tier fallback: "Perfect Iron Rune" -> "iron rune"
    const k2 = k.replace(/^(lesser|greater|grand|perfect|superior|exceptional)\s+/,"");
    if (k2 !== k && map[k2]) return { type, entry: map[k2] };
  }
  return null;
}
```

- [ ] **Step 4: Verify it loads with no errors**

Start the local static server from the repo root and open the site in the preview:
```bash
node serve 8099   # or: python -m http.server 8099  (repo serves index.html at /)
```
- preview_start the served URL, then preview_console_logs.
Expected: no console errors; `EFFECTS` populated — verify with preview_eval `JSON.stringify(Object.keys(EFFECTS))` → `["meta","runes","uniques","gems","notables"]`, and `effectFor("Rune / soul core", Object.values(EFFECTS.runes)[0].name)` returns an object (not null).

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "Build view: load effects.json + effectFor lookup"
```

---

### Task 7: Front end — `entityCard()` renderer + `.ent-card` styles

**Files:**
- Modify: `index.html` (add `entityCard` near `effectFor`; add CSS after the `.bv-tip` block at line ~746)

**Interfaces:**
- Consumes: `effectFor` result `{ type, entry }`, `esc`, `lookupUrl`.
- Produces: `entityCard(type, entry) -> string` (HTML for one `.ent-card`).

- [ ] **Step 1: Add the renderer**

Directly below `effectFor` (Task 6 Step 3), add:

```js
// rich hover/tap card for one entity. Mirrors the .bv-tip item card; reuses .tip-mod/.tip-num.
function entityCard(type, entry){
  const numify = m => esc(m).replace(/(\d[\d.]*(?:\s*(?:to|–|-)\s*\d[\d.]*)?)/g, '<span class="tip-num">$1</span>');
  const modRows = arr => (arr||[]).map(l=>`<div class="tip-mod">${numify(l)}</div>`).join("");
  let body = "", badge = "";
  if (type === "runes"){ badge = "Rune / Soul Core"; body = modRows(entry.lines); }
  else if (type === "notables"){ badge = "Notable"; body = modRows(entry.stats); }
  else if (type === "uniques"){
    badge = "Unique";
    body = (entry.base?`<div class="ent-base">${esc(entry.base)}</div>`:"")
      + modRows(entry.mods)
      + (entry.flavour?`<div class="ent-flav">${esc(entry.flavour)}</div>`:"");
  } else if (type === "gems"){
    badge = entry.kind === "support" ? "Support" : "Skill";
    body = ((entry.tags||[]).length?`<div class="ent-tags">${entry.tags.slice(0,6).map(t=>`<span class="ent-tag">${esc(t)}</span>`).join("")}</div>`:"")
      + `<div class="ent-desc">${esc(entry.desc)}</div>`;
  }
  const foot = `<div class="ent-foot">derived from public ladder data · <a href="${lookupUrl(entry.name)}" target="_blank" rel="noopener noreferrer">look it up ↗</a></div>`;
  return `<div class="ent-card" role="tooltip"><div class="ent-head"><span class="ent-name">${esc(entry.name)}</span><span class="ent-badge">${esc(badge)}</span></div>${body}${foot}</div>`;
}
```

- [ ] **Step 2: Add the CSS**

In the `<style>` block, immediately AFTER the `.bv-actions{ margin-top:15px; }` line (line ~747), add:

```css
  /* in-site effect cards on meta entities (runes/uniques/gems/notables) */
  .meta-item.has-card{ position:relative; }
  .meta-item .nm.tip-link.ent-trigger{ background:none; border:none; padding:0; margin:0; font:inherit;
    text-align:left; color:var(--bone); cursor:help; border-bottom:1px dotted transparent; }
  .meta-item .nm.tip-link.ent-trigger:hover, .meta-item .nm.tip-link.ent-trigger:focus-visible{
    color:var(--gold-bright); border-bottom-color:var(--hair-strong); outline:none; }
  .ent-card{ display:none; position:absolute; left:0; top:calc(100% + 4px); z-index:50;
    width:max-content; max-width:300px; padding:9px 11px 10px;
    background:var(--ink-2); border:1px solid var(--hair-strong); border-radius:3px;
    box-shadow:0 10px 30px rgba(0,0,0,.55); text-align:left; cursor:default; white-space:normal; }
  .meta-item.has-card:hover .ent-card, .meta-item.has-card:focus-within .ent-card,
  .meta-item.has-card.open .ent-card{ display:block; }
  .ent-head{ display:flex; align-items:baseline; gap:8px; justify-content:space-between;
    margin-bottom:6px; padding-bottom:6px; border-bottom:1px solid var(--hair); }
  .ent-name{ font-family:var(--fdisplay); font-size:13px; color:var(--gold-bright); }
  .ent-badge{ font-family:var(--fmono); font-size:9px; letter-spacing:.1em; text-transform:uppercase;
    color:var(--muted); border:1px solid var(--hair); border-radius:2px; padding:1px 5px; flex:none; }
  .ent-base{ font-family:var(--fmono); font-size:10px; color:var(--muted); margin-bottom:5px; }
  .ent-desc{ font-family:var(--ftext); font-size:12px; line-height:1.45; color:var(--bone-dim); }
  .ent-flav{ font-family:var(--ftext); font-style:italic; font-size:11.5px; color:var(--muted); margin-top:7px; }
  .ent-tags{ display:flex; flex-wrap:wrap; gap:4px; margin-bottom:6px; }
  .ent-tag{ font-family:var(--fmono); font-size:9px; letter-spacing:.04em; color:var(--bone-dim);
    border:1px solid var(--hair); border-radius:2px; padding:1px 5px; }
  .ent-foot{ font-family:var(--fmono); font-size:9px; line-height:1.5; color:var(--muted);
    margin-top:8px; padding-top:6px; border-top:1px solid var(--hair); }
  .ent-foot a{ color:var(--verdigris); text-decoration:none; }
  .ent-foot a:hover{ color:var(--gold-bright); }
```

- [ ] **Step 3: Verify the renderer in isolation**

In the preview (server still running), preview_eval:
```js
entityCard("runes", { name:"Test Rune", lines:["Boots: 5% increased Movement Speed"] })
```
Expected: returns an HTML string containing `ent-card`, `Test Rune`, `tip-num` around `5`. No exception.

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "Build view: entityCard renderer + effect-card styles"
```

---

### Task 8: Front end — enrich `metaCol()` to attach cards

**Files:**
- Modify: `index.html` (`metaCol` item builder, lines ~1731-1742)

**Interfaces:**
- Consumes: `effectFor`, `entityCard`.
- Produces: enriched `.meta-item` markup — a focusable `.ent-trigger` button + appended `.ent-card` when `effectFor` hits; otherwise the existing `data-tip` + link, unchanged.

- [ ] **Step 1: Replace the item builder**

Find (lines ~1731-1742):

```js
  const items = arr.map(x=>{
    const label = fmtName ? fmtName(x) : esc(x.name);
    let cls = "meta-item", attr = "", nm;
    if (kind){   // named entity: tooltip (full name + category) + one-click lookup
      cls += " tip-row";
      attr = ` data-tip="${esc(x.name)} · ${esc(kind)} · look it up ↗"`;
      nm = `<a class="nm tip-link" href="${lookupUrl(x.name)}" target="_blank" rel="noopener noreferrer">${label}</a>`;
    } else {     // affix lines are self-describing stat text — left as plain labels
      nm = `<span class="nm">${label}</span>`;
    }
    return `<div class="${cls}"${attr}><div class="r1">${nm}<span class="pc">${x.pct}%</span></div><div class="track"><div class="fill" style="width:${Math.max(2,Math.min(100,x.pct))}%"></div></div></div>`;
  }).join("");
```

Replace with:

```js
  const items = arr.map(x=>{
    const label = fmtName ? fmtName(x) : esc(x.name);
    let cls = "meta-item", attr = "", nm, card = "";
    if (kind){   // named entity: rich effect card when we have it, else the lookup link
      cls += " tip-row";
      const hit = effectFor(kind, x.name);
      if (hit){
        cls += " has-card";
        nm = `<button type="button" class="nm tip-link ent-trigger" aria-expanded="false">${label}</button>`;
        card = entityCard(hit.type, hit.entry);
      } else {
        attr = ` data-tip="${esc(x.name)} · ${esc(kind)} · look it up ↗"`;
        nm = `<a class="nm tip-link" href="${lookupUrl(x.name)}" target="_blank" rel="noopener noreferrer">${label}</a>`;
      }
    } else {     // affix lines are self-describing stat text — left as plain labels
      nm = `<span class="nm">${label}</span>`;
    }
    return `<div class="${cls}"${attr}><div class="r1">${nm}<span class="pc">${x.pct}%</span></div><div class="track"><div class="fill" style="width:${Math.max(2,Math.min(100,x.pct))}%"></div></div>${card}</div>`;
  }).join("");
```

- [ ] **Step 2: Verify in the live UI**

In the preview: open a ledger row to expand its detail (preview_click the first `.row`), then preview_snapshot.
Expected: in "Top skills / Top supports / Top notables / Top uniques / Weapon augments", hovering an entity name shows a dark card with real effect text (a rune's slot-prefixed lines, a unique's mods + flavour, a gem's tags + description, a notable's stats). Entities with no match still show the old "look it up ↗" link. preview_console_logs shows no errors.

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "Build view: show effect cards on meta entities (was google-link only)"
```

---

### Task 9: Front end — hybrid tap controller + keyboard a11y

**Files:**
- Modify: `index.html` (add `setupEntityCards()` near `setupArchive`; call it in boot near line 2878)

**Interfaces:**
- Consumes: the `.ent-trigger` / `.meta-item.has-card` markup from Task 8.
- Produces: `setupEntityCards()` — one delegated controller. Desktop keeps CSS hover/focus; click pins/toggles `.open`; touch taps to open; outside-click and Esc close; only one open at a time.

- [ ] **Step 1: Add the controller**

Directly above `function metaCol(` (line ~1727), add:

```js
// hybrid open/close for effect cards: desktop also opens on hover/focus via CSS; this adds
// click-to-pin (desktop) and tap-to-open (touch), single-open, with outside-click + Esc close.
function closeAllCards(){
  document.querySelectorAll(".meta-item.has-card.open").forEach(el=>{
    el.classList.remove("open");
    const b = el.querySelector(".ent-trigger"); if (b) b.setAttribute("aria-expanded","false");
  });
}
function setupEntityCards(){
  document.addEventListener("click", e=>{
    if (e.target.closest && e.target.closest(".ent-card")) return;   // clicks inside a card (e.g. the link) pass through
    const trig = e.target.closest && e.target.closest(".ent-trigger");
    if (trig){
      const host = trig.closest(".meta-item.has-card");
      if (host){
        e.preventDefault();
        const wasOpen = host.classList.contains("open");
        closeAllCards();
        if (!wasOpen){ host.classList.add("open"); trig.setAttribute("aria-expanded","true"); }
      }
      return;
    }
    closeAllCards();   // any outside click
  });
  document.addEventListener("keydown", e=>{ if (e.key === "Escape") closeAllCards(); });
}
```

- [ ] **Step 2: Call it in boot**

Find `setupArchive();` in `boot()` (line ~2878) and add directly below:

```js
  setupEntityCards();
```

- [ ] **Step 3: Verify hover, click-pin, tap, and keyboard**

In the preview (desktop viewport): open a build row.
- Hover an entity → card shows; move away → hides.
- Click the entity name → card stays pinned; click elsewhere → closes. preview_console_logs: no errors.
- Keyboard: Tab to a trigger → card shows on focus; Esc → closes.
Then preview_resize to a mobile width and confirm tap-to-open / tap-outside-to-close works (CSS `:hover` won't fire on tap, the controller handles it).

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "Build view: hybrid hover/tap + keyboard control for effect cards"
```

---

### Task 10: CI gating, commit list, and attribution

**Files:**
- Modify: `.github/workflows/test.yml` (the "Reconstructor syntax + unit tests" step, lines 43-46)
- Modify: `.github/workflows/builds.yml` (unit-test gate lines 40-43; commit step lines 58-65)
- Modify: `index.html` (open-data credits — search for the Cellar/credits copy)
- Modify: `README.md` (data sources/credits)

**Interfaces:**
- Consumes: `tools/test-effects.cjs`, `effects.json`.
- Produces: CI runs the effects unit tests; the weekly build commits a refreshed `effects.json`; sources are credited on-site and in the README.

- [ ] **Step 1: Gate effects tests in test.yml**

In `.github/workflows/test.yml`, replace (lines 43-46):

```yaml
      - name: Reconstructor syntax + unit tests
        run: |
          node --check tools/build-from-ninja.cjs
          node --test tools/test-build-from-ninja.cjs
```

with:

```yaml
      - name: Reconstructor + effects syntax + unit tests
        run: |
          node --check tools/build-from-ninja.cjs
          node --check tools/effects.cjs
          node --test tools/test-build-from-ninja.cjs tools/test-effects.cjs
```

- [ ] **Step 2: Gate effects tests in builds.yml**

In `.github/workflows/builds.yml`, replace (lines 40-43):

```yaml
      - name: Reconstructor syntax + unit tests
        run: |
          node --check tools/build-from-ninja.cjs
          node --test tools/test-build-from-ninja.cjs
```

with:

```yaml
      - name: Reconstructor + effects syntax + unit tests
        run: |
          node --check tools/build-from-ninja.cjs
          node --check tools/effects.cjs
          node --test tools/test-build-from-ninja.cjs tools/test-effects.cjs
```

- [ ] **Step 3: Add effects.json to the build commit**

In `.github/workflows/builds.yml`, replace the commit step body (lines 58-65):

```yaml
          if git diff --quiet -- builds/ meta-detail.json; then
            echo "No change this run."
          else
            git add builds/ meta-detail.json
            git commit -m "Builds: refresh reconstructed builds + meta ($(date -u '+%Y-%m-%d %H:%M UTC'))"
            # the hourly distill bot pushes to the same branch — rebase to avoid a Monday race
            git pull --rebase --autostash origin main
            git push
          fi
```

with:

```yaml
          if git diff --quiet -- builds/ meta-detail.json effects.json; then
            echo "No change this run."
          else
            git add builds/ meta-detail.json effects.json
            git commit -m "Builds: refresh reconstructed builds + meta + effects ($(date -u '+%Y-%m-%d %H:%M UTC'))"
            # the hourly distill bot pushes to the same branch — rebase to avoid a Monday race
            git pull --rebase --autostash origin main
            git push
          fi
```

- [ ] **Step 4: Credit the sources on-site**

In `index.html`, find the open-data / credits copy (search for `data.json is the API` near line 1244, or the footer credits). Add a sentence in the nearest credits/disclaimer block:

```html
<p class="sub">In-build effect text for runes, uniques, gems and notables is derived at build time from public ladder data (poe.ninja), the official passive-tree export, and Path of Building Community (PoB2, MIT) — see <a href="effects.json">effects.json</a>. It falls back to a web lookup when an entry isn't available.</p>
```

- [ ] **Step 5: Credit the sources in README**

In `README.md`, in the data-sources/credits section, add:

```markdown
- **Effect tooltips** (`effects.json`): rune/unique/gem/notable effect text derived at build
  time from poe.ninja public ladder data, the GGG `poe2-skilltree-export` (0.5.2), and PoB2
  `Gems.lua` (MIT). Strictly additive — falls back to a web lookup when an entry is missing.
```

- [ ] **Step 6: Verify CI config is well-formed**

Run:
```bash
node --check tools/effects.cjs && node --test tools/test-effects.cjs
python - <<'PY'
import yaml
for f in (".github/workflows/test.yml", ".github/workflows/builds.yml"):
    yaml.safe_load(open(f)); print("ok", f)
PY
```
Expected: effects tests PASS; both YAML files parse (`ok ...`). (If `pyyaml`/python is unavailable locally, this is validated in CI — note it and proceed.)

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/test.yml .github/workflows/builds.yml index.html README.md
git commit -m "Effects: gate unit tests in CI, commit effects.json, credit sources"
```

---

## Self-Review

**Spec coverage** (against `2026-06-19-in-site-effect-tooltips-design.md`):
- Full coverage (runes/soul cores, uniques, skill+support gems, notables) → Tasks 3 (runes/uniques/gems), 2 (notables), 8 (all surfaced via `metaCol`). ✓
- Hybrid hover/tap interaction → Tasks 7 (CSS hover/focus) + 9 (tap/keyboard). ✓
- Build-time derived dataset, version-pinned, attributed, fails safe → Tasks 5 (generation, pinned tree 0.5.2 + Gems.lua) + 10 (CI, attribution). ✓
- Matching/normalization with tier handling → Tasks 1 (`normKey`) + 6 (`normKeyFE` + rune tier fallback). ✓
- Coverage honesty / no over-claim → effects derived only from real data; gems without descriptions omitted (Task 3); missing entries fall back to link (Tasks 6/8). The weekly run logs counts (Task 5). ✓
- **Spec deviation (intentional, post-spike):** the spec named PoB2 `Data/` (uniques) as a source and a separate `tools/build-effects.cjs`. The spike proved rune/unique/gem effect text is already in the poe.ninja character data the enumerate pass pulls, so the plan derives it there (PoB2 used only for gem tags via the already-fetched `Gems.lua`) and folds generation into `build-from-ninja.cjs` + a `tools/effects.cjs` module. Lower-dependency, same honesty/fail-safe posture. The spec should be updated to match.

**Placeholder scan:** No "TBD"/"add error handling"/"similar to Task N". Every code step shows complete code. The only intentionally data-dependent values are printed counts in Task 5 Step 6 (real numbers depend on the cache) — acceptable, the assertion is "non-zero".

**Type consistency:** `effectFor` returns `{ type, entry }`; `entityCard(type, entry)` consumes exactly that. `collectFromChar` writes `acc.runes[k].lines` / `acc.uniques[k].{base,mods,flavour}` / `acc.gems[k].{name,desc}`; `buildEffectsJson` reads those same fields and merges `gemInfo[k].{kind,tags}`; `entityCard` reads `entry.lines` / `entry.{base,mods,flavour}` / `entry.{kind,tags,desc}` / `entry.stats`. `normKey` (compiler) and `normKeyFE` (front end) implement identical rules. ✓

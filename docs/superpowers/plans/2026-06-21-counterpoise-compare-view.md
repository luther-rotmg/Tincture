# The Counterpoise (compare view) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add "The Counterpoise" — a client-only `index.html` section that compares 2–3 ascendancies side by side (vitals, defence layer, composition), sourced entirely from data already in memory.

**Architecture:** Pure helpers (hash parse/serialize, column view-model, shared-entry detector) are added to the inline `<script>` in `index.html` and locked with the existing source-extraction test harness (`tools/test-frontend.cjs`). A new `<section id="compare">` is rendered by `renderCompare()` from `META.byAsc` + the active league's build list; selection lives in a `compareSel` array driven by pickers, a per-ledger-row "vs" shortcut, and a `#compare=` URL hash. No backend, no new fetch, no new dependency.

**Tech Stack:** Vanilla JS + CSS in a single `index.html` (no framework, no build step). Node's built-in test runner (`node --test`) for the pure-helper locks. Python pipeline untouched.

## Global Constraints

(Every task implicitly includes these — copied from the spec + project ethos.)

- **No new dependencies, no build step.** Single-file `index.html` (HTML+CSS+JS inline). No libraries.
- **No browser storage** (no localStorage/IndexedDB). Shareable state lives only in the URL hash.
- **Fails safe.** A bad/missing field renders "—"; one malformed entry never aborts the view.
- **Honesty invariants.** Never fabricate a value. EHP/DPS keep the "median, where the source reports it" caveat. No declared overall "winner" — per-row higher-value highlight is a factual cue only, beside the note "higher isn't automatically better — survivability and damage trade off."
- **CSP-clean.** No new external resources; inline styles/scripts only (already permitted by the existing CSP meta). No `eval`, no new fetch.
- **Design tokens only.** Reuse the gold/oxblood/bone/verdigris vars + Cinzel/Spectral/IBM Plex Mono already defined at the top of `index.html`. No new colours/fonts.
- **Max 3 columns, min 2 to render.** Deep link format: `#compare=slugA,slugB[,slugC]`.
- **Slugs** are `slugOf({asc, skill})` = `` `${asc}-${skill||""}`.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"") ``. For a blank-skill ascendancy this is `asc`-slugged (matches `META.byAsc` keys).

---

### Task 1: Hash helpers — `parseCompareHash` + `compareHashOf`

**Files:**
- Modify: `index.html` (inline `<script>`, near the other deep-link helpers around the `#asc`/`writeAscHash` routing)
- Test: `tools/test-frontend.cjs` (append cases; extracts the helpers from `index.html` source)

**Interfaces:**
- Produces:
  - `parseCompareHash(hash: string, known: string[]) -> string[]` — parses `#compare=a,b,c` (or a bare `a,b,c`), lowercases/trims, drops slugs not in `known`, dedupes, caps at 3.
  - `compareHashOf(slugs: string[]) -> string` — returns `"#compare=" + slugs.slice(0,3).join(",")`, or `""` when empty.

- [ ] **Step 1: Write the failing tests**

Append to `tools/test-frontend.cjs` (before the final newline). It reuses the file's existing `extract()` + `html` (the source-extraction harness already at the top of that file):

```js
// --- The Counterpoise: hash helpers (Task 1) ---
const parseCompareHash = new Function('hash','known',
  extract(/function parseCompareHash\s*\([^)]*\)\s*\{([\s\S]*?)\n\}/, 'parseCompareHash'));
const compareHashOf = new Function('slugs',
  extract(/function compareHashOf\s*\([^)]*\)\s*\{([\s\S]*?)\n\}/, 'compareHashOf'));

test('parseCompareHash filters to known slugs, dedupes, caps at 3', () => {
  const known = ['titan','deadeye','oracle','lich'];
  assert.deepEqual(parseCompareHash('#compare=titan,deadeye', known), ['titan','deadeye']);
  assert.deepEqual(parseCompareHash('compare=titan,deadeye', known), ['titan','deadeye']); // tolerate missing #
  assert.deepEqual(parseCompareHash('#compare=TITAN, Deadeye ', known), ['titan','deadeye']); // case/space
  assert.deepEqual(parseCompareHash('#compare=titan,titan,deadeye', known), ['titan','deadeye']); // dedupe
  assert.deepEqual(parseCompareHash('#compare=titan,bogus,oracle', known), ['titan','oracle']); // unknown dropped
  assert.deepEqual(parseCompareHash('#compare=titan,deadeye,oracle,lich', known), ['titan','deadeye','oracle']); // cap 3
  assert.deepEqual(parseCompareHash('', known), []);
  assert.deepEqual(parseCompareHash('#compare=', known), []);
});

test('compareHashOf round-trips with parseCompareHash', () => {
  const known = ['titan','deadeye','oracle'];
  assert.equal(compareHashOf([]), '');
  assert.equal(compareHashOf(['titan','deadeye']), '#compare=titan,deadeye');
  assert.deepEqual(parseCompareHash(compareHashOf(['titan','deadeye','oracle']), known), ['titan','deadeye','oracle']);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test tools/test-frontend.cjs`
Expected: FAIL — `extract()` throws `front-end test could not find parseCompareHash in index.html` (the helpers don't exist yet).

- [ ] **Step 3: Add the helpers to `index.html`**

In the inline `<script>`, next to the deep-link routing (search for `writeAscHash` / `#asc=`), add two top-level functions. Their closing `}` MUST be at column 0 (so the test's `\n\}` extraction captures only the function body):

```js
// ---- The Counterpoise: compare-selection hash (URL-only, no storage) ----
function parseCompareHash(hash, known){
  const raw = String(hash == null ? "" : hash).replace(/^#?compare=/, "");
  const out = [];
  for (const part of raw.split(",")){
    const v = part.trim().toLowerCase();
    if (v && known.indexOf(v) >= 0 && out.indexOf(v) < 0) out.push(v);
    if (out.length >= 3) break;
  }
  return out;
}
function compareHashOf(slugs){
  return (slugs && slugs.length) ? "#compare=" + slugs.slice(0, 3).join(",") : "";
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test tools/test-frontend.cjs`
Expected: PASS (existing esc/fmt/relTime tests still pass; the two new tests pass).

- [ ] **Step 5: Commit**

```bash
git add index.html tools/test-frontend.cjs
git commit -m "feat(compare): #compare hash parse/serialize helpers + tests"
```

---

### Task 2: Column view-model — `ascForCompare` + `sharedCompareNames`

**Files:**
- Modify: `index.html` (inline `<script>`, near `metaFor`/`defenceHTML`)
- Test: `tools/test-frontend.cjs`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure).
- Produces:
  - `ascForCompare(slug, byAsc, build) -> column | null` — merges `byAsc[slug]` (stats/defence/composition) with the ledger `build` (cls/tag/pop/n). `column` shape:
    `{ slug, asc, cls, tag, pop, n, weapon, ehp, dps, level, def, skills[], supports[], uniques[], notables[] }`
    where each composition array is `[{name, pct}]` (top 3) and `def` is the `build.defence` object (or `{}`).
  - `sharedCompareNames(cols) -> { [name]: true }` — names appearing in the composition of **2+** columns.

- [ ] **Step 1: Write the failing tests**

Append to `tools/test-frontend.cjs`:

```js
// --- The Counterpoise: column model (Task 2) ---
const ascForCompare = new Function('slug','byAsc','build',
  extract(/function ascForCompare\s*\([^)]*\)\s*\{([\s\S]*?)\n\}/, 'ascForCompare'));
const sharedCompareNames = new Function('cols',
  extract(/function sharedCompareNames\s*\([^)]*\)\s*\{([\s\S]*?)\n\}/, 'sharedCompareNames'));

const BYASC = {
  titan: { asc:'Titan', stats:{ehp:45000,dps:120000,level:95},
    build:{defence:{ehp:45000,life:3000,es:0,resists:{fire:75,cold:75,lightning:75,chaos:30},evade:0,crit:0}},
    weapons:[{name:'Mace',pct:80}], skills:[{name:'Sunder',pct:60},{name:'Leap',pct:40},{name:'Warcry',pct:30},{name:'x',pct:1}],
    supports:[{name:'Brutality',pct:70}], uniques:[{name:'Widowhail',pct:50}], notables:[{name:'Resolute',pct:66}] },
  deadeye: { asc:'Deadeye', stats:{ehp:27000,dps:300000,level:94},
    build:{defence:{ehp:27000,life:1800,es:600,resists:{fire:75,cold:75,lightning:75,chaos:0},evade:60,crit:80}},
    weapons:[{name:'Bow',pct:90}], skills:[{name:'Lightning Arrow',pct:55}], supports:[{name:'Brutality',pct:40}],
    uniques:[{name:'Widowhail',pct:65}], notables:[{name:'Point Blank',pct:50}] },
};

test('ascForCompare merges byAsc + ledger build, takes top 3, null on unknown', () => {
  const col = ascForCompare('titan', BYASC, {asc:'Titan',cls:'Warrior',tag:'tanky slam',pop:12.3,n:400});
  assert.equal(col.asc, 'Titan');
  assert.equal(col.cls, 'Warrior');           // from ledger build (byAsc has no cls)
  assert.equal(col.tag, 'tanky slam');
  assert.equal(col.ehp, 45000);
  assert.equal(col.dps, 120000);
  assert.equal(col.weapon, 'Mace');
  assert.equal(col.def.resists.chaos, 30);
  assert.equal(col.skills.length, 3);          // capped at top 3 even though 4 provided
  assert.equal(col.n, 400);
  assert.equal(ascForCompare('nope', BYASC, null), null);
});

test('ascForCompare tolerates a missing ledger build (cls/tag/pop null)', () => {
  const col = ascForCompare('deadeye', BYASC, null);
  assert.equal(col.asc, 'Deadeye');
  assert.equal(col.cls, null);
  assert.equal(col.pop, null);
  assert.equal(col.ehp, 27000);
});

test('sharedCompareNames flags names in 2+ columns only', () => {
  const a = ascForCompare('titan', BYASC, null);
  const b = ascForCompare('deadeye', BYASC, null);
  const shared = sharedCompareNames([a, b]);
  assert.equal(shared['Widowhail'], true);     // unique in both
  assert.equal(shared['Brutality'], true);     // support in both
  assert.ok(!shared['Sunder']);                // only in titan
  assert.ok(!shared['Bow']);                   // weapons are not part of composition overlap
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test tools/test-frontend.cjs`
Expected: FAIL — `could not find ascForCompare in index.html`.

- [ ] **Step 3: Add the helpers to `index.html`**

Near `metaFor`/`defenceHTML` (top-level, closing `}` at column 0):

```js
// ---- The Counterpoise: per-column view-model + shared-entry detector ----
function ascForCompare(slug, byAsc, build){
  const md = byAsc && byAsc[slug];
  if (!md) return null;
  const d = (md.build && md.build.defence) || {};
  const top = arr => (arr || []).slice(0, 3).map(x => ({ name: x.name, pct: x.pct }));
  return {
    slug: slug,
    asc: md.asc || (build && build.asc) || slug,
    cls: (build && build.cls) || md.cls || null,
    tag: (build && build.tag) || null,
    pop: build ? build.pop : null,
    n: build ? build.n : null,
    weapon: (md.weapons && md.weapons[0] && md.weapons[0].name) || null,
    ehp: (md.stats && md.stats.ehp) || d.ehp || null,
    dps: (md.stats && md.stats.dps) || null,
    level: (md.stats && md.stats.level) || null,
    def: d,
    skills: top(md.skills), supports: top(md.supports),
    uniques: top(md.uniques), notables: top(md.notables),
  };
}
function sharedCompareNames(cols){
  const seen = {}, shared = {};
  for (const c of (cols || [])){
    if (!c) continue;
    const names = [].concat(c.skills || [], c.supports || [], c.uniques || [], c.notables || [])
      .map(x => x && x.name).filter(Boolean);
    const uniq = Array.from(new Set(names));
    for (const nm of uniq){ if (seen[nm]) shared[nm] = true; seen[nm] = true; }
  }
  return shared;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test tools/test-frontend.cjs`
Expected: PASS (all prior + 3 new tests).

- [ ] **Step 5: Commit**

```bash
git add index.html tools/test-frontend.cjs
git commit -m "feat(compare): ascForCompare column model + shared-entry detector + tests"
```

---

### Task 3: Section markup + `compareTableHTML` + `renderCompare` + desktop CSS

**Files:**
- Modify: `index.html` — add a `<section id="compare">` near The Assay; add `compareTableHTML(slugs)`, `renderCompare()`; add CSS in the `<style>` block (using existing tokens).

**Interfaces:**
- Consumes: `ascForCompare`, `sharedCompareNames` (Task 2); globals `META`, `curLeague()`, `slugOf`, `fmt`, `esc`, `decant`.
- Produces:
  - `compareTableHTML(slugs: string[]) -> string` — the comparison table markup (or empty string if `< 2` resolvable columns).
  - `renderCompare()` — fills `#compare` section content from `compareSel` (declared here as `let compareSel = []`), showing the prompt when `< 2`.
  - global `let compareSel = []`.

- [ ] **Step 1: Add the section markup**

Add near the Assay section (search `id="assay"`), after it:

```html
<section class="section-frame counterpoise" id="compare" aria-label="Compare ascendancies side by side">
  <header class="section-head">
    <h2>The Counterpoise</h2>
    <p class="section-sub">Weigh two or three ascendancies against each other — vitals, defences, and the build behind each. Higher isn't automatically better; survivability and damage trade off.</p>
  </header>
  <div class="cmp-pickers" id="cmpPickers" role="group" aria-label="Choose ascendancies to compare"></div>
  <div class="cmp-table-wrap" id="cmpTable"></div>
</section>
```

- [ ] **Step 2: Add `compareTableHTML` + `renderCompare` + `compareSel`**

In the inline `<script>` (near `renderAssay`):

```js
let compareSel = [];   // up to 3 slugs; URL-hash-backed, no storage

function compareTableHTML(slugs){
  const builds = (curLeague().builds || []);
  const bySlug = {};
  builds.forEach(b => { bySlug[slugOf(b)] = b; });
  const cols = (slugs || []).map(s => ascForCompare(s, META && META.byAsc, bySlug[s])).filter(Boolean);
  if (cols.length < 2) return "";
  const shared = sharedCompareNames(cols);

  // pick the column index with the max numeric value (for the factual higher-value accent)
  const maxIdx = vals => { let mi = -1, mv = -Infinity; vals.forEach((v,i)=>{ if (v != null && v > mv){ mv = v; mi = i; } }); return mi; };
  const numRow = (label, vals, fmtFn) => {
    const mi = maxIdx(vals);
    const tds = vals.map((v,i)=>`<td class="${i===mi?'cmp-best':''}">${v==null?'—':(fmtFn?fmtFn(v):fmt(v))}</td>`).join("");
    return `<tr><th scope="row">${label}</th>${tds}</tr>`;
  };
  const resRow = key => numRow(key[0].toUpperCase()+key.slice(1)+" res",
    cols.map(c => c.def && c.def.resists ? c.def.resists[key] : null),
    v => `${v}%${v>=75?' ✓':''}`);
  const listRow = (label, pick) => `<tr><th scope="row">${label}</th>` +
    cols.map(c => `<td>${(pick(c)||[]).map(x=>`<span class="cmp-ent${shared[x.name]?' cmp-shared':''}" title="${esc(x.name)} — ${x.pct}% of this ascendancy">${esc(x.name)}</span>`).join("")||'—'}</td>`).join("") + `</tr>`;

  const head = `<tr><td class="cmp-corner"></td>${cols.map(c=>`<th scope="col" class="cmp-colhead">
      <div class="cmp-asc">${esc(c.asc)}</div>
      <div class="cmp-meta">${esc(c.cls||'')}${c.tag?` · <i>${esc(c.tag)}</i>`:''}</div>
      <div class="cmp-meta">${c.weapon?esc(c.weapon):''}${c.n!=null?` · n=${fmt(c.n)}`:''}</div>
      <button class="decant sm cmp-decant" type="button" data-slug="${esc(c.slug)}">Decant</button>
    </th>`).join("")}</tr>`;

  return `<table class="cmp-table">
    <thead>${head}</thead>
    <tbody>
      ${numRow('Median EHP', cols.map(c=>c.ehp))}
      ${numRow('Median DPS', cols.map(c=>c.dps))}
      ${numRow('Level', cols.map(c=>c.level))}
      ${numRow('Life', cols.map(c=>c.def&&c.def.life))}
      ${numRow('Energy shield', cols.map(c=>c.def&&c.def.es))}
      ${resRow('fire')}${resRow('cold')}${resRow('lightning')}${resRow('chaos')}
      ${numRow('Evade', cols.map(c=>c.def&&c.def.evade), v=>`${v}%`)}
      ${numRow('Crit', cols.map(c=>c.def&&c.def.crit), v=>`${v}%`)}
      ${listRow('Top skills', c=>c.skills)}
      ${listRow('Top supports', c=>c.supports)}
      ${listRow('Signature uniques', c=>c.uniques)}
      ${listRow('Key notables', c=>c.notables)}
    </tbody>
  </table>
  <p class="cmp-foot">Medians, where the source reports them. Same ladder data as the ledger — nothing fabricated. The accent marks the higher number in a row, not a better build.</p>`;
}

function renderCompare(){
  const wrap = $("#cmpTable");
  if (!wrap) return;
  const html = compareTableHTML(compareSel);
  wrap.innerHTML = html || `<p class="cmp-empty">Pick two ascendancies above to weigh them against each other.</p>`;
  // decant from a column
  wrap.querySelectorAll(".cmp-decant").forEach(btn => btn.addEventListener("click", e => {
    e.stopPropagation();
    const b = (curLeague().builds||[]).find(x => slugOf(x) === btn.dataset.slug);
    if (b) decant(b);
  }));
}
```

(If the codebase uses a `$` selector helper, reuse it; otherwise use `document.getElementById`/`querySelector` as the surrounding code does.)

- [ ] **Step 3: Call `renderCompare()` on boot**

In `boot()`, after `META` is promoted and alongside `renderAssay()`/`renderExchange()`, add `renderCompare();`.

- [ ] **Step 4: Add desktop CSS** (in `<style>`, using existing tokens)

```css
  .counterpoise .cmp-table-wrap{ overflow-x:auto; }
  .cmp-table{ width:100%; border-collapse:collapse; font-size:13px; }
  .cmp-table th[scope="row"]{ text-align:left; color:var(--muted); font-family:var(--fmono); font-size:11px; letter-spacing:.04em; white-space:nowrap; padding:7px 12px 7px 0; position:sticky; left:0; background:var(--bg); z-index:1; }
  .cmp-table td{ padding:7px 14px; text-align:right; border-bottom:1px solid var(--hair); min-width:120px; }
  .cmp-table tbody tr:hover td, .cmp-table tbody tr:hover th{ background:rgba(200,162,74,.04); }
  .cmp-colhead{ text-align:right; vertical-align:bottom; padding:6px 14px 12px; border-bottom:1px solid var(--hair-strong); }
  .cmp-asc{ font-family:var(--fdisplay,Cinzel),serif; color:var(--gold-bright); font-size:15px; }
  .cmp-meta{ font-size:11px; color:var(--muted); }
  .cmp-corner{ border-bottom:1px solid var(--hair-strong); }
  td.cmp-best{ color:var(--gold-bright); font-weight:600; }
  .cmp-ent{ display:inline-block; margin:0 0 3px 6px; padding:2px 7px; border:1px solid var(--hair); border-radius:2px; font-size:11.5px; }
  .cmp-ent.cmp-shared{ border-color:var(--verdigris,#5b8a7e); color:var(--verdigris,#5b8a7e); }
  .cmp-foot, .cmp-empty{ color:var(--muted); font-size:11.5px; margin-top:12px; }
  .cmp-decant{ margin-top:8px; }
```

- [ ] **Step 5: Verify in preview**

Temporarily seed a selection to verify rendering before pickers exist:
- Start/confirm the preview server (`preview_list`; `preview_start name="tincture"` if needed).
- `preview_eval`: `compareSel = ['titan','deadeye']; renderCompare(); document.querySelectorAll('.cmp-table td').length` → expect > 0; and `document.querySelectorAll('.cmp-table .cmp-best').length` → ≥ 1; `document.querySelectorAll('.cmp-shared').length` → ≥ 0.
- `preview_console_logs level=error` → none.
- Confirm a shared unique (if any) is marked, EHP/DPS rows present, defence rows present.

(Use the real slugs present in `Object.keys(META.byAsc)` if titan/deadeye aren't in the current data.)

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "feat(compare): The Counterpoise section + table render + desktop styles"
```

---

### Task 4: Pickers + selection state + `#compare` hash routing

**Files:**
- Modify: `index.html` — `renderComparePickers()`, wire pickers→state→hash→render, integrate `#compare` into the hash router.

**Interfaces:**
- Consumes: `compareSel`, `renderCompare`, `parseCompareHash`, `compareHashOf`, `META.byAsc`.
- Produces: `renderComparePickers()`, `setCompareSel(slugs)`, `writeCompareHash()`; `#compare` handled in the existing hashchange routine.

- [ ] **Step 1: Add pickers + state mutators**

```js
function comparablesList(){   // [{slug, asc}] sorted by asc name
  const ba = (META && META.byAsc) || {};
  return Object.keys(ba).map(s => ({ slug: s, asc: ba[s].asc || s })).sort((a,b)=>a.asc.localeCompare(b.asc));
}
function renderComparePickers(){
  const host = $("#cmpPickers");
  if (!host) return;
  const opts = comparablesList();
  const slots = Math.min(3, Math.max(2, compareSel.length + (compareSel.length < 3 ? 1 : 0)));
  let html = "";
  for (let i = 0; i < slots; i++){
    const sel = compareSel[i] || "";
    html += `<select class="cmp-pick" data-i="${i}" aria-label="Comparison slot ${i+1}">`
      + `<option value="">${i < 2 ? "Pick an ascendancy…" : "+ add a third…"}</option>`
      + opts.map(o => `<option value="${esc(o.slug)}"${o.slug===sel?" selected":""}>${esc(o.asc)}</option>`).join("")
      + `</select>`;
  }
  host.innerHTML = html;
  host.querySelectorAll(".cmp-pick").forEach(sel => sel.addEventListener("change", () => {
    const picks = [...host.querySelectorAll(".cmp-pick")].map(s => s.value).filter(Boolean);
    setCompareSel(picks);
  }));
}
function setCompareSel(slugs){
  const known = (META && META.byAsc) ? Object.keys(META.byAsc) : [];
  const out = [];
  (slugs || []).forEach(s => { if (s && known.indexOf(s) >= 0 && out.indexOf(s) < 0 && out.length < 3) out.push(s); });
  compareSel = out;
  writeCompareHash();
  renderComparePickers();
  renderCompare();
}
function writeCompareHash(){
  const h = compareHashOf(compareSel);
  // URL-only, no history spam — match writeAscHash's approach
  history.replaceState(null, "", h || (location.pathname + location.search));
}
```

- [ ] **Step 2: Call `renderComparePickers()` on boot**

In `boot()`, beside the new `renderCompare();`, add `renderComparePickers();` (pickers first, then table).

- [ ] **Step 3: Integrate `#compare` into the hash router**

Find the function that reacts to the URL hash on boot and on `hashchange` (search `#asc`, `writeAscHash`, `addEventListener("hashchange"`). Add, where it dispatches on the hash:

```js
if (/^#?compare=/.test(location.hash)){
  const known = (META && META.byAsc) ? Object.keys(META.byAsc) : [];
  compareSel = parseCompareHash(location.hash, known);
  renderComparePickers();
  renderCompare();
}
```

Also, on boot (after META is ready), apply any incoming `#compare` once (the same three lines), so a shared link restores the selection.

- [ ] **Step 4: Verify in preview**

- Reload. `preview_eval`:
  - Set two pickers via JS: `(() => { const s=document.querySelectorAll('.cmp-pick'); s[0].value=Object.keys(META.byAsc)[0]; s[0].dispatchEvent(new Event('change')); s[1].value=Object.keys(META.byAsc)[1]; s[1].dispatchEvent(new Event('change')); return [compareSel, location.hash]; })()` → expect 2 slugs + `#compare=` hash.
  - Deep-link round-trip: `location.hash = '#compare=' + Object.keys(META.byAsc).slice(0,2).join(','); ` then reload and check `compareSel.length === 2` and the table rendered.
- `preview_console_logs level=error` → none.

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat(compare): pickers, selection state, and #compare deep-link routing"
```

---

### Task 5: Ledger row "vs" shortcut + mobile CSS + shared/honesty polish

**Files:**
- Modify: `index.html` — add the "vs" affordance in `renderRows()`; add mobile CSS; confirm honesty note + shared highlight read well.

**Interfaces:**
- Consumes: `setCompareSel`, `compareSel`, `slugOf`.

- [ ] **Step 1: Add the "vs" affordance in `renderRows()`**

In the row markup (search `renderRows`, near the per-row action area / `guide-link`), add an explicit element so the row-toggle handler ignores it (it already early-returns on `a`/`.arch-btn`):

```js
`<button class="vs-link" type="button" data-slug="${esc(slugOf(b))}" title="Add ${esc(b.asc)} to The Counterpoise comparison" aria-label="Compare ${esc(b.asc)}">vs</button>`
```

After rows are appended, wire it:

```js
rows.querySelectorAll(".vs-link").forEach(btn => btn.addEventListener("click", e => {
  e.stopPropagation();
  setCompareSel([...compareSel, btn.dataset.slug]);
  const sec = document.getElementById("compare");
  if (sec) sec.scrollIntoView({ behavior: "smooth", block: "start" });
}));
```

- [ ] **Step 2: Add mobile CSS** (in `<style>`)

```css
  .vs-link{ font-family:var(--fmono); font-size:10px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); background:none; border:1px solid var(--hair); border-radius:2px; padding:2px 6px; cursor:pointer; transition:color .18s, border-color .18s; }
  .vs-link:hover{ color:var(--gold-bright); border-color:var(--gold); }
  .cmp-pickers{ display:flex; flex-wrap:wrap; gap:10px; margin:4px 0 18px; }
  .cmp-pick{ min-height:36px; }
  @media (max-width:480px){
    .cmp-table td, .cmp-table th[scope="row"]{ padding:6px 10px; font-size:12px; }
    .cmp-table td{ min-width:104px; }
    .cmp-pickers{ gap:8px; }
    .cmp-pick{ flex:1 1 100%; }
    .vs-link{ min-height:32px; display:inline-flex; align-items:center; }
  }
```

- [ ] **Step 3: Verify in preview (desktop + mobile)**

- Reload. Click a `.vs-link` via `preview_eval` (`document.querySelector('.vs-link').click()`) → `compareSel` gains that slug; page scrolled to `#compare`.
- `preview_resize` to ~377px (or eval-set): confirm the label gutter stays pinned (`position:sticky` left col), 2 columns fit, a 3rd horizontal-scrolls within `.cmp-table-wrap`; pickers go full-width; touch targets ≥ 32–36px.
- `preview_console_logs level=error` → none. `preview_screenshot` for the record (best-effort).

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat(compare): ledger 'vs' shortcut + mobile sticky-gutter styles"
```

---

### Task 6: Full verification, JS syntax + test suite, merge to main

**Files:** none new — verification + integration.

- [ ] **Step 1: Inline-JS syntax check**

Run the project's inline-script parse check (extracts `<script>` blocks, skips `application/ld+json`, `vm.Script` each):

```bash
node -e 'const fs=require("fs"),vm=require("vm");const html=fs.readFileSync("index.html","utf8");const re=/<script\b([^>]*)>([\s\S]*?)<\/script>/gi;let m,n=0,bad=0;while((m=re.exec(html))){const a=m[1]||"",s=m[2];if(!s.trim())continue;const t=a.match(/type\s*=\s*["\x27]([^"\x27]+)/i);if(t&&!/javascript|module/i.test(t[1]))continue;n++;try{new vm.Script(s)}catch(e){bad++;console.log("PARSE ERR",e.message)}}console.log(bad?("FAIL "+bad+"/"+n):("OK "+n+" script(s)"))'
```
Expected: `OK 1 script(s)`.

- [ ] **Step 2: Full test suite green**

```bash
node --test tools/test-build-from-ninja.cjs tools/test-effects.cjs tools/test-contracts.cjs tools/test-frontend.cjs
python scripts/test_distill.py
```
Expected: Node all pass (incl. the 5 new compare tests); Python `OK`.

- [ ] **Step 3: End-to-end preview pass**

Confirm in the live preview, 0 console errors throughout:
- SPA boots; The Counterpoise section present and empty-prompt shows with `< 2` picks.
- Pick 2 via dropdowns → table renders; pick a 3rd → 3 columns.
- A ledger row "vs" link adds + scrolls.
- `#compare=a,b` deep link restores on reload.
- Decant from a column triggers the decant path.
- Shared composition entries highlighted; higher-value accent present; honesty foot-note shown.
- Mobile ~377px: sticky gutter + 3rd-column scroll; pickers full-width.
- CSP: no violations (no new external resources).

- [ ] **Step 4: Merge the feature branch to main**

Use `superpowers:finishing-a-development-branch` to decide merge vs PR. For this repo (direct-to-main pattern from the maintenance work, GitHub Pages live):

```bash
git checkout main && git fetch origin -q && git merge --ff-only origin/main
git checkout -- economy.json data.json 2>/dev/null || true   # drop CI-data drift; never commit it
git rebase main feature/counterpoise-compare
git checkout main && git merge --ff-only feature/counterpoise-compare
git push origin main
git branch -d feature/counterpoise-compare
```

- [ ] **Step 5: Post-merge confirmation**

- `gh run list --workflow=test.yml --limit 1` → the push's Tests run is `success` (CI runs node + python).
- Final preview boot on `main` → 0 console errors.
- Append a one-line entry to `.superpowers/sdd/autonomous-log.md` recording the feature shipped + commit.

---

## Self-Review

**Spec coverage:**
- Selection (section + pickers + row "vs") → Tasks 3,4,5. ✓
- Deep link `#compare` → Tasks 1,4. ✓
- Table: header/vitals/defence/composition → Task 3. ✓
- Shared-entry highlight → Tasks 2 (detector) + 3 (markup) + 5 (style). ✓
- Honesty (no winner, factual accent, median caveat, sample size) → Task 3 (`cmp-foot`, `cmp-best`, `n=`). ✓
- Mobile sticky gutter → Tasks 3 (sticky `th`) + 5 (media query). ✓
- Testing (pure helpers + preview) → Tasks 1,2 (unit) + 3,4,5,6 (preview). ✓
- Fail-safe ("—", `< 2` prompt, unknown-slug drop) → Tasks 1,2,3. ✓
- CSP-clean / no new deps → Task 6 verification. ✓

**Placeholder scan:** No TBD/TODO; all steps carry real code or exact commands. ✓

**Type consistency:** `compareSel` (string[]), `parseCompareHash(hash,known)`, `compareHashOf(slugs)`, `ascForCompare(slug,byAsc,build)→column`, `sharedCompareNames(cols)→{name:true}`, `compareTableHTML(slugs)→string`, `renderCompare()`, `renderComparePickers()`, `setCompareSel(slugs)`, `writeCompareHash()` — names/signatures consistent across tasks. ✓

**Note for implementer:** `$` is the codebase's selector helper if present; otherwise use `document.querySelector`/`getElementById` to match surrounding code. Confirm the real ascendancy slugs via `Object.keys(META.byAsc)` when seeding preview checks (titan/deadeye are illustrative).

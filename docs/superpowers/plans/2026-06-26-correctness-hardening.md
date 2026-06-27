# Correctness & Honesty Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix five audit-found correctness/honesty defects: relabel the mislabeled "24-hour" trend to "since last refresh" everywhere, make the Counterpoise per-column Decant work for all ascendancies, fix the variant fallback's dropped slug + all-null body, guard `relTime`/counters against "NaN", and add the missing >100%-share apportionment test.

**Architecture:** Each fix is a small, exact edit with a known before/after. Front-end edits (`index.html`) are browser-preview-verified (the project has **no JS unit harness**) by the controller during subagent execution. Docs edits (`README.md`, `CLAUDE.md`) are grep-verified. The Python test (`test_distill.py`) runs in CI (`test.yml`) — **Python is not installed locally**, so it is verified by construction against the existing test harness, not a local run.

**Tech Stack:** Vanilla inline CSS/HTML/JS in one `index.html`; Markdown docs; stdlib `unittest` Python; browser preview (`.claude/launch.json` server "tincture", port 8099).

## Global Constraints

- **Honesty:** **no "24-hour"/"24h" trend claim may survive** anywhere user-facing (UI, CSV, JSON-LD, README) — the delta is a since-last-refresh diff. The variant/synthesized fallback stays a clearly-labelled non-loadable `.txt` (banner + `.txt` suffix + toast); fixes are additive and never fabricate a `.build` or a share number.
- **Scope:** `index.html`, `README.md`, `CLAUDE.md`, `scripts/test_distill.py`. **No change to `scripts/distill.py`** (the "24h docstring" was a phantom — it doesn't exist; `apply_trends` already says "previous snapshot"). No change to the delta math, the ledger ranking, or the Decant/build-view happy path.
- **Additive only:** B inserts a guarded `else` branch (top-N Decant path byte-identical); C only edits the post-`real==null` fallback (line 1695 `saveRealBuild` untouched). Never fabricate.
- **Commit scope:** stage only the files each task names (`git add <files>`) — the working tree may carry an unrelated modified `economy.json`; never stage it.
- **Branch:** `feature/correctness-hardening` (stacked on `feature/look-feel-voice`). Commit after every task.

---

### Task 1: A — Relabel the trend ("since last refresh", not 24h)

**Files:** Modify `index.html` (8 sites), `README.md` (4 lines), `CLAUDE.md` (1 line)

- [ ] **Step 1: index.html — the seven UI/metadata labels + the export field**

Apply these exact find/replace edits (match the distinctive substring; the curly quotes ‘ ’ in the first are literal — copy them exactly):

1. Line ~1141: `Change in share over 24 hours. Reads ‘baseline’` → `Change in share since the last refresh. Reads ‘baseline’`
2. Line ~2281: `title="24-hour trends appear once enough hourly snapshots accumulate"` → `title="trends appear once enough hourly snapshots accumulate"`
3. Line ~2377: `Trend = 24-hour change in share.` → `Trend = change in share since the last refresh.`
4. Line ~2877: `"trend_24h"` → `"trend_since_refresh"`
5. Line ~2908: `24-hour trends read <b>baseline</b> until enough snapshots accumulate.` → `Trends read <b>baseline</b> until enough snapshots accumulate.`
6. Line ~36 (JSON-LD description): `24h trends` → `since-last-refresh trends`
7. Line ~1356 (data-access footer): `24-hour trends sit at baseline` → `Trends sit at baseline`
8. Line ~1619 (export field key): `trend24h: b.delta ?? null,` → `trendSinceRefresh: b.delta ?? null,` (safe — sole occurrence, zero readers)

- [ ] **Step 2: README.md — four published lines**

1. Line ~17: `24-hour trend arrows that light up once a day` → `trend arrows that light up once a day`
2. Line ~33: `computes each build's 24-hour movement by diffing` → `computes each build's movement since the last refresh by diffing`
3. Line ~119: `for the 24-hour trend arrows.` → `for the trend arrows.`
4. Line ~133: `ascendancy shares + 24h trend)` → `ascendancy shares + since-last-refresh trend)`

- [ ] **Step 3: CLAUDE.md — the source of the mislabel premise**

In the Pipeline bullet: `24h trend deltas (diff vs previous snapshot)` → `since-last-snapshot trend deltas (diff vs previous snapshot)`

- [ ] **Step 4: Verify**

Run: `grep -niE "24[ -]?h(our)?[^a-z]*(trend|change|movement)|trend[^a-z]*24" index.html README.md CLAUDE.md`
Expected: **no matches** (every trend "24-hour"/"24h" reference is gone). Then in the browser preview, reload `http://localhost:8099`: the ledger "Trend" hint tooltip reads "since the last refresh"; the ledger foot reads "Trend = change in share since the last refresh."; the Cellar disclaimer reads "Trends read baseline…"; export a CSV and confirm the header column is `trend_since_refresh`. 0 console errors.

- [ ] **Step 5: Commit**
```bash
git add index.html README.md CLAUDE.md
git commit -m "fix(honesty): relabel the trend 'since last refresh' (it's a 1h delta, not 24h) across UI/CSV/JSON-LD/README"
```

---

### Task 2: B — Counterpoise per-column Decant for all ascendancies

**Files:** Modify `index.html` (`renderCompare` `.cmp-decant` handler, ~2165-2169)

**Interfaces:** Consumes `decant(b, slugOverride)` (async, index.html:1679 — manifest-gates the override slug, serves real `.build` or honest `.txt`), `META.byAsc[slug]` (has `asc`, no `cls`), `slugOf`, `curLeague`.

- [ ] **Step 1: Replace the handler body**

Find (index.html:2165-2169):
```js
  wrap.querySelectorAll(".cmp-decant").forEach(btn => btn.addEventListener("click", e => {
    e.stopPropagation();
    const b = (curLeague().builds||[]).find(x => slugOf(x) === btn.dataset.slug);
    if (b) decant(b);
  }));
```
Replace with:
```js
  wrap.querySelectorAll(".cmp-decant").forEach(btn => btn.addEventListener("click", e => {
    e.stopPropagation();
    const slug = btn.dataset.slug;
    const b = (curLeague().builds||[]).find(x => slugOf(x) === slug);
    if (b) { decant(b); return; }
    // not in the active top-N ledger (one of the non-ranked ascendancies): synthesize a pick
    // from its meta-detail entry and let decant() manifest-gate the slug (real .build or honest .txt).
    const md = META && META.byAsc && META.byAsc[slug];
    if (md) decant({ asc: md.asc, skill: "" }, slug);
  }));
```
(The top-N path `if (b) { decant(b); return; }` is the unchanged happy path. `META.byAsc` carries no `cls`, so the stub is `{ asc, skill:"" }`. If `md` is absent the branch is a guarded no-op — no throw.)

- [ ] **Step 2: Verify in preview**

Reload. Open The Counterpoise; pick a top-N ascendancy and one that is NOT in the active ledger's top-N (e.g. compare Deadeye with Pathfinder/Amazon/Shaman — any column whose ascendancy isn't a ranked ledger row). Click the **non-top-N** column's "Decant" button → it now Decants (saves a real `.build` if reconstructed, else the honest `-tincture-template.txt`), instead of doing nothing. The top-N column's Decant still works. 0 console errors. (Confirm via `preview_console_logs` + a `preview_network`/download check, or eval that the click path reaches `decant`.)

- [ ] **Step 3: Commit**
```bash
git add index.html
git commit -m "fix(ui): Counterpoise Decant works for non-top-N ascendancies (was a silent no-op)"
```

---

### Task 3: C — Variant fallback names the real pick + carries real fields

**Files:** Modify `index.html` (`decant()` honest-fallback tail, ~1695-1698)

**Interfaces:** Consumes the override-aware local `slug` (index.html:1680, `const slug = slugOverride || slugOf(b)`), `templateText(b)`, `slugOf`, `curLeague`. `b` is the (reassignable) function parameter.

- [ ] **Step 1: Enrich the stub + use the override slug in the filename**

Find (index.html:1695-1697):
```js
  if (real != null) return saveRealBuild(b, real, slug + ".build");
  // honest fallback: a labelled meta template (.txt) — never the game's .build slot
  saveBlob(templateText(b), slugOf(b) + "-tincture-template.txt", "text/plain;charset=utf-8");
```
Replace with:
```js
  if (real != null) return saveRealBuild(b, real, slug + ".build");
  // honest fallback: a labelled meta template (.txt) — never the game's .build slot.
  // enrich a stub pick (variant / non-top-N compare) from its ascendancy's ledger row so the
  // template carries real share/playstyle instead of all-null; name the file with the real slug.
  const lrow = (curLeague().builds||[]).find(x => slugOf(x) === slugOf(b));
  if (lrow) b = { ...lrow, ...b };
  saveBlob(templateText(b), slug + "-tincture-template.txt", "text/plain;charset=utf-8");
```
(Only `slugOf(b)` → `slug` on the filename, plus the two enrich lines. The `saveRealBuild` happy path on 1695 and the toast below are untouched. A variant's asc == its primary's asc, so the asc-slug ledger lookup pulls the correct fields; for a non-top-N pick there is no ledger row, so share fields stay null — honest.)

- [ ] **Step 2: Verify (inspection + forced fallback)**

The fallback only fires when a pick's real `.build` is unavailable. In the preview console, force it for a variant: pick a slug whose `.build` you block, e.g. run `decant({asc:"Deadeye", skill:""}, "deadeye-2")` after temporarily making `builds/deadeye-2.build` 404 (or eval `decant` with a slug known to lack a file). Confirm the downloaded file is named **`deadeye-2-tincture-template.txt`** (the `-2` suffix preserved, not `deadeye-...`), and that its body shows the Deadeye ascendancy's real `metaSharePct`/playstyle (enriched from the ledger), not all-null. Confirm the NOT-loadable banner + the "starter (.txt) … No loadable build for this exact pick yet" toast still appear. 0 console errors.

- [ ] **Step 3: Commit**
```bash
git add index.html
git commit -m "fix(ui): variant fallback keeps the -N slug + enriches the template (was base-slug, all-null)"
```

---

### Task 4: D — `relTime` NaN guard + the sibling counter guard

**Files:** Modify `index.html` (`relTime` ~1566, `animateCounters` ~2940)

- [ ] **Step 1: Guard `relTime`**

Find (index.html:1569 — the first computed line inside `relTime`):
```js
  const diff = Math.max(0, Date.now() - new Date(iso).getTime());
```
Replace with (insert the guard line above it):
```js
  if (!iso || isNaN(new Date(iso).getTime())) return "—";
  const diff = Math.max(0, Date.now() - new Date(iso).getTime());
```
(Mirrors `absTime`'s `isNaN` guard; the `"—"` sentinel reads correctly at the callers — "refreshed —", "reconstructed —", "as of —".)

- [ ] **Step 2: Guard `animateCounters`**

Find (index.html:2940): `  const target = +el.dataset.count;`
Replace: `  const target = +el.dataset.count || 0;`
(Matches the already-guarded reduced-motion path at ~2456 `fmt(+el.dataset.count || 0)`; prevents a "NaN" counter if `data-count` is ever absent/malformed.)

- [ ] **Step 3: Verify in preview**

Reload. In the console: `relTime("not-a-date")` → returns `"—"` (never "NaN"); `relTime("")` → `"—"`; `relTime(new Date().toISOString())` → a normal "just now"/"N min ago". Then `(function(){const d=document.createElement('div');d.className='still-count';document.body.appendChild(d);})()` is unnecessary — instead just confirm the existing counters in The Still render numbers (not "NaN") on load. 0 console errors.

- [ ] **Step 4: Commit**
```bash
git add index.html
git commit -m "fix(ui): relTime returns '—' (not 'NaN') on a bad timestamp; guard animateCounters target"
```

---

### Task 5: E — Apportionment >100%-share test

**Files:** Modify `scripts/test_distill.py` (add a method to the existing `Apportion` class, ~line 300)

**Interfaces:** Consumes `distill.normalize_one(league_dict) -> (rows, total)` (the only caller of the private `_apportion_n(rows, total)` at distill.py:296; the clamp `target = min(total, round(sum(exacts)))` is at distill.py:313). This is a **characterization/regression test** — it locks behavior the current code already satisfies, so it passes immediately (no RED phase).

- [ ] **Step 1: Add the test method**

In `scripts/test_distill.py`, inside the existing `class Apportion(unittest.TestCase):` (after `test_derived_n_never_sums_above_total`), add:
```python
    def test_derived_n_clamped_when_shares_exceed_100(self):
        # poe.ninja top-N shares can sum to >100% (overlapping categories + independent rounding);
        # the apportionment clamp (target = min(total, round(sum(exacts)))) must never let the
        # derived sample counts inflate past the real ladder population.
        league = {"total": 1000, "statistics": [
            {"class": "Titan", "percentage": 25.0}, {"class": "Deadeye", "percentage": 25.0},
            {"class": "Lich", "percentage": 25.0}, {"class": "Invoker", "percentage": 25.0},
            {"class": "Infernalist", "percentage": 25.0}]}   # shares sum to 125%
        rows, total = distill.normalize_one(league)
        self.assertLessEqual(sum(r["n"] for r in rows), total)
```
(Uses real mapped ascendancies — Titan/Deadeye/Lich/Invoker/Infernalist are all in `ASC_TO_CLASS` — to avoid the unmapped-class stderr warning. Mirrors the existing `test_derived_n_never_sums_above_total` style exactly.)

- [ ] **Step 2: Verify**

If `python` is available locally: `python scripts/test_distill.py` → all tests pass including `test_derived_n_clamped_when_shares_exceed_100`. **If Python is not installed locally** (expected for this project), verify by construction: the new method is inside the `Apportion` class, calls the same `distill.normalize_one` entry point the sibling tests use, and asserts `sum(n) <= total` — the clamp at distill.py:313 guarantees this. CI (`.github/workflows/test.yml`) runs the suite on the commit. State clearly in the report whether the local run was possible.

- [ ] **Step 3: Commit**
```bash
git add scripts/test_distill.py
git commit -m "test(distill): lock the >100%-share apportionment clamp (sum(n) <= total)"
```

---

## Self-Review

**Spec coverage:** A → Task 1 (index.html 8 sites + README 4 + CLAUDE.md 1; no distill.py per the dropped phantom); B → Task 2; C → Task 3; D → Task 4 (relTime + animateCounters); E → Task 5. All spec items mapped.

**Placeholder scan:** none — every edit has the exact find/replace text or full before/after block, plus a concrete verify step with expected output.

**Consistency:** the field rename is `trend24h`→`trendSinceRefresh` (Task 1 step 1.8); B uses `decant({asc, skill:""}, slug)` matching the real signature `decant(b, slugOverride)` (no `cls`, since `META.byAsc` lacks it); C uses the override-aware local `slug` (defined at 1680) for the filename and reassigns the param `b`; E calls `distill.normalize_one` (the real public entry) and asserts against `total` (its second return value). The honesty constraints (no 24-hour survives; fallback stays a labelled non-loadable `.txt`; no fabrication) hold across Tasks 1/2/3.

**Execution note:** Tasks 1-4 are browser-preview-verified by the controller after each commit (subagent edits + commits the named files; controller reloads :8099 + runs the verify step + checks console). Task 5 is CI-verified (no local Python). B and C touch the Decant area but different functions (`renderCompare` vs `decant`) and only their non-happy-path branches — independently reviewable.

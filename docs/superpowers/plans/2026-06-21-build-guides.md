# Curated build guides Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a hand-curated community-guide link per ascendancy (honest "a community guide", neutral-search fallback) plus an automated staleness reminder, all static/no-backend.

**Architecture:** A committed `guides.json` (curated, with an `unguided` allowlist) is read at boot into a `GUIDES` global; the existing per-row `.guide-link` becomes `guideLinkHTML(b)` which renders the curated link when present, else the current neutral search. `scripts/distill.py` gains pure, tested helpers (`guides_schema_errors`, `untriaged_guides`) that drive a CI coverage test (fails on an *untriaged* ascendancy) and a non-blocking hourly warning.

**Tech Stack:** Vanilla JS + CSS in `index.html`; stdlib Python pipeline; `node --test` + Python `unittest`. No new deps.

## Global Constraints
- No new dependencies, no build step, no backend, no browser storage; single-file `index.html`; fails safe.
- **No scraping / republishing guide content** — only *links*, with `source` attribution.
- Honesty copy: render as **"{source} guide ↗"** with title **"A community guide for {asc} by {source} — a pointer, not an endorsement; may lag the latest patch"**. Never "best guide". Neutral search stays the fallback.
- `guides.json` shape: `{ "patch": str, "updated": str, "guides": { "<slug>": {"url": str, "source": str} }, "unguided": [str] }`. Slugs are `slugify_asc(asc)` (Python) ≡ `slugOf({asc, skill:""})` (FE) = the ascendancy name slugified.
- A missing guide must **never fail the hourly run** (soft warning only); CI coverage failure is only for *untriaged* (in neither `guides` nor `unguided`) live ascendancies.
- All FE URLs `esc()`-d; outbound links keep `target="_blank" rel="noopener noreferrer"`.

---

### Task 1: Pure pipeline helpers — `guides_schema_errors` + `untriaged_guides` (TDD)

**Files:**
- Modify: `scripts/distill.py` (add two pure functions near `slugify_asc`, ~line 483)
- Test: `scripts/test_distill.py` (new test class)

**Interfaces:**
- Produces:
  - `guides_schema_errors(doc) -> list[str]` — human-readable problems; `[]` means valid. Checks: `doc` is a dict; `guides` is a dict of `{url, source}` with http(s) `url` and non-empty `source`; `unguided` (if present) is a list of strings; no slug appears in both `guides` and `unguided`.
  - `untriaged_guides(payload, doc) -> list[str]` — sorted slugs of **live** (non-`curated`) ascendancies in the payload's default league that are in neither `doc["guides"]` nor `doc["unguided"]`.

- [ ] **Step 1: Write the failing tests**

Add to `scripts/test_distill.py` (new class, after an existing one):

```python
class Guides(unittest.TestCase):
    def test_schema_errors_catches_bad_entries(self):
        ok = {"patch":"0.5.0","guides":{"deadeye":{"url":"https://x.gg","source":"Maxroll"}},"unguided":["lich"]}
        self.assertEqual(distill.guides_schema_errors(ok), [])
        bad = {"guides":{"deadeye":{"url":"ftp://x","source":""}, "titan":{"source":"M"}}, "unguided":"nope"}
        errs = distill.guides_schema_errors(bad)
        self.assertTrue(any("deadeye" in e for e in errs))   # bad url + empty source
        self.assertTrue(any("titan" in e for e in errs))     # missing url
        self.assertTrue(any("unguided" in e for e in errs))  # not a list
        # a slug in both guides and unguided is an error
        both = {"guides":{"deadeye":{"url":"https://x","source":"M"}}, "unguided":["deadeye"]}
        self.assertTrue(any("both" in e.lower() for e in distill.guides_schema_errors(both)))

    def test_untriaged_lists_only_unhandled_live_ascendancies(self):
        payload = {"default":"sc","leagues":[
            {"url":"sc","builds":[{"asc":"Deadeye"},{"asc":"Titan"},{"asc":"Smith of Kitava"}]},
            {"url":"std","curated":True,"builds":[{"asc":"Lich"}]},
        ]}
        doc = {"guides":{"deadeye":{"url":"https://x","source":"M"}}, "unguided":["titan"]}
        # Deadeye guided, Titan unguided, Smith untriaged, Lich is curated-only (ignored)
        self.assertEqual(distill.untriaged_guides(payload, doc), ["smith-of-kitava"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/test_distill.py`
Expected: FAIL — `AttributeError: module 'distill' has no attribute 'guides_schema_errors'`.

- [ ] **Step 3: Implement the helpers in `scripts/distill.py`** (place right after `slugify_asc`)

```python
def guides_schema_errors(doc):
    """Return a list of human-readable problems with a guides.json doc; [] means valid."""
    errs = []
    if not isinstance(doc, dict):
        return ["guides.json is not an object"]
    guides = doc.get("guides")
    if not isinstance(guides, dict):
        errs.append("'guides' is missing or not an object")
        guides = {}
    for slug, e in guides.items():
        if not isinstance(e, dict):
            errs.append(f"guides['{slug}'] is not an object"); continue
        url = e.get("url")
        if not (isinstance(url, str) and (url.startswith("http://") or url.startswith("https://"))):
            errs.append(f"guides['{slug}'] has a missing/invalid url")
        if not (isinstance(e.get("source"), str) and e.get("source").strip()):
            errs.append(f"guides['{slug}'] has a missing/empty source")
    ung = doc.get("unguided", [])
    if not isinstance(ung, list) or not all(isinstance(s, str) for s in ung):
        errs.append("'unguided' must be a list of slug strings")
        ung = [s for s in (ung if isinstance(ung, list) else []) if isinstance(s, str)]
    both = set(guides) & set(ung)
    if both:
        errs.append(f"slug(s) in both guides and unguided: {sorted(both)}")
    return errs


def untriaged_guides(payload, doc):
    """Sorted slugs of live (non-curated) default-league ascendancies handled by neither
    guides nor unguided — i.e. new ascendancies that need a curation decision."""
    guides = (doc.get("guides") or {}) if isinstance(doc, dict) else {}
    ung = set((doc.get("unguided") or []) if isinstance(doc, dict) else [])
    handled = set(guides) | ung
    default_url = payload.get("default")
    out = set()
    for lg in payload.get("leagues", []):
        if lg.get("url") != default_url or lg.get("curated"):
            continue
        for b in lg.get("builds", []):
            asc = b.get("asc")
            if asc:
                slug = slugify_asc(asc)
                if slug not in handled:
                    out.add(slug)
    return sorted(out)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/test_distill.py`
Expected: `OK` (all prior + the 2 new tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/distill.py scripts/test_distill.py
git commit -m "feat(guides): pure guides.json schema + untriaged helpers + tests"
```

---

### Task 2: Curate + create `guides.json`, lock coverage in CI

**Files:**
- Create: `guides.json` (repo root)
- Test: `scripts/test_distill.py` (coverage-lock test reading the shipped file)

**Interfaces:**
- Consumes: `guides_schema_errors`, `untriaged_guides` (Task 1); `slugify_asc`.

- [ ] **Step 1: Research the live ascendancies (controller does this)**

List the default-league ascendancies:
`python -c "import json;d=json.load(open('data.json'));lg=[l for l in d['leagues'] if l['url']==d['default']][0];print([b['asc'] for b in lg['builds']])"`
For each, WebSearch `"Path of Exile 2" 0.5.0 <Ascendancy> build guide` (or "Runes of Aldur <Ascendancy>"); open the top reputable result (Maxroll, Mobalytics, established creators); confirm it is current for 0.5.0 and about that ascendancy. Record `{url, source}`. Where no solid current guide exists, add the slug to `unguided` instead.

- [ ] **Step 2: Write `guides.json`** (example shape — real URLs from Step 1)

```json
{
  "patch": "0.5.0",
  "updated": "2026-06-21",
  "guides": {
    "deadeye": { "url": "https://maxroll.gg/poe2/build-guides/…", "source": "Maxroll" }
  },
  "unguided": []
}
```
Every default-league ascendancy slug must be in `guides` or `unguided`.

- [ ] **Step 3: Write the coverage-lock test** (append to `class Guides`)

```python
    def test_shipped_guides_json_valid_and_complete(self):
        import os
        path = os.path.join(os.path.dirname(__file__), "..", "guides.json")
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        self.assertEqual(distill.guides_schema_errors(doc), [])
        # the demo payload is what distill --demo produces; every live ascendancy must be triaged
        payload = json.load(open(os.path.join(os.path.dirname(__file__), "..", "data.json"), encoding="utf-8"))
        self.assertEqual(distill.untriaged_guides(payload, doc), [],
                         "every live ascendancy must be in guides or unguided — add the new one(s)")
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/test_distill.py`
Expected: `OK` (fails first if a slug is untriaged — fix `guides.json`, re-run).

- [ ] **Step 5: Commit**

```bash
git add guides.json scripts/test_distill.py
git commit -m "feat(guides): curated guides.json + coverage-lock test"
```

---

### Task 3: Wire the non-blocking hourly warning into `distill.py`

**Files:**
- Modify: `scripts/distill.py` (`warn_missing_guides` + a call in the live run path)

**Interfaces:**
- Consumes: `untriaged_guides`, `guides_schema_errors` (Task 1).
- Produces: `warn_missing_guides(payload)` — reads `guides.json`, prints warnings to stderr, returns the untriaged list; never raises.

- [ ] **Step 1: Implement `warn_missing_guides`** (in `scripts/distill.py`, near the other write_/warn helpers)

```python
def warn_missing_guides(payload):
    """Non-blocking: log new/un-triaged ascendancies + patch drift for guides.json. Never raises."""
    try:
        path = os.path.join(ROOT, "guides.json")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        for e in guides_schema_errors(doc):
            print(f"[warn] guides.json: {e}", file=sys.stderr)
        missing = untriaged_guides(payload, doc)
        for slug in missing:
            print(f"[warn] ascendancy '{slug}' is in the meta but has no guide "
                  f"(add it to guides.json or its unguided list)", file=sys.stderr)
        gp, dp = doc.get("patch"), payload.get("patch")
        if gp and dp and gp != dp:
            print(f"[warn] guides.json patch {gp} is behind data.json patch {dp} — re-vet the guides",
                  file=sys.stderr)
        return missing
    except Exception as e:  # noqa: BLE001
        print(f"[warn] could not check guides.json: {e}", file=sys.stderr)
        return []
```
(Confirm `import sys` and `ROOT` exist at the top of distill.py — they do; reuse them.)

- [ ] **Step 2: Call it in the live run** — find `run_live` (or the main live path that writes data.json) and add, after `data.json` is written / `payload` is final:

```python
    warn_missing_guides(payload)
```

- [ ] **Step 3: Verify offline** — `python scripts/distill.py --demo` runs clean (the warning prints only if the demo payload has an untriaged ascendancy, which Task 2 ensured it doesn't → no warning). Then a quick check it doesn't raise:

Run: `python -c "import sys; sys.argv=['x']; import scripts.distill as d" 2>/dev/null || python scripts/test_distill.py`
Expected: `OK` (tests still green; no import/syntax error).

- [ ] **Step 4: Commit**

```bash
git add scripts/distill.py
git commit -m "feat(guides): non-blocking hourly warning for un-triaged/stale guides"
```

---

### Task 4: Front end — fetch `guides.json` + `guideLinkHTML(b)`

**Files:**
- Modify: `index.html` — boot fetch + `GUIDES` global + `guideLinkHTML(b)` replacing the inline `.guide-link`.

**Interfaces:**
- Consumes: `slugOf`, `esc`, `guideUrl` (existing); `GUIDES`.
- Produces: `let GUIDES = null`; `guideLinkHTML(b) -> string`.

- [ ] **Step 1: Add `GUIDES` global** near `let LANDING = null;` (search it):

```js
let GUIDES = null;         // guides.json: curated community-guide link per ascendancy slug
```

- [ ] **Step 2: Fetch `guides.json` at boot** — in the enrichment `Promise.all` (search `fetchJSON("b/index.json"`), add a slot and promote:

```js
    fetchJSON("guides.json", 8000, "default"),
```
and after the destructure (where `LANDING` is set):

```js
  if (gd && gd.guides) GUIDES = gd;   // shape-gate before promoting (neutral search if absent)
```
(Add `gd` as the matching new destructured variable in the `const [...] = await Promise.all([...])`.)

- [ ] **Step 3: Add `guideLinkHTML(b)`** near `guideUrl` (index.html:1829):

```js
// curated community guide when we have one, else the neutral web search (an honest pointer, never an endorsement)
function guideLinkHTML(b){
  const g = (GUIDES && GUIDES.guides) ? GUIDES.guides[slugOf(b)] : null;
  if (g && g.url){
    return `<a class="guide-link" target="_blank" rel="noopener noreferrer" href="${esc(g.url)}"`
      + ` title="A community guide for ${esc(b.asc)} by ${esc(g.source)} — a pointer, not an endorsement; may lag the latest patch">`
      + `${esc(g.source)} guide ↗</a>`;
  }
  return `<a class="guide-link" target="_blank" rel="noopener noreferrer" href="${guideUrl(b)}"`
    + ` title="Open a web search for community build guides — Tincture doesn't host or endorse guides">guide ↗</a>`;
}
```

- [ ] **Step 4: Use it** — replace the inline `.guide-link` template at index.html:2206. Find:

```js
      `<a class="guide-link" target="_blank" rel="noopener noreferrer" href="${guideUrl(b)}" title="Open a web search for community build guides — Tincture doesn't host or endorse guides">guide ↗</a>`,
```
Replace with:

```js
      guideLinkHTML(b),
```

- [ ] **Step 5: Verify in preview** (controller runs the gate)

- Robust inline-JS syntax check OK; `node --test tools/test-frontend.cjs` still 8 pass.
- Preview: a guided ascendancy's row shows "{source} guide ↗" with the curated href + the honest title; an `unguided`/absent one shows "guide ↗" (neutral search). Rename `guides.json` → both fall back to neutral search, no console error (fail-safe). 0 console errors.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "feat(guides): front-end curated guide link with neutral-search fallback"
```

---

### Task 5: Full verification + merge to main

- [ ] **Step 1:** Full suites green — `python scripts/test_distill.py`; `python scripts/buildfile.py --selftest`; `node --test tools/test-build-from-ninja.cjs tools/test-effects.cjs tools/test-contracts.cjs tools/test-frontend.cjs`; robust inline-JS syntax OK.
- [ ] **Step 2:** Live preview end-to-end (0 console errors): guided rows show "{source} guide ↗", un-guided show neutral; mobile tap target (the guide link already ≥36px on mobile from the polish pass); CSP clean (no new external resources — outbound links are navigations, not subresources).
- [ ] **Step 3:** Merge — `superpowers:finishing-a-development-branch` (this repo: sync main → rebase → ff-merge → push → delete branch; `git checkout -- economy.json data.json` first; never stage docs/shots).
- [ ] **Step 4:** Post-merge — `gh run list --workflow=test.yml --limit 1` is `success`; final preview boot on main is clean; update README roadmap (curated guide directory → shipped) + the project memory.

---

## Self-Review

**Spec coverage:** guides.json schema + `unguided` (Tasks 1,2) ✓ · FE curated link + neutral fallback + honest copy (Task 4) ✓ · CI coverage-lock on untriaged (Tasks 1,2) ✓ · hourly soft warning + patch drift (Tasks 1,3) ✓ · curation research (Task 2) ✓ · honesty wording (Global Constraints + Task 4) ✓ · testing (every task) ✓ · fail-safe (Task 3 try/except, Task 4 shape-gate) ✓.

**Placeholder scan:** the only non-literal is the curated URLs themselves (Task 2 Step 1 is genuine research output, not a code placeholder) — acceptable and unavoidable for a curation task. All code steps carry complete code.

**Type consistency:** `guides_schema_errors(doc)->list`, `untriaged_guides(payload, doc)->list`, `warn_missing_guides(payload)->list`, `guideLinkHTML(b)->str`, `GUIDES={patch,guides,unguided}` — consistent across tasks. Slug = `slugify_asc`/`slugOf({asc,skill:""})` everywhere.

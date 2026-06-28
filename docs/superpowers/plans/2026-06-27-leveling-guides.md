# Leveling guides Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pair every meta build with a curated community *leveling*-guide pointer (honest, attributed, never an endorsement), mirroring the existing build-guides feature.

**Architecture:** Extend `guides.json` with an optional `leveling` map + `levelingUnguided` list (keyed by ascendancy slug, same keys as `guides`). The front end adds `levelingUrl`/`levelingLinkHTML` (twins of `guideUrl`/`guideLinkHTML`) and renders a leveling link on each ledger row and in The Prescription. The pipeline validates the new keys (optional), triages live ascendancies for leveling coverage (parallel `untriaged_leveling`), and warns non-blockingly — with a CI coverage-lock that fails on an untriaged ascendancy.

**Tech Stack:** Static `index.html` (vanilla JS, no deps), `scripts/distill.py` (Python stdlib only), `scripts/test_distill.py` (stdlib `unittest`), `guides.json` (data), `README.md` (docs).

## Global Constraints

- **Stdlib-only Python** — no pip/deps in `distill.py`/`test_distill.py` (the hourly Action is dependency-free).
- **Fail-safe** — an absent/renamed `guides.json` or absent `leveling` map must degrade to the neutral search everywhere, never break the page or the pipeline.
- **Leveling keys are TRULY OPTIONAL** — `guides_schema_errors` must return `[]` on a doc with **no** `leveling`/`levelingUnguided` keys. The committed `guides.json` has none today and `test_shipped_guides_json_valid_and_complete` asserts it validates clean; a validator that *requires* the keys breaks CI.
- **No change to existing build-guide behavior** — `guideUrl`/`guideLinkHTML`/`untriaged_guides` keep their signatures and observable behavior; existing tests must pass unchanged.
- **Honesty wording (verbatim):** curated → `"{source} leveling ↗"`, title `"A community leveling guide for {asc} by {source} — a pointer, not an endorsement; may lag the latest patch"`; neutral → `"leveling ↗"`, title `"Open a web search for community leveling guides — Tincture doesn't host or endorse guides"`. Use a **straight** apostrophe in `doesn't` (matches index.html:1850). Never "best"/endorsement.
- **Do not touch the `patch` field** (shared with build guides; the existing patch-drift warn covers it). Bump only `updated` → `2026-06-27` when the leveling map ships.
- **Never stage** `economy.json`, `docs/clip/*`, or `docs/shots/*` (pre-existing untracked artifacts).
- DRY, YAGNI, TDD, frequent commits.

## File Structure

- `scripts/distill.py` — add `_live_default_slugs` (shared league-walk), extend `guides_schema_errors` (optional leveling validation), add `untriaged_leveling`, wire the leveling warn into `warn_missing_guides`.
- `scripts/test_distill.py` — extend the `Guides` class: optional-leveling schema accept/reject, `untriaged_leveling` triage, and the shipped coverage-lock for leveling.
- `guides.json` — add the `leveling` map (10 curated entries) + empty `levelingUnguided`; bump `updated`.
- `index.html` — add `levelingUrl`/`levelingLinkHTML`; render on the ledger row and in The Prescription.
- `README.md` — add a "Curated leveling guides" bullet.

---

### Task 1: distill.py — `guides_schema_errors` validates the optional leveling keys

**Files:**
- Modify: `scripts/distill.py:503-527` (`guides_schema_errors`)
- Test: `scripts/test_distill.py:474-484` (`test_schema_errors_catches_bad_entries`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `guides_schema_errors(doc)` now also flags problems in `doc["leveling"]` (optional dict of `{slug: {url, source}}`) and `doc["levelingUnguided"]` (optional list of slug strings), plus a slug-in-both check — while still returning `[]` when those keys are absent. Signature unchanged.

- [ ] **Step 1: Write the failing test** — extend `test_schema_errors_catches_bad_entries` by appending these assertions inside the method (after the existing `both` block at line 484):

```python
        # leveling keys are OPTIONAL — a doc with none still validates clean
        self.assertEqual(distill.guides_schema_errors(
            {"guides":{"deadeye":{"url":"https://x.gg","source":"Maxroll"}}}), [])
        # a valid leveling map + levelingUnguided validates clean
        okl = {"guides":{"deadeye":{"url":"https://x.gg","source":"Maxroll"}},
               "leveling":{"deadeye":{"url":"https://x.gg/lvl","source":"Maxroll"}},
               "levelingUnguided":["titan"]}
        self.assertEqual(distill.guides_schema_errors(okl), [])
        # bad leveling: non-http url + empty source, and a non-list levelingUnguided
        badl = {"guides":{"deadeye":{"url":"https://x.gg","source":"M"}},
                "leveling":{"oracle":{"url":"ftp://x","source":""}},
                "levelingUnguided":"nope"}
        el = distill.guides_schema_errors(badl)
        self.assertTrue(any("oracle" in e for e in el))            # bad url + empty source
        self.assertTrue(any("levelingUnguided" in e for e in el))  # not a list
        # a slug in both leveling and levelingUnguided is an error
        bothl = {"guides":{"deadeye":{"url":"https://x","source":"M"}},
                 "leveling":{"oracle":{"url":"https://x","source":"M"}},
                 "levelingUnguided":["oracle"]}
        self.assertTrue(any("both leveling" in e.lower()
                            for e in distill.guides_schema_errors(bothl)))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python scripts/test_distill.py Guides.test_schema_errors_catches_bad_entries`
Expected: FAIL (the `badl`/`bothl` assertions fail — leveling isn't validated yet, so `el` is `[]` and no "both leveling" error is produced).

- [ ] **Step 3: Write the minimal implementation** — replace the body of `guides_schema_errors` (lines 503-527) with a version that factors the per-entry check into a local helper and reuses it for both maps:

```python
def guides_schema_errors(doc):
    """Return a list of human-readable problems with a guides.json doc; [] means valid.
    The `leveling`/`levelingUnguided` keys are OPTIONAL (additive) — absent is valid."""
    errs = []
    if not isinstance(doc, dict):
        return ["guides.json is not an object"]

    def _map_errs(m, label):
        out = []
        for slug, e in m.items():
            if not isinstance(e, dict):
                out.append(f"{label}['{slug}'] is not an object"); continue
            url = e.get("url")
            if not (isinstance(url, str) and (url.startswith("http://") or url.startswith("https://"))):
                out.append(f"{label}['{slug}'] has a missing/invalid url")
            if not (isinstance(e.get("source"), str) and e.get("source").strip()):
                out.append(f"{label}['{slug}'] has a missing/empty source")
        return out

    guides = doc.get("guides")
    if not isinstance(guides, dict):
        errs.append("'guides' is missing or not an object")
        guides = {}
    errs += _map_errs(guides, "guides")
    ung = doc.get("unguided", [])
    if not isinstance(ung, list) or not all(isinstance(s, str) for s in ung):
        errs.append("'unguided' must be a list of slug strings")
        ung = [s for s in (ung if isinstance(ung, list) else []) if isinstance(s, str)]
    both = set(guides) & set(ung)
    if both:
        errs.append(f"slug(s) in both guides and unguided: {sorted(both)}")

    # leveling (optional) — same shape as guides; absent keys are valid
    lvl = doc.get("leveling")
    lvl_map = {}
    if lvl is not None:
        if not isinstance(lvl, dict):
            errs.append("'leveling' must be an object")
        else:
            lvl_map = lvl
            errs += _map_errs(lvl, "leveling")
    lung = doc.get("levelingUnguided", [])
    if not isinstance(lung, list) or not all(isinstance(s, str) for s in lung):
        errs.append("'levelingUnguided' must be a list of slug strings")
        lung = [s for s in (lung if isinstance(lung, list) else []) if isinstance(s, str)]
    lboth = set(lvl_map) & set(lung)
    if lboth:
        errs.append(f"slug(s) in both leveling and levelingUnguided: {sorted(lboth)}")
    return errs
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/test_distill.py Guides`
Expected: PASS (the extended schema test + the existing `Guides` tests all green — the refactor preserves the original `guides`/`unguided` behavior).

- [ ] **Step 5: Commit**

```bash
git add scripts/distill.py scripts/test_distill.py
git commit -m "distill: validate optional leveling/levelingUnguided in guides_schema_errors"
```

---

### Task 2: distill.py — `untriaged_leveling` + non-blocking leveling warn

**Files:**
- Modify: `scripts/distill.py:530-548` (`untriaged_guides` → delegate to a new shared `_live_default_slugs`) and add `untriaged_leveling`
- Modify: `scripts/distill.py:859-880` (`warn_missing_guides` — add the leveling warn loop)
- Test: `scripts/test_distill.py` (`Guides` class — add a `test_untriaged_leveling_*` method)

**Interfaces:**
- Consumes: `slugify_asc(asc)` (distill.py:499).
- Produces:
  - `_live_default_slugs(payload) -> set[str]` — slugs of live, non-curated, default-league ascendancies.
  - `untriaged_leveling(payload, doc) -> list[str]` — sorted live slugs in neither `leveling` nor `levelingUnguided`.
  - `untriaged_guides(payload, doc)` keeps its exact signature/behavior (now a thin wrapper over `_live_default_slugs`).

- [ ] **Step 1: Write the failing test** — add this method to the `Guides` class (e.g. right after `test_untriaged_tolerates_bad_payload`, line 497):

```python
    def test_untriaged_leveling_lists_only_unhandled_live_ascendancies(self):
        payload = {"default":"sc","leagues":[
            {"url":"sc","builds":[{"asc":"Deadeye"},{"asc":"Titan"},{"asc":"Smith of Kitava"}]},
            {"url":"std","curated":True,"builds":[{"asc":"Lich"}]},
        ]}
        doc = {"leveling":{"deadeye":{"url":"https://x","source":"M"}}, "levelingUnguided":["titan"]}
        # Deadeye has a leveling guide, Titan is levelingUnguided, Smith is untriaged, Lich is curated-only
        self.assertEqual(distill.untriaged_leveling(payload, doc), ["smith-of-kitava"])
        # tolerates a bad payload/doc exactly like its build-guide twin
        self.assertEqual(distill.untriaged_leveling(None, {"leveling":{}, "levelingUnguided":[]}), [])
        self.assertEqual(distill.untriaged_leveling({}, None), [])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python scripts/test_distill.py Guides.test_untriaged_leveling_lists_only_unhandled_live_ascendancies`
Expected: FAIL with `AttributeError: module 'distill' has no attribute 'untriaged_leveling'`.

- [ ] **Step 3: Write the minimal implementation** — replace `untriaged_guides` (lines 530-548) with the shared-walk version and add `untriaged_leveling` immediately after:

```python
def _live_default_slugs(payload):
    """Slugs of live (non-curated) default-league ascendancies in the payload."""
    payload = payload if isinstance(payload, dict) else {}
    default_url = payload.get("default")
    out = set()
    for lg in payload.get("leagues", []):
        if lg.get("url") != default_url or lg.get("curated"):
            continue
        for b in lg.get("builds", []):
            asc = b.get("asc")
            if asc:
                out.add(slugify_asc(asc))
    return out


def untriaged_guides(payload, doc):
    """Sorted slugs of live (non-curated) default-league ascendancies handled by neither
    guides nor unguided — i.e. new ascendancies that need a curation decision."""
    guides = (doc.get("guides") or {}) if isinstance(doc, dict) else {}
    ung = set((doc.get("unguided") or []) if isinstance(doc, dict) else [])
    handled = set(guides) | ung
    return sorted(s for s in _live_default_slugs(payload) if s not in handled)


def untriaged_leveling(payload, doc):
    """Leveling twin of untriaged_guides: live slugs in neither leveling nor levelingUnguided."""
    lvl = (doc.get("leveling") or {}) if isinstance(doc, dict) else {}
    lung = set((doc.get("levelingUnguided") or []) if isinstance(doc, dict) else [])
    handled = set(lvl) | lung
    return sorted(s for s in _live_default_slugs(payload) if s not in handled)
```

- [ ] **Step 4: Wire the leveling warn into `warn_missing_guides`** — in `warn_missing_guides` (distill.py:859-880), after the existing `missing` loop (the `for slug in missing:` block ending at line 872, before the `gp, dp = ...` patch-drift line 873), insert:

```python
        for slug in untriaged_leveling(payload, doc):
            print(f"[warn] ascendancy '{slug}' has no leveling guide "
                  f"(add it to guides.json leveling or levelingUnguided list)", file=sys.stderr)
```

Leave the rest of `warn_missing_guides` unchanged (it still `return missing` — the build-guide list; leveling triage is asserted directly in the test, not via this return).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/test_distill.py Guides`
Expected: PASS — the new leveling triage test passes AND the existing `test_untriaged_lists_only_unhandled_live_ascendancies` / `test_untriaged_tolerates_bad_payload` still pass (the wrapper preserves behavior).

- [ ] **Step 6: Commit**

```bash
git add scripts/distill.py scripts/test_distill.py
git commit -m "distill: add untriaged_leveling + non-blocking leveling warn (shared league-walk)"
```

---

### Task 3: guides.json — add the curated leveling map (curation + coverage-lock)

**Files:**
- Modify: `guides.json` (add `leveling` map + `levelingUnguided`; bump `updated`)
- Modify: `scripts/test_distill.py:499-511` (`test_shipped_guides_json_valid_and_complete`)

**Interfaces:**
- Consumes: `untriaged_leveling` (Task 2), `guides_schema_errors` (Task 1).
- Produces: the shipped `guides.json` carries a `leveling` entry (or `levelingUnguided` membership) for every live default-league ascendancy, locked by CI.

- [ ] **Step 1: Extend the shipped coverage-lock test (RED first)** — in `test_shipped_guides_json_valid_and_complete`, after the existing `untriaged_guides` assertion (line 510-511), add:

```python
            self.assertEqual(distill.untriaged_leveling(payload, doc), [],
                             "every live ascendancy must be in guides.json's leveling or "
                             "levelingUnguided — add the new one(s)")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/test_distill.py Guides.test_shipped_guides_json_valid_and_complete`
Expected: FAIL — the shipped `guides.json` has no `leveling` map yet, so all 10 live ascendancies are untriaged for leveling.

- [ ] **Step 3: Click-verify the one flagged pick, then add the leveling map.** The rev2 spec's curation table seeds 10 picks. **Before writing**, verify the `abyssal-lich` pick by opening it (WebFetch, and if it 403s, WebSearch the title): `https://mobalytics.gg/poe-2/builds/plants-lich-deadrabb1t`. If it is **not** a real, current 0.5.x campaign/leveling build, move `abyssal-lich` from `leveling` to `levelingUnguided` instead (do **not** force a weak pick). Then set `guides.json` to (keys must match the live slugs in `guides` exactly):

```json
{
  "patch": "0.5.3",
  "updated": "2026-06-27",
  "guides": {
    "martial-artist": { "url": "https://maxroll.gg/poe2/build-guides/whirling-assault-martial-artist-build-guide", "source": "Maxroll" },
    "spirit-walker": { "url": "https://maxroll.gg/poe2/build-guides/spirit-walker-twisters", "source": "Maxroll" },
    "deadeye": { "url": "https://maxroll.gg/poe2/build-guides/lightning-arrow-deadeye", "source": "Maxroll" },
    "gemling-legionnaire": { "url": "https://maxroll.gg/poe2/build-guides/gemling-legionnaire-twister-build-guide", "source": "Maxroll" },
    "oracle": { "url": "https://maxroll.gg/poe2/build-guides/entangle-oracle-build-guide", "source": "Maxroll" },
    "stormweaver": { "url": "https://maxroll.gg/poe2/build-guides/arc-stormweaver-build-guide", "source": "Maxroll" },
    "disciple-of-varashta": { "url": "https://maxroll.gg/poe2/build-guides/disciple-of-varashta-plant-build-guide", "source": "Maxroll" },
    "blood-mage": { "url": "https://www.switchbladegaming.com/path-of-exile-2/blood-mage-build-2/", "source": "Switchblade Gaming" },
    "titan": { "url": "https://maxroll.gg/poe2/build-guides/whirling-assault-titan-endgame-build-guide", "source": "Maxroll" },
    "abyssal-lich": { "url": "https://odealo.com/articles/detonate-dead-abyssal-lich-poe-2-build", "source": "Odealo" }
  },
  "unguided": ["chronomancer", "infernalist", "invoker", "lich", "pathfinder"],
  "leveling": {
    "martial-artist": { "url": "https://deltiasgaming.com/path-of-exile-2-0-5-monk-martial-artist-leveling-guide/", "source": "Deltia's Gaming" },
    "spirit-walker": { "url": "https://www.poe-vault.com/poe2/huntress/spirit-walker/companion-leveling-build", "source": "PoE Vault" },
    "deadeye": { "url": "https://maxroll.gg/poe2/build-guides/lightning-arrow-deadeye-leveling-build-guide", "source": "Maxroll" },
    "gemling-legionnaire": { "url": "https://maxroll.gg/poe2/build-guides/grenade-mercenary-leveling-guide", "source": "Maxroll" },
    "oracle": { "url": "https://maxroll.gg/poe2/build-guides/the-shapeshift-druid-leveling-guide", "source": "Maxroll" },
    "stormweaver": { "url": "https://maxroll.gg/poe2/build-guides/spark-archmage-stormweaver-leveling-guide", "source": "Maxroll" },
    "disciple-of-varashta": { "url": "https://maxroll.gg/poe2/build-guides/disciple-of-varashta-plant-build-guide", "source": "Maxroll" },
    "blood-mage": { "url": "https://maxroll.gg/poe2/build-guides/fireball-blood-mage-leveling-guide", "source": "Maxroll" },
    "titan": { "url": "https://maxroll.gg/poe2/build-guides/boneshatter-titan-leveling-guide", "source": "Maxroll" },
    "abyssal-lich": { "url": "https://mobalytics.gg/poe-2/builds/plants-lich-deadrabb1t", "source": "Mobalytics" }
  },
  "levelingUnguided": []
}
```

(If `abyssal-lich` failed verification in Step 3: remove its `leveling` entry and set `"levelingUnguided": ["abyssal-lich"]`.)

- [ ] **Step 4: Run the coverage-lock + full suite to verify green**

Run: `python scripts/test_distill.py`
Expected: PASS — `untriaged_leveling(payload, doc) == []` (all live ascendancies triaged), `guides_schema_errors == []`, and the whole suite green.

- [ ] **Step 5: Commit**

```bash
git add guides.json scripts/test_distill.py
git commit -m "guides: add curated leveling map (10 live ascendancies) + coverage-lock"
```

---

### Task 4: index.html — `levelingUrl`/`levelingLinkHTML` + ledger-row render

**Files:**
- Modify: `index.html:1851` (insert the two functions right after `guideLinkHTML` closes)
- Modify: `index.html:2273-2278` (add `levelingLinkHTML(b)` to `subBits`)

**Interfaces:**
- Consumes: `esc` (index.html:1454), `slugOf` (index.html:1603), `GUIDES` (index.html:1442, whole guides.json object), `DATA.patch`.
- Produces: `levelingUrl(b)` (neutral leveling search URL) and `levelingLinkHTML(b)` (curated-or-neutral `<a class="guide-link">`), rendered on every ledger row.

- [ ] **Step 1: Add the functions** — after the closing `}` of `guideLinkHTML` (index.html:1851), insert:

```javascript

// curated community LEVELING guide when we have one, else the neutral web search (an honest pointer, never an endorsement)
function levelingUrl(b){
  const q = `${b.asc}${b.skill ? " " + b.skill : ""} Path of Exile 2 ${DATA.patch || "0.5.3"} leveling guide`;
  return "https://www.google.com/search?q=" + encodeURIComponent(q);
}
function levelingLinkHTML(b){
  const g = (GUIDES && GUIDES.leveling) ? GUIDES.leveling[slugOf(b)] : null;
  if (g && g.url){
    return `<a class="guide-link" target="_blank" rel="noopener noreferrer" href="${esc(g.url)}"`
      + ` title="A community leveling guide for ${esc(b.asc)} by ${esc(g.source)} — a pointer, not an endorsement; may lag the latest patch">`
      + `${esc(g.source)} leveling ↗</a>`;
  }
  return `<a class="guide-link" target="_blank" rel="noopener noreferrer" href="${levelingUrl(b)}"`
    + ` title="Open a web search for community leveling guides — Tincture doesn't host or endorse guides">leveling ↗</a>`;
}
```

- [ ] **Step 2: Render it on the ledger row** — in the `subBits` array (index.html:2273-2278), add `levelingLinkHTML(b),` right after `guideLinkHTML(b),`:

```javascript
    const subBits = [
      b.cls && `<span class="cls">${esc(b.cls)}</span>`,
      tag && esc(tag),
      (b.n!=null ? `~${fmt(b.n)} characters` : null),
      guideLinkHTML(b),
      levelingLinkHTML(b),
    ].filter(Boolean);
```

- [ ] **Step 3: Verify in the browser preview** (server on port 8099 — `node serve`/launch config "tincture"; reload):
  - `preview_console_logs` → 0 errors.
  - `preview_snapshot` on a ledger row → shows both `"… guide ↗"` and `"{source} leveling ↗"` separated by `·`.
  - A curated slug (e.g. Deadeye) shows `"Maxroll leveling ↗"` linking the dedicated leveling URL; hover title matches the honesty copy.
  - `preview_click` the leveling link's row area (not the link) → row still toggles; clicking the link does not toggle (covered by the `.guide-link`/`a` ignore selector at index.html:2339).

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "fe: levelingUrl/levelingLinkHTML + leveling pointer on each ledger row"
```

---

### Task 5: index.html — leveling link in The Prescription

**Files:**
- Modify: `index.html:3085` (add a neutral leveling link after the existing neutral `guide ↗` link in `.rx-acts`)

**Interfaces:**
- Consumes: `levelingUrl` (Task 4), `esc`, the quiz result object `c` with `c.b` (the build).

- [ ] **Step 1: Add the leveling link** — in the `.rx-acts` block, after the existing guide link (index.html:3085), add a sibling. The two lines become:

```javascript
        <a href="${guideUrl(c.b)}" target="_blank" rel="noopener noreferrer">guide ↗</a>
        <a href="${levelingUrl(c.b)}" target="_blank" rel="noopener noreferrer">leveling ↗</a>
```

(Neutral-only on purpose — mirrors the existing neutral `guideUrl` link here; do **not** switch the Prescription to the curated `guideLinkHTML`/`levelingLinkHTML`, per "no change to existing build-guide behavior".)

- [ ] **Step 2: Verify in the browser preview:**
  - Run the Prescription quiz to a result; `preview_snapshot` the `.rx-card` → the action row shows `Decant`, `view in ledger ↓`, `guide ↗`, **and** `leveling ↗`.
  - `preview_console_logs` → 0 errors.
  - Clicking `leveling ↗` opens a new tab to the neutral leveling search for that ascendancy (target=_blank; does not navigate the SPA).

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "fe: leveling pointer in The Prescription quiz result"
```

---

### Task 6: README.md — document the leveling-guides feature

**Files:**
- Modify: `README.md:155` (add a sibling bullet right after the "Curated build guides" line)

- [ ] **Step 1: Add the bullet** — after the `- [x] **Curated build guides** …` line (README.md:155), insert:

```markdown
- [x] **Curated leveling guides** — a hand-picked community *leveling* guide per live ascendancy (`guides.json` `leveling` map), shown as *"{source} leveling ↗"* next to the build-guide link on each ledger row and in The Prescription, with the neutral web search as the fallback where none is vetted. Same CI coverage-lock + hourly non-blocking warn as the build guides, so leveling picks can't silently go stale. No scraping — links + attribution only
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document the curated leveling-guides feature in README"
```

---

## Final verification (after all tasks)

- [ ] `python scripts/test_distill.py` → all green (was 49 OK; +1 new `Guides` method and extended assertions).
- [ ] `python scripts/distill.py --demo` → runs offline, fail-safe path intact (no leveling-related crash; warns are non-blocking).
- [ ] Browser preview: ledger row + Prescription both show the leveling pointer; rename `guides.json` → neutral leveling search everywhere, page still renders, 0 console errors (fail-safe); restore the name.
- [ ] `git status` clean except the intended files; `economy.json`/`docs/shots`/`docs/clip` never staged.

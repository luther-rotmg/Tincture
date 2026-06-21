# Curated build guides + auto-staleness reminder

**Status:** approved design · **Date:** 2026-06-21 · **Type:** content + small FE/pipeline feature

## Overview

Replace the per-row neutral "guide ↗" web-search with a **hand-curated community guide link per
ascendancy** where one exists, framed honestly as "a community guide" (never "the best"), with the
neutral search as the fallback. Add an **automated staleness reminder** so a meta shift that introduces
a new ascendancy (or a patch bump) surfaces a "needs a guide" warning without anyone remembering to check.

No scraping (ToS + the project's "don't republish others' builds" rule) — only *links*, with attribution.

## Goals
- One vetted community guide link per live ascendancy, honestly attributed and patch-dated.
- Preserve honesty: "a community guide by {source}", not an endorsement; neutral search where coverage is thin.
- Automate the reminder: CI fails on a missing guide at commit time; the hourly job logs a non-blocking
  warning when the meta gains an un-guided ascendancy.
- Stay on-ethos: static, no backend, no new deps, fails safe.

## Non-goals (YAGNI)
- No scraping / republishing guide content. No ratings. No per-skill granularity. No new UI section
  (this enhances the existing `.guide-link`). No hard pipeline failure on a missing guide.

## Data — `guides.json` (committed, hand-curated)

```json
{
  "patch": "0.5.0",
  "updated": "2026-06-21",
  "guides": {
    "deadeye":   { "url": "https://maxroll.gg/poe2/…", "source": "Maxroll" },
    "titan":     { "url": "https://…",                 "source": "Mobalytics" }
  },
  "unguided": ["some-ascendancy-slug"]
}
```
- `guides` keyed by ascendancy **slug** (`slugOf({asc, skill:""})` — matches `META.byAsc` keys and the `/b` slugs).
- `url` (required), `source` (required — the site/creator name for attribution). Optional `note`.
- `patch` = the patch the picks were vetted against (drives staleness).
- **`unguided`** = ascendancies *intentionally* left without a curated guide (no solid current pick yet, OR not
  in the current live meta — e.g. demo/sample or past-league ascendancies). They fall back to the neutral search
  in the UI exactly like an absent key; the list exists so the coverage check (below) can tell "triaged,
  deliberately skipped" apart from "new and forgotten" — and so the check stays deterministic even when a
  `--demo` run swaps `data.json` to the sample set.
- Any live ascendancy in NEITHER `guides` nor `unguided` is **untriaged** → the reminder fires.

## Front end (`index.html`)
- **Boot**: fetch `guides.json` alongside the other enrichment JSON (`fetchJSON("guides.json", 8000, "default")`,
  fail-safe), shape-gate, promote to a global `GUIDES` (`{patch, guides}`); `null`/missing → feature simply
  doesn't activate (neutral search remains).
- **`guideLinkHTML(b)`** (new, replaces the inline `.guide-link` markup at index.html:2206):
  - if `GUIDES && GUIDES.guides[slugOf(b)]` → `<a class="guide-link" target="_blank" rel="noopener noreferrer"
    href="{esc url}" title="A community guide for {asc} by {source} — a pointer, not an endorsement; may lag
    the latest patch">{source} guide ↗</a>`
  - else → the existing neutral-search link (unchanged).
  - `guideUrl(b)` (the neutral search) stays as the fallback builder.
- All URLs `esc()`-d; `rel="noopener noreferrer"` preserved. No behavior change to the row-toggle (`.guide-link`
  is already in the ignore-selector).

## Auto-staleness reminder (two layers)
1. **`scripts/test_distill.py`** — a test that: validates `guides.json` shape (every `guides` entry has `url`+`source`,
   `url` is http(s); `unguided` is a list of strings; no slug in both); and asserts every ascendancy in the
   **bundled demo** `data.json`'s default league is **triaged** — present in `guides` OR `unguided`. An untriaged
   (new) ascendancy **fails CI at commit time** — the bite that forces a decision. Legitimate gaps never fail
   (they're in `unguided`). Runs in `test.yml`.
2. **`scripts/distill.py`** — `untriaged_guides(payload, guides)` (pure, tested) returns live ascendancies in
   neither `guides` nor `unguided`; `warn_missing_guides` prints a non-blocking `⚠ ascendancy '<asc>' is in the
   meta but has no guide (add to guides.json or its unguided list)` for each, plus `⚠ guides.json patch <p> is
   behind data.json patch <q>` when the patch trails. Visible in the hourly Action log; **never fails the run**
   (fails safe) — this catches a meta change that lands between code commits.

## Curation (implementation step, controller does the research)
- For each live ascendancy in the default league, WebSearch (e.g. "PoE2 0.5.0 <Ascendancy> build guide"),
  open/skim the top reputable result (Maxroll, Mobalytics, established creators), confirm it's current for
  0.5.0 / Runes of Aldur and actually about that ascendancy, and record `{url, source}`.
- Where no solid, current guide exists, add the slug to **`unguided`** (neutral-search fallback) rather than
  force a weak pick — so it's recorded as a deliberate skip, not an oversight.
- Record honestly: `source` is the host/creator; the UI says "a community guide", not "best".

## Honesty guards
- Wording "a community guide by {source}" + the "pointer, not an endorsement; may lag the patch" title.
- Neutral search fallback (defers judgment to the user) wherever there's no vetted pick.
- Attribution always shown; patch-dated; the "Tincture doesn't host or endorse guides" stance preserved in copy.
- The reminder prevents silent staleness (the main honesty risk the feasibility scout flagged).

## Testing
- **Python**: `test_distill.py` — guides.json schema + coverage (above) + `warn_missing_guides` is pure/tested
  (returns the list of missing ascendancies for a given payload+guides, so the warning logic is unit-tested).
- **FE**: live preview — a guided ascendancy shows "{source} guide ↗" with the right href + title; an
  un-guided one shows the neutral search; 0 console errors; guides.json fetch fail-safe (rename → neutral search
  everywhere, no break).
- **Suites stay green**; robust inline-JS syntax OK; CI (`test.yml`) runs the new Python test.

## Integration points
- New `guides.json` at repo root.
- `index.html`: boot fetch (~3249 block) + `GUIDES` global; `guideLinkHTML(b)` replacing the inline link (~2206);
  `guideUrl` kept as fallback.
- `scripts/distill.py`: `warn_missing_guides(payload)` called in `run_live`; pure helper for testability.
- `scripts/test_distill.py`: schema + coverage + helper tests.
- `test.yml` already runs `test_distill.py` (no workflow change needed).

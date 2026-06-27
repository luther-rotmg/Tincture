# Leveling guides — curated per-ascendancy leveling-guide links

**Status:** approved design · **Date:** 2026-06-27 · **Type:** small feature (data + FE + pipeline guard) — mirrors the existing build-guides feature
**Branch:** `feature/leveling-guides` (off `main`)

## Overview

The meta builds are reconstructed from level **85–100** ladder characters — the *destination*, not the path
to it. A new player can't fund or play that at level 20. This adds a curated **community leveling-guide link
per ascendancy**, so each build pairs "here's the endgame build" with "here's how to get there" — honestly
(a *pointer*, never an endorsement; never a fabricated leveling build, which we have no data to derive and
which would violate the no-fabrication rule).

It is a near-exact **mirror of the existing build-guides feature** (`guides.json` + `guideLinkHTML` +
`untriaged_guides`/`warn_missing_guides` + a CI triage test). Reuse the proven shape; do not invent a new one.

## Goals

- One vetted community **leveling** guide link per live ascendancy where a solid current one exists, honestly
  attributed and patch-dated; neutral web search where none is curated.
- Same honesty as build guides: "a community leveling guide by {source}", never "best"; neutral fallback;
  attribution always shown; the staleness reminder fires on a new un-triaged ascendancy so coverage can't rot.
- Stay on-ethos: static, no backend, no new deps, fail-safe, no fabricated leveling build.

## Non-goals (YAGNI)

- **No** generated/reconstructed leveling build (we have no leveling data; fabrication is forbidden).
- **No** new UI section — this extends the existing build-view guide link. No ledger/quiz clutter.
- **No** hard pipeline failure on a missing leveling guide (non-blocking warn, like build guides).
- **No** change to the existing build-guide behavior, the ranking, or any other feature.

## Honesty guardrails

- "A community leveling guide by {source} — a pointer, not an endorsement; may lag the latest patch."
- Neutral web search fallback wherever there's no vetted pick (defers judgment to the user).
- Dedicated PoE2 *leveling* guides are rarer than endgame ones, so coverage is expected to be **partial** at
  first — many ascendancies honestly fall to `levelingUnguided` / neutral search. That's correct behavior, not
  a gap. Never force a weak pick to look complete.

## Data — `guides.json` (extend, mirroring `guides`/`unguided`)

Add two parallel top-level keys (the shared `patch`/`updated` already date the file):
```json
{
  "patch": "0.5.3", "updated": "2026-06-27",
  "guides": { … },          // unchanged
  "unguided": [ … ],        // unchanged
  "leveling": {
    "martial-artist": { "url": "https://maxroll.gg/poe2/…/leveling", "source": "Maxroll" }
  },
  "levelingUnguided": ["some-slug"]
}
```
- `leveling` keyed by ascendancy **slug** (`slugOf({asc, skill:""})` — same keys as `guides`/`META.byAsc`/`/b`).
- Each entry: `url` (required, http(s)) + `source` (required). A slug with no solid current leveling guide goes
  in **`levelingUnguided`** (→ neutral search), exactly like `unguided`. A live ascendancy in **neither** is
  *untriaged* → the reminder fires.
- A leveling URL may legitimately be a build guide's leveling section (same host) — fine; it's still a real
  leveling pointer.

## Front end (`index.html`)

- **`levelingUrl(b)`** (new, mirrors `guideUrl` at index.html:1836): neutral search
  `` `${b.asc} Path of Exile 2 ${DATA.patch || "0.5.3"} leveling guide` `` → google search URL.
- **`levelingLinkHTML(b)`** (new, mirrors `guideLinkHTML` at index.html:1842): if
  `GUIDES && GUIDES.leveling && GUIDES.leveling[slugOf(b)]` has a `url` → `<a class="guide-link" target="_blank"
  rel="noopener noreferrer" href="${esc(url)}" title="A community leveling guide for ${esc(b.asc)} by
  ${esc(source)} — a pointer, not an endorsement; may lag the latest patch">${esc(source)} leveling ↗</a>`; else
  the neutral fallback `<a class="guide-link" … href="${levelingUrl(b)}" title="Open a web search for community
  leveling guides — Tincture doesn't host or endorse guides">leveling ↗</a>`.
- **Render** `levelingLinkHTML(b)` adjacent to the existing `guideLinkHTML(b)` in the build view
  (index.html:2277). Reuses the `.guide-link` CSS class (no new CSS). The `.guide-link` selector is already in
  the row-toggle ignore list (index.html:2339), so the new link inherits the click-ignore behavior.
- **Boot:** no change needed — `GUIDES` is the whole `guides.json` object (promoted at index.html:3333 once
  `gd.guides` shape-gates), so `GUIDES.leveling` rides along; `levelingLinkHTML` null-checks it, so an absent
  `leveling` map simply yields the neutral-search link everywhere (fail-safe).

## Pipeline honesty guard (`scripts/distill.py` + `scripts/test_distill.py`)

- **`guides_schema_errors(doc)`** (distill.py:503): also validate the **optional** `leveling` map (each entry
  has http(s) `url` + non-empty `source`) and `levelingUnguided` (a list of slug strings), and that no slug is
  in both `leveling` and `levelingUnguided`. Absent leveling keys are valid (the feature is additive). Reuse
  the existing per-entry validation logic (a small shared helper or a second pass over the `leveling` map).
- **Triage:** extend the un-triaged check to cover leveling — either generalize `untriaged_guides(payload, doc)`
  into a shared `_untriaged(payload, doc, map_key, list_key)` used by both, or add a parallel
  `untriaged_leveling(payload, doc)` (same logic, reading `leveling`/`levelingUnguided`). Returns live
  default-league ascendancies in neither.
- **`warn_missing_guides(payload)`** (distill.py:859): also log un-triaged **leveling** ascendancies
  (non-blocking, `⚠ ascendancy '<asc>' has no leveling guide (add it to guides.json leveling or
  levelingUnguided list)`), and keep the existing patch-drift warning (the shared `patch` covers both).
- **`scripts/test_distill.py`:** extend the guides test to (1) validate the `leveling`/`levelingUnguided` shape
  via `guides_schema_errors`, and (2) assert every live (bundled-demo default-league) ascendancy is **triaged**
  for leveling — present in `leveling` OR `levelingUnguided`. An un-triaged new ascendancy **fails CI** (the
  same bite that protects the build guides). Runs in `test.yml`.

## Curation (implementation step — the controller does the research)

- For each live ascendancy in the default league, WebSearch (e.g. "PoE2 0.5.3 <Ascendancy> leveling guide"),
  open/skim the top reputable result (Maxroll/Mobalytics/established creators), confirm it's current for
  0.5.x / Runes of Aldur and is actually a **leveling** guide (or a build guide with a real leveling section),
  and record `{url, source}`. Where no solid current leveling guide exists, add the slug to
  **`levelingUnguided`** (neutral search) rather than force a weak pick.
- Record honestly: `source` is the host/creator; the UI says "a community leveling guide", not "best".

## Testing

- **Python (`test_distill.py`):** `guides_schema_errors` accepts a valid `leveling`/`levelingUnguided` and
  rejects a bad one (non-http url, empty source, slug in both, non-list); the triage test fails on an
  un-triaged leveling ascendancy and passes when all are triaged. `python scripts/test_distill.py` green.
- **Front end (preview):** a slug with a `leveling` entry shows "{source} leveling ↗" with the right href +
  title next to the build-guide link; an un-curated one shows the neutral "leveling ↗" search; `guides.json`
  fetch fail-safe (rename → neutral leveling search everywhere, no break); 0 console errors.
- Suites stay green; CI (`test.yml`) runs the new Python assertions.

## Rollout

Pure static + the existing hourly guard. Deploys with the `index.html` + `guides.json` + `distill.py` commit.
Branch off `main`; standard finish (the owner's merge/PR choice).

## Integration points (verified anchors)

- `guides.json`: new `leveling` map + `levelingUnguided` list (root).
- `index.html`: new `levelingUrl`/`levelingLinkHTML` beside `guideUrl` [1836] / `guideLinkHTML` [1842]; render
  call beside `guideLinkHTML(b)` [2277]; `GUIDES` promoted [3333] (no change). `.guide-link` CSS [176] reused.
- `scripts/distill.py`: `guides_schema_errors` [503] (+leveling), `untriaged_guides` [530] (+leveling sibling/
  shared helper), `warn_missing_guides` [859] (+leveling warn).
- `scripts/test_distill.py`: extend the guides triage/schema test for leveling.

# Leveling guides — curated per-ascendancy leveling-guide links

**Status:** approved design · **rev2** (folded in the 3-agent verification: code-grounding, a live WebSearch
curation sweep, and a consistency/honesty pass) · **Date:** 2026-06-27 · **Type:** small feature (data + FE +
pipeline guard) — mirrors the existing build-guides feature
**Branch:** `feature/leveling-guides` (off `main`)

**Verification outcome (rev2):** every code anchor confirmed accurate. The WebSearch sweep found a real, current
0.5.x leveling guide for **all 10** live default-league ascendancies (0 fall to neutral search) — so coverage is
effectively complete, not partial. Three corrections folded in below: (1) the schema validator must treat the
leveling keys as **truly optional** (HIGH — the committed `guides.json` has no leveling keys and a CI test asserts
it validates clean); (2) use a **parallel `untriaged_leveling`**, not a refactor of the shared signature (zero
existing-caller risk); (3) `guideUrl`/`guideLinkHTML` actually render at **three** sites, so the render **scope is
now decided explicitly** (ledger row + The Prescription; *not* the hero). The ledger `subBits` join is `" · "`
(line 2303), so an added array element is auto-separated — no run-together.

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
- The verification sweep found a solid current leveling guide for **all 10** live default-league ascendancies,
  so first-ship coverage is effectively complete. But `levelingUnguided` + the neutral fallback stay as the
  honest mechanism for the *other* leagues and any *future* ascendancy that has no good guide yet — a slug with
  no solid current leveling guide goes there rather than getting a forced weak pick. Partial coverage is correct
  behavior, not a gap; never green-check a hole.
- Apostrophe glyph: the existing fallback title uses a **straight** apostrophe (`Tincture doesn't host …`,
  index.html:1850) — match it verbatim (the leveling fallback uses the same straight `'`).

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
### Render scope — decided explicitly (verification finding: `guideUrl`/`guideLinkHTML` render at 3 sites)

The build-guide link renders in **three** places, with two different patterns. Leveling mirrors the **two**
per-build sites and deliberately skips the hero:

1. **Ledger row** — index.html:2277, inside the `subBits` array (joined with `" · "` at index.html:2303).
   The build guide here uses the **curated** `guideLinkHTML(b)`. → **Add `levelingLinkHTML(b)` as its own
   `subBits` element** right after `guideLinkHTML(b)`. It always returns a truthy `<a>` (neutral fallback), so
   it survives `.filter(Boolean)` and the `" · "` join auto-separates the two anchors (no run-together). This is
   the canonical per-build home — every ledger build gets a leveling pointer. Reuses `.guide-link` CSS (no new
   CSS) and the row-toggle ignore selector (index.html:2339) covers it via both `.guide-link` and the bare `a`.
2. **The Prescription** (quiz outcome) — index.html:3085, the `.rx-acts` action row. Here the build guide uses
   the **neutral** inline `<a href="${guideUrl(c.b)}" …>guide ↗</a>`, **not** the curated `guideLinkHTML`. To
   stay a faithful mirror and honor "no change to existing build-guide behavior," **add a neutral sibling**
   `<a href="${levelingUrl(c.b)}" target="_blank" rel="noopener noreferrer">leveling ↗</a>` right after it. (It
   intentionally stays neutral-only, matching the existing neutral guide link there — we do *not* upgrade the
   Prescription's build-guide link to curated.) This is where a *new* player lands after the quiz — exactly the
   "help me get to the higher level range" moment. No `.rx-acts` CSS change needed (it's a flex row of links).
3. **Hero CTA** — index.html:2419 (`hg.href = guideUrl(top)`). **Out of scope.** Workstream ② established a
   one-primary-action hero; a second link there dilutes it. The hero's single build still has its leveling
   pointer one row down in the ledger.

- **Boot:** no change needed — `GUIDES` is the whole `guides.json` object (promoted at index.html:3333 once
  `gd.guides` shape-gates), so `GUIDES.leveling` rides along; `levelingLinkHTML` null-checks it, so an absent
  `leveling` map simply yields the neutral-search link everywhere (fail-safe).

## Pipeline honesty guard (`scripts/distill.py` + `scripts/test_distill.py`)

- **`guides_schema_errors(doc)`** (distill.py:503): also validate the `leveling` map (each entry has http(s)
  `url` + non-empty `source`) and `levelingUnguided` (a list of slug strings), and that no slug is in both
  `leveling` and `levelingUnguided`. **HIGH-priority correctness requirement (verification):** the leveling keys
  are **truly optional** — guard every leveling check on *presence* (`lvl = doc.get('leveling'); if lvl is not
  None: …` and `doc.get('levelingUnguided', [])`), and **never append an error merely because a key is absent.**
  The committed `guides.json` currently has **no** leveling keys, and `test_distill.py` asserts
  `guides_schema_errors(doc) == []` on that exact file — a validator that *requires* the keys breaks CI on the
  unchanged file. Reuse the existing per-entry validation logic (a small shared helper or a second pass over the
  `leveling` map). Mirror the existing absent-tolerant precedent at distill.py:520 (`doc.get('unguided', [])`).
- **Triage — use a parallel function (verification: lower-risk than a refactor):** add
  **`untriaged_leveling(payload, doc)`** reading `leveling`/`levelingUnguided` with the same league-walk as
  `untriaged_guides` (returns live default-league ascendancies in neither map). Do **not** refactor
  `untriaged_guides(payload, doc)` into a shared `_untriaged(...)` — its 2-arg signature is called by name from
  `warn_missing_guides` and two test sites; a parallel function touches zero existing callers and matches the
  "no change to existing behavior" goal. (A shared private helper is acceptable *only if* `untriaged_guides` is
  preserved verbatim as a thin wrapper — the parallel function is strictly lower-risk, so prefer it.)
- **`warn_missing_guides(payload)`** (distill.py:859): after the existing build-guide warn loop, also log
  un-triaged **leveling** ascendancies from `untriaged_leveling(payload, doc)` (non-blocking, `⚠ ascendancy
  '<asc>' has no leveling guide (add it to guides.json leveling or levelingUnguided list)`), and keep the single
  existing patch-drift warning as-is (the shared `patch` covers both maps). The function's `missing` return is
  build-guides-only today and is consumed only by `test_distill` + CLI — leave the return shape unchanged
  (the leveling triage is asserted directly via `untriaged_leveling` in the test, not via this return).
- **`scripts/test_distill.py`:** extend the guides test to (1) validate the `leveling`/`levelingUnguided` shape
  via `guides_schema_errors`, and (2) assert every live (bundled-demo default-league) ascendancy is **triaged**
  for leveling — present in `leveling` OR `levelingUnguided`. An un-triaged new ascendancy **fails CI** (the
  same bite that protects the build guides). Runs in `test.yml`.

## Curation seed (from the rev2 WebSearch sweep — verify each link before recording)

The verification sweep already found a current leveling pick for **all 10** live default-league
(`runesofaldur`) ascendancies. Use this as the seed for the `guides.json` `leveling` map; the build's curation
step is mostly transcription + a click-verify (especially the flagged abyssal-lich). Key by the **real slug**
from live `data.json` (`slugOf({asc, skill:""})`) — confirm the slug spelling against the live league rather
than trusting this table's keys. `levelingUnguided` ships **empty** (no live ascendancy needs it right now).

| slug | source | url | note |
|---|---|---|---|
| `martial-artist` | Deltia's Gaming | `https://deltiasgaming.com/path-of-exile-2-0-5-monk-martial-artist-leveling-guide/` | dedicated 0.5 Monk leveling |
| `spirit-walker` | PoE Vault | `https://www.poe-vault.com/poe2/huntress/spirit-walker/companion-leveling-build` | dedicated companion leveling |
| `deadeye` | Maxroll | `https://maxroll.gg/poe2/build-guides/lightning-arrow-deadeye-leveling-build-guide` | dedicated; same source+skill as build guide (cleanest) |
| `gemling-legionnaire` | Maxroll | `https://maxroll.gg/poe2/build-guides/grenade-mercenary-leveling-guide` | dedicated Grenade Merc leveling, covers Gemling |
| `oracle` | Maxroll | `https://maxroll.gg/poe2/build-guides/the-shapeshift-druid-leveling-guide` | dedicated Shapeshift Druid leveling, covers Oracle |
| `stormweaver` | Maxroll | `https://maxroll.gg/poe2/build-guides/spark-archmage-stormweaver-leveling-guide` | dedicated Spark Stormweaver leveling |
| `disciple-of-varashta` | Maxroll | `https://maxroll.gg/poe2/build-guides/disciple-of-varashta-plant-build-guide` | the existing build-guide URL — has a real leveling section (preferred same-source case) |
| `blood-mage` | Maxroll | `https://maxroll.gg/poe2/build-guides/fireball-blood-mage-leveling-guide` | dedicated Fireball Blood Mage leveling |
| `abyssal-lich` | Mobalytics (deadrabb1t) | `https://mobalytics.gg/poe-2/builds/plants-lich-deadrabb1t` | ⚠ **click-verify** — Mobalytics 403s automated fetch, so confirmed via search snippet only; the one asc with no Maxroll dedicated leveling guide (witch league-starter → Abyssal Lich). If it doesn't hold up on a manual open, drop to `levelingUnguided`. |
| `titan` | Maxroll | `https://maxroll.gg/poe2/build-guides/boneshatter-titan-leveling-guide` | dedicated Boneshatter Titan leveling (different skill than the build guide, same host) |

- **Patch note (non-blocking):** several picks show 0.5.4 ("Return of the Ancients") in their titles — *ahead* of
  guides.json's `0.5.3` field, which is fine (the pointers are current). The shared `patch`/`updated` belong to
  the build-guides side and the existing patch-drift warn already covers them; **do not** change `patch` as part
  of this feature. Set `updated` to `2026-06-27` when the leveling map is added.
- **Curation rule (general, for re-curation / other leagues):** WebSearch "PoE2 <Ascendancy> leveling guide",
  open/skim the top reputable result (Maxroll/PoE Vault/Mobalytics/Deltia's/established creators), confirm it's
  current for 0.5.x and is actually a **leveling** guide (or a build guide with a real leveling section), record
  `{url, source}`. No solid current guide → `levelingUnguided` (neutral search), never a forced weak pick.
- Record honestly: `source` is the host/creator; the UI says "a community leveling guide", not "best".

## Testing

- **Python (`test_distill.py`):**
  - **Optionality lock (HIGH):** `guides_schema_errors` on a doc with **no** leveling keys returns `[]` (the
    existing `test_shipped_guides_json_valid_and_complete` already asserts this on the real file — confirm it
    still passes *before* the `leveling` map is added, and after).
  - `guides_schema_errors` **accepts** a valid `leveling`/`levelingUnguided` and **rejects** a bad one (non-http
    url, empty source, slug in both `leveling` and `levelingUnguided`, non-list `levelingUnguided`).
  - `untriaged_leveling` **fails** (returns the slug) on an un-triaged leveling ascendancy and returns `[]` when
    all live ascendancies are triaged; `test_shipped_guides_json_valid_and_complete` asserts
    `untriaged_leveling(payload, doc) == []` against the shipped file + live `data.json` (the coverage-lock).
  - `python scripts/test_distill.py` green (was 49 OK; new assertions add to that).
- **Front end (preview):** a slug with a `leveling` entry shows "{source} leveling ↗" with the right href +
  title next to the build-guide link **in the ledger row** (separated by `·`); an un-curated one shows the
  neutral "leveling ↗" search; **The Prescription** shows a neutral "leveling ↗" beside its "guide ↗"; row
  click still toggles (link clicks ignored); `guides.json` fetch fail-safe (rename → neutral leveling search
  everywhere, no break); 0 console errors.
- Suites stay green; CI (`test.yml`) runs the new Python assertions.

## Rollout

Pure static + the existing hourly guard. Deploys with the `index.html` + `guides.json` + `distill.py` commit.
Branch off `main`; standard finish (the owner's merge/PR choice).

## Docs

- **`README.md:155`** — add a sibling bullet right after the "Curated build guides" line:
  `- [x] **Curated leveling guides** — a hand-picked community *leveling* guide per live ascendancy
  (`guides.json` `leveling` map), shown as *"{source} leveling ↗"* next to the build-guide link on each ledger
  row and in The Prescription, with the neutral web search as the fallback where none is vetted. Same CI
  coverage-lock + hourly non-blocking warn as the build guides, so leveling picks can't silently go stale.`

## Integration points (verified anchors)

- `guides.json`: new `leveling` map + (empty) `levelingUnguided` list (root); bump `updated` → `2026-06-27`.
- `index.html`: new `levelingUrl`/`levelingLinkHTML` beside `guideUrl` [1836] / `guideLinkHTML` [1842];
  **two** render sites — curated `levelingLinkHTML(b)` as a new `subBits` element after `guideLinkHTML(b)`
  [2277] (`" · "` join at 2303 auto-separates), and a neutral `levelingUrl(c.b)` link after the neutral
  `guideUrl(c.b)` link in `.rx-acts` [3085]; hero [2419] intentionally **not** touched. `GUIDES` promoted
  [3333] (no change). `.guide-link` CSS [176] reused (no new CSS).
- `scripts/distill.py`: `guides_schema_errors` [503] (+optional leveling, presence-guarded), new
  `untriaged_leveling(payload, doc)` beside `untriaged_guides` [530] (parallel, no refactor),
  `warn_missing_guides` [859] (+leveling warn loop).
- `scripts/test_distill.py`: extend the `Guides` class [473-511] — schema accept/reject for leveling, a leveling
  triage assertion, and extend `test_shipped_guides_json_valid_and_complete` to assert the live set is triaged
  for leveling once the `leveling` map ships.
- `README.md`: add the leveling-guides bullet [after 155].

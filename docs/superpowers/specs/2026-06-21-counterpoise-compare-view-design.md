# The Counterpoise — side-by-side ascendancy comparison

**Status:** approved design · **Date:** 2026-06-21 · **Type:** front-end feature (no backend, no new data)

## Overview

A new client-only section, **The Counterpoise**, lets a user put 2–3 ascendancies side by side and
read their vitals, defence layer, and build composition in one table — directly serving the site's
core job ("what should I play?"). The name fits the apothecary theme: a counterpoise is the weight
you balance against another on a scale.

Everything it needs is already in `meta-detail.json` (loaded at boot as `META`) and the league's
build list (`data.json`). There is **no new fetch, no new pipeline work, no new dependency** — it is
purely an additive front-end view in `index.html`.

## Goals

- Compare 2–3 ascendancies on the metrics that decide a build choice, in one glance.
- Reuse the exact data + honesty framing the ledger/build-view already use (no new claims).
- Be shareable via a URL hash, consistent with the existing `#asc`/`#league`/`#quiz` deep links.
- Stay on-ethos: static, no backend, fails safe, nothing fabricated.

## Non-goals (YAGNI)

- No custom metric picker, no user-defined columns, no >3 columns.
- No persistence beyond the URL hash (the site uses **no** browser storage).
- No computed "score" or declared overall "winner" (honesty — see Honesty guards).
- No new data fetched or precomputed in the pipeline.

## Data sources (all already in memory)

For a selected ascendancy slug `s` (where `s === slugOf(build)`):

- **Ledger build** — found in the current league's builds where `slugOf(b) === s`. Supplies:
  `asc`, `cls`, `tag` (playstyle), `pop`, `n` (sample), and the sample-confidence cue inputs.
- **`META.byAsc[s]`** — supplies:
  - `stats` → `{ ehp, dps, level, sample }` (medians, where the source reports them)
  - `build.defence` → `{ ehp, life, es, ward, resists{fire,cold,lightning,chaos}, evade, pdr, block, crit }`
    (precomputed by the reconstructor; present for all 23 ascendancies)
  - `skills`, `supports`, `uniques`, `notables`, `anointments`, `weapons` — each `{ name, pct }`
  - `build` (for the Decant) and `pob` (for "Copy PoB").

All 23 ascendancies have full `stats`, `build.defence`, and composition arrays (verified).

## Architecture & components (all in `index.html`)

- **State:** `compareSel` — an array of up to 3 slugs (the current selection). The single source of
  truth; the pickers, the row "vs" links, and the hash all read/write it.
- **`renderCompare()`** — renders the section: the picker controls reflecting `compareSel`, plus the
  comparison table for the current selection (or an empty prompt when `< 2` selected). Idempotent;
  safe to call on any selection change. Follows the structure of `renderAssay()`/`renderExchange()`.
- **`compareTableHTML(slugs)`** — pure builder: takes the slug list, returns the table HTML from the
  merged ledger-build + `META.byAsc[s]` data. No DOM/side effects → unit-testable.
- **`ascForCompare(s)`** — pure helper merging the ledger build + `META.byAsc[s]` into one column
  view-model (or `null` if the slug is unknown). Keeps `compareTableHTML` clean and testable.
- **Pickers:** 2 base `<select>` + an "add a third" control (revealed only when 2 are chosen);
  each `<select>` lists all ascendancies (from `META.byAsc`, labelled by `asc`), with the current
  pick selected. Changing/removing a picker updates `compareSel` → `writeCompareHash()` → `renderCompare()`.
- **Row shortcut:** in `renderRows()`, each ledger row gets a small **"vs"** affordance (an `<a>`/button)
  that adds the row's slug to `compareSel` (dedup, cap 3), updates the hash, re-renders, and
  smooth-scrolls to the section. It is an explicit action element so the existing row-toggle handler
  ignores it (the handler already early-returns on `a`/`.arch-btn`).
- **Deep link:** `parseCompareHash()` / `writeCompareHash()` integrated into the existing hash router
  (alongside `#asc`/`#league`/`#quiz`). On boot and `hashchange`, `#compare=slugA,slugB[,slugC]` sets
  `compareSel` (filtered to known, deduped, capped at 3) and renders. `writeCompareHash()` uses the
  same `replaceState`/no-history-spam approach as `writeAscHash()`.

## Comparison table layout

Columns = selected ascendancies (2–3); a **sticky left label gutter** names each row group.

- **Header (per column):** ascendancy name, class, playstyle tag, signature weapon (top of `weapons`),
  the sample-confidence cue, and a **Decant** button (reusing the existing decant path) + **PoB** copy.
- **Vitals:** median EHP, median DPS, level — labelled "median, where the source reports it"
  (identical framing to the build view).
- **Defence layer** (from `build.defence`): life, ES, ward (omit row if all null), the four resists
  (each showing a cap "✓" at 75), evade, block/PDR, crit.
- **Composition:** top 3 skills, top 3 supports, signature uniques (top 3), key notables (top 3) —
  each name with its `pct` share. **Shared entries highlighted:** any skill/support/unique/notable that
  appears in 2+ columns gets a subtle marker so overlap is obvious at a glance.

## Honesty guards

- **No "winner."** Each *numeric* row marks the column holding the higher value with a subtle gold
  accent as a **factual** cue only, beside a single standing note: *"higher isn't automatically better —
  survivability and damage trade off."* No aggregate score or overall winner is ever shown.
- **Provenance unchanged.** Same source as the ledger; EHP/DPS keep the "median, where reported"
  caveat; sample size is shown per column so a thin-sample pick is visible.
- **Fails safe.** Unknown slug → dropped from the selection. Missing field → "—". Never fabricates a
  value to fill a cell.

## Mobile

Sticky label gutter; 2 value columns fit a phone width; a 3rd horizontal-scrolls (label gutter stays
pinned). Reuses the Cluster-D mobile approach (viewport clamps, ≥36px touch targets for the pickers,
Decant, and "vs" links). Verified at ~377px.

## Error handling

- `renderCompare()` with `< 2` valid slugs → an inline prompt ("pick two ascendancies to compare"),
  not an error.
- Each column built independently; one malformed `META.byAsc` entry degrades to "—" cells, never
  aborts the table (same fail-safe stance as `renderRows()`).
- Hash parsing tolerates junk: unknown/duplicate slugs filtered; >3 truncated; empty → no table.

## Testing

- **Pure helpers** locked with the existing source-extraction harness (`tools/test-frontend.cjs`):
  `parseCompareHash` (junk/dedupe/cap/unknown filtering) and `writeCompareHash` round-trip, and a
  shared-entry detector if extracted. Add to the `test.yml` + `builds.yml` node test list (already wired).
- **Live preview verification:** pick via dropdowns → table renders; "vs" link from a ledger row adds +
  scrolls; `#compare=` deep link restores the selection on reload; shared-item highlight shows; Decant
  from a column works; 0 console errors; mobile (~377px) sticky gutter + 3-column scroll; CSP clean
  (no new external resources — inline styles/scripts only, already covered by the existing CSP).

## Integration points (where each piece plugs into `index.html`)

- New `<section class="section-frame counterpoise" id="compare" aria-label="Compare ascendancies">`
  placed near The Assay (analytics neighbourhood).
- `boot()` calls `renderCompare()` once after `META` is promoted (alongside `renderAssay()` etc.), and
  the hash router calls it on `#compare` changes.
- `renderRows()` row markup gains the "vs" affordance.
- The hash router (the `#asc`/`#league`/`#quiz` handler) gains `#compare` parsing.
- CSS added with the existing design tokens (no new colours/fonts); a `@media (max-width:480px)` block
  for the sticky-gutter/scroll behaviour.

## Out of scope / future

- A "share this comparison" copy-link button (the hash already makes it shareable; a button is a trivial
  later add if wanted).
- Comparing across leagues (current scope compares within the active league's data set).

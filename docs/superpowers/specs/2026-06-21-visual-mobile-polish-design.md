# Visual + mobile polish pass

**Status:** approved design · **Date:** 2026-06-21 · **Type:** front-end polish (CSS + 2 `title` attributes), no behavior change

## Overview

A targeted polish pass fixing concrete layout/usability issues found in a geometry audit of `index.html`
at 1280px and 377px. Desktop is clean; all findings are on mobile. Scope is CSS in the existing
`<style>` block plus two `title` attributes in render functions — no new deps, no behavior change, no
pipeline change. Must not disturb the (dense, hand-rolled) Assay chart geometry or any other section.

## Audit baseline (what's wrong, measured)

- **Horizontal scroll on mobile.** `.controls .sort` (the 4 sort buttons `popularity / rising / EHP / DPS`)
  is a ~369px group inside a 341px controls row; it doesn't wrap, so its right edge spills ~10–28px past
  the viewport → the whole page scrolls sideways at ≤390px.
- **Clipped ascendancy names.** `.bar-lab .a` (Assay share-bar labels) and `.cru-rowh .a` (Crucible row
  headers) use `overflow:hidden; text-overflow:ellipsis; white-space:nowrap` with **no `title`** — so
  "Gemling Legionnaire" / "Disciple of Varashta" truncate on mobile and the full name isn't recoverable.
- **Cramped tap targets on mobile** (below the ~44px ideal / the site's own 36px target): league
  `<select>` ~19px tall, folder button ~28px, class chips ~30px, search input ~29px, row-toggle ▸ 26×31px.
- Desktop (1280) and the `/b` landing pages: clean — no fixes.

## Fixes

### F1 — Sort group wraps (Tier 1, the bug)
Let the sort control wrap so it never overflows. In the mobile breakpoint (and/or on `.sort` itself),
ensure the 4 buttons flow to a second row when they don't fit. Keep them left-aligned and grouped.
**Done when:** no horizontal scroll at 360 / 377 / 390px (`document.documentElement.scrollWidth <= clientWidth + 2`); sort still functions; desktop unchanged.

### F2 — Un-clip ascendancy names (Tier 2)
1. Add `title="${esc(b.asc)}"` to the `.bar-lab .a` span (render at index.html:2453) and
   `title="${esc(r.asc)}"` to the `.cru-rowh .a` span (render at index.html:2623) — full name always
   available on hover/long-press, zero layout impact.
2. In the mobile breakpoint, let `.bar-lab .a` **wrap** (`white-space:normal; overflow:visible; text-overflow:clip`)
   so the full name shows — safe because a share-bar row can grow vertically.
3. Leave `.cru-rowh .a` as ellipsis (the Crucible is a fixed-row-height grid; wrapping would break it) —
   the new `title` covers it.
**Done when:** the longest names render fully in the Assay share bars on mobile; both spans carry a `title`;
the Crucible grid + share bars still render correctly (cell/bar geometry unchanged).

### F3 — Comfortable tap targets on mobile (Tier 2/3)
In the `@media (max-width:480px)` block, raise `min-height` to **≥36px** for: `.league-select`,
`.folder` button, `.chip`, `.ledger-search` input, and `.row-toggle` (give the toggle a little more
width/padding too). Use `min-height` + vertical padding; don't change desktop sizing.
**Done when:** each of those controls measures ≥36px tall at 377px; desktop unchanged; nothing overflows
as a result (re-run F1 check).

### F5 — The Still grid overflow at ≤375px (found during impl)
At ≤880px The Still stacks to one `1fr` column, but the copy column's min-content (~359px, from an
unbreakable source-credit string) floors the track above the container, so anything narrower than 377px
scrolls sideways. Fix: in the ≤880px block, `grid-template-columns:minmax(0,1fr)`, `.still-grid > *{min-width:0}`,
`.still-copy{overflow-wrap:break-word}`, `.still-svg{max-width:100%;height:auto}`. **Done when:** no horizontal
scroll at 360px.

### F6 — Stat/counter grids overflow at ≤320px (found during impl)
`.counters` (`repeat(2,1fr)`) and `.stat-grid` columns are floored by their labels' min-content, overflowing
on very narrow phones. Fix (mobile block): `.stat-grid > *, .counters > *{ min-width:0 }` so columns shrink and
labels wrap. **Done when:** no element overflows at 360px (a sub-pixel/pseudo-element residual at 320px — the
rare iPhone-SE-1 width — is acceptable; 360px is the supported floor).

### F4 — Control-row tidy (Tier 3, measurable)
Confirm the controls row (chips + sort + search) wraps cleanly with consistent gaps once the sort wraps
(F1) and targets grow (F3) — no overlap, even spacing. Adjust the controls `gap`/`row-gap` only if the
audit shows uneven spacing. Minimal; mostly falls out of F1+F3.
**Done when:** at 360/377/390px the controls wrap without overlap and with consistent spacing (measured).

## Non-goals (YAGNI)
- No open-ended aesthetic redesign / re-theming (screenshots are unavailable in this environment, so
  purely-subjective "prettiness" beyond the measured fixes is out of scope — flag for the owner's eye).
- No markup restructuring beyond the two `title` attributes. No JS behavior change. No new colours/fonts/deps.

## Testing
- **Geometry probe** (preview_eval) at 360 / 377 / 390px: assert no horizontal scroll; the named tap
  targets ≥36px tall; `.bar-lab .a` full text visible (scrollWidth ≤ clientWidth) and both `.a` spans have
  a `title`.
- **Regression**: desktop (1280) re-probe — `.wrap` still centered, no new overflow, section heads aligned;
  the Assay charts (donut/bars/Crucible) and the ledger still render (row counts, chart element counts
  unchanged); 0 console errors.
- **Inline-JS syntax** (comment-stripped robust check) OK; the existing Node + Python suites stay green.

## Integration points (index.html)
- `<style>`: `.controls .sort` wrap (F1); the `@media (max-width:480px)` block — `.bar-lab .a` wrap (F2),
  tap-target `min-height`s (F3), controls `gap` if needed (F4).
- Render functions: add `title` to `.bar-lab .a` (~2453) and `.cru-rowh .a` (~2623) (F2).

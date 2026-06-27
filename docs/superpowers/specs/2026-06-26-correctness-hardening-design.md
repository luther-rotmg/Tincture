# Correctness & Honesty Hardening

**Status:** approved design · **Date:** 2026-06-26 · **Type:** bug-fix sweep (front-end + pipeline)
**Branch:** `feature/correctness-hardening` (stacked on `feature/look-feel-voice` → ② → ①)

## Overview

Workstream ③ of the post-audit program. A focused set of correctness and honesty fixes the audit found —
each one produces wrong, misleading, or dead output today:

- **A.** The trend arrow is a **~1-hour** delta (diff vs the last committed snapshot) but is labeled
  **"24-hour"** everywhere. Relabel it to the truth ("since last refresh") — no change to the delta itself.
- **B.** The Counterpoise per-column **Decant silently does nothing** for the 6 ascendancies not in the
  active ledger's top-N.
- **C.** The variant **fallback export is mislabeled and all-null** when a variant's real `.build` is
  unavailable (drops the `-2`/`-3` slug suffix, blank meta fields).
- **D.** `relTime` renders **"NaN min ago"** on a malformed timestamp (its sibling `absTime` is guarded).
- **E.** The apportionment **>100%-share clamp is untested** in `test_distill.py` (the one case where the
  anti-inflation clamp actually matters).

B/C/D are front-end (`index.html`, browser-preview-verifiable). A spans `index.html` labels + a `distill.py`
docstring; E is `test_distill.py` (Python → CI-verified; Python isn't installed locally).

## Goals

- Every trend label states what the delta actually is (since the last refresh), not a 24h window it isn't.
- Every Counterpoise column's Decant works — including the 6 non-top-N ascendancies.
- The variant fallback (if ever hit) names the file with the real variant slug and carries real meta fields.
- No timestamp ever renders "NaN".
- The anti-inflation apportionment clamp has a test that exercises the >100%-share path.

## Non-goals (YAGNI)

- **No change to the delta computation** — it stays a since-last-snapshot diff (the chosen fix is relabel,
  not recompute; a real 24h delta was explicitly declined because `history.json` only holds the default
  league's shares).
- **No** new features; **no** changes to the build-view/Decant happy path, the Earned-Confidence (①) or
  Look-Feel-Voice (②) code, or the ledger ranking.
- **Deferred** lower-priority audit items (confidence-meter saturation, style-attribute numeric coercion,
  history `Math.max` spread, exVal sub-unit rounding) — not correctness bugs; out of this sweep.

## Honesty guardrails

- A label must match the quantity it labels: the delta is "since the last refresh," so that is what every
  surface (UI text, tooltip, CSV column, code docstring/comment) must say. No "24-hour" claim survives.
- The variant fallback is an honesty path (a non-loadable `.txt`); fixing it must keep it clearly a labelled
  template, never imply a loadable build — and must name the correct pick.

## A — Relabel the trend (it's "since last refresh", not 24h)

Replace every "24-hour"/"24 hours"/"24h" trend reference. Confirmed `index.html` sites:
- Ledger header hint, [1141](index.html:1141): tooltip `Change in share over 24 hours. Reads 'baseline'…` →
  `Change in share since the last refresh. Reads 'baseline'…`.
- Crucible/ledger baseline cell, [2281](index.html:2281): `title="24-hour trends appear once enough hourly
  snapshots accumulate"` → `title="trends appear once enough hourly snapshots accumulate"`.
- Ledger foot, [2377](index.html:2377): `Trend = 24-hour change in share.` → `Trend = change in share since
  the last refresh.`
- Cellar disclaimer, [2908](index.html:2908): `24-hour trends read baseline…` → `Trends read baseline…`.
- CSV export header, [2877](index.html:2877): `trend_24h` → `trend_since_refresh`.
- Internal normalized field, [1619](index.html:1619): `trend24h: b.delta ?? null` — rename the key to
  `trendDelta` and update its readers (grep `trend24h` across the file; rename all, or keep the key and only
  fix labels if any reader is fragile — verification will enumerate the readers so the plan picks the safe path).
- `scripts/distill.py`: the module docstring / any comment that says it "computes 24h trend deltas" →
  "since-last-snapshot trend deltas" (verification will pin the exact line; `apply_trends`'s own docstring is
  already window-agnostic and stays).

No behavior change — only labels/strings/comments. The delta math (`apply_trends`) is untouched.

## B — Counterpoise per-column Decant for all ascendancies

`renderCompare`, [2165-2169](index.html:2165): today
```js
const b = (curLeague().builds||[]).find(x => slugOf(x) === btn.dataset.slug);
if (b) decant(b);
```
For the 6 ascendancies not in the active league's top-N ledger, `find` returns `undefined` and the click is a
silent no-op. Fix: when no ledger build matches, synthesize a minimal pick from `META.byAsc[slug]` and Decant
with the slug override — mirroring the existing variant Decant (`bv-var-decant`, which calls
`decant({asc, cls, skill:""}, slug)`). Shape:
```js
const slug = btn.dataset.slug;
const b = (curLeague().builds||[]).find(x => slugOf(x) === slug);
if (b) { decant(b); return; }
const md = META && META.byAsc && META.byAsc[slug];
if (md) decant({ asc: md.asc, cls: md.cls || null, skill: "" }, slug);
```
Verification will confirm the exact `decant(b, slugOverride)` signature and the `bv-var-decant` precedent so
the plan uses the real parameter name. `decant()` then manifest-gates the slug and serves the real `.build`
or the honest template, as it already does for variants — so this stays honest for non-reconstructed picks.

## C — Variant fallback names the real pick + carries real fields

In `decant()` (~[1690-1700](index.html:1697)) the honest fallback writes
`saveBlob(templateText(b), slugOf(b) + "-tincture-template.txt", …)`. When `decant` was called with a slug
override (a variant, or B's synthesized pick) whose real `.build` is unavailable, `slugOf(b)` ignores the
override (so a variant exports as the base slug) and `b` may be a stub with null `cls/pop/n/delta` (so the
template body is all-null). Fix: thread the override slug into the fallback filename, and enrich `b` from the
ledger/`metaFor` before building `templateText` so the template carries the real ascendancy fields.
Verification will extract the exact current `decant()` signature, the override parameter, and the
`templateText`/`metaFor` helpers so the plan's edit is precise and the happy path is untouched.

## D — `relTime` NaN guard

`relTime`, [1566-1575](index.html:1566): `Math.max(0, Date.now() - new Date(iso).getTime())` yields `NaN` for
a malformed/absent `iso`, rendering "NaN min ago". Mirror `absTime`'s guard — add at the top:
```js
if (!iso || isNaN(new Date(iso).getTime())) return "—";
```
A sentinel (`"—"`) keeps the callers' `"refreshed " + relTime(…)` reading "refreshed —" rather than
"refreshed " or "refreshed NaN min ago".

## E — Apportionment >100%-share test

`scripts/test_distill.py`: add a case feeding `_apportion_n` (or the public path that calls it) shares that
sum **> 100%** (e.g. five rows at 25% each = 125% against a known `total`) and assert `sum(n) <= total` — the
`target = min(total, round(sum(exacts)))` clamp is the anti-inflation guard and is currently untested.
Verification will pin the exact function name/signature and the existing test style. (Optionally tighten the
`<= characters + 1` tolerance in `test_no_inflated_totals` to `<= characters` for non-curated leagues, if
verification confirms the apportionment guarantees it.) Python → runs in CI (`test.yml`); not locally
runnable (Python not installed).

## Testing / verification

- **A (labels):** browser preview — the ledger hint, baseline tooltip, ledger foot, and Cellar disclaimer all
  say "since the last refresh" / no "24-hour"; the CSV export header is `trend_since_refresh`. `grep` confirms
  no "24-hour"/"24h" trend reference remains in `index.html`; `distill.py` docstring updated.
- **B:** preview — open The Counterpoise, compare a top-N ascendancy with one of the 6 non-top-N ones (e.g.
  Pathfinder/Amazon/Shaman), click that column's Decant → it Decants (real `.build` or honest template), no
  silent no-op; 0 console errors.
- **C:** preview/logic — a variant Decant whose `.build` is forced unavailable falls back to a `.txt` named
  with the **variant** slug and with real ascendancy fields (not all-null). (Hard to trigger naturally; verify
  by code inspection + a forced 404 in the preview.)
- **D:** preview — call `relTime("not-a-date")` in the console → returns `"—"`, never "NaN".
- **E:** `python scripts/test_distill.py` in CI → the new >100%-share test passes (and the suite stays green).
- Full suites stay green; 0 console errors across the page.

## Rollout

Stacked on `feature/look-feel-voice` (different `index.html` regions than ①/②, plus untouched
`distill.py`/`test_distill.py` — no conflict). Front-end fixes deploy with the `index.html` commit; the
`distill.py` docstring is cosmetic; the new test runs in CI. At finish, PR base = `feature/look-feel-voice`,
retarget up the chain as ①→②→③ merge.

## Integration points (verify by anchor)

- `index.html`: trend labels [1141, 2281, 2377, 2877, 2908], `trend24h` field [1619] + its readers;
  `renderCompare` `.cmp-decant` handler [2165-2169]; `decant()` fallback [~1697] + `templateText`/`metaFor`;
  `relTime` [1566-1575].
- `scripts/distill.py`: module docstring / 24h comment (verify line); `apply_trends` unchanged.
- `scripts/test_distill.py`: new >100%-share apportionment test; optional `+1`-tolerance tightening.

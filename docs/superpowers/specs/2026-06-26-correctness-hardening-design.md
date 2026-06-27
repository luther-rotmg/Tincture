# Correctness & Honesty Hardening

**Status:** approved design (rev. 2, post adversarial verification) · **Date:** 2026-06-26 · **Type:** bug-fix sweep (front-end + docs + pipeline test)
**Branch:** `feature/correctness-hardening` (stacked on `feature/look-feel-voice` → ② → ①)

## Overview

Workstream ③ of the post-audit program. A focused set of correctness/honesty fixes the audit found — each
produces wrong, misleading, or dead output today:

- **A.** The trend arrow is a **~1-hour** delta (diff vs the last committed snapshot) but is labeled
  **"24-hour"** in the UI, the CSV header, the JSON-LD, and the README. Relabel to "since last refresh" /
  "since-last-snapshot" — **no change to the delta math.**
- **B.** The Counterpoise per-column **Decant silently does nothing** for the ascendancies not in the active
  ledger's top-N.
- **C.** The variant **fallback export drops the `-2`/`-3` slug suffix and is all-null** when a variant's real
  `.build` is unavailable.
- **D.** `relTime` renders **"NaN min ago"** on a malformed timestamp (its sibling `absTime` is guarded).
- **E.** The apportionment **>100%-share clamp is untested** in `test_distill.py`.

### Verified premises (from the adversarial spec review)

- **The `distill.py` docstring task is a PHANTOM** — there is no "24h"/"24-hour" string anywhere in
  `distill.py`; `apply_trends`'s docstring already says "previous snapshot" (window-agnostic). Dropped.
- **A was incomplete** — four more "24-hour"/"24h" trend references exist: `index.html:36` (JSON-LD
  description), `index.html:1356` (data-access footer), and `README.md` lines 17/33/119/133. Added.
- **`decant`'s signature is `async function decant(b, slugOverride)`** (index.html:1679); the variant
  precedent is `decant({ asc, skill:"" }, slug)` — **no `cls`**. And **`META.byAsc` entries carry `asc` but
  no `cls`** — so the B stub is `{ asc, skill:"" }`, not `{asc, cls, skill}`.
- **C is a two-line fix:** the fallback at `index.html:1697` uses `slugOf(b)` (override-blind) for the
  filename while the real-build path at 1695 already uses the override-aware local `slug`; plus enrich `b`
  from the ledger row so the template body isn't all-null. Both additive; the happy path (1695,
  `saveRealBuild`) is untouched. `templateText`'s NOT-loadable banner stays — honesty preserved.
- **B/C never fabricate:** the synthesized/variant pick routes through the manifest gate + honest `.txt`
  fallback exactly as today.

## Goals

- Every trend label states what the delta is (since the last refresh) — no "24-hour" claim survives anywhere
  user-facing.
- Every Counterpoise column's Decant works (real `.build` or honest template), no silent no-op.
- The variant fallback names the file with the real variant slug and carries the ascendancy's real fields.
- No timestamp renders "NaN".
- The anti-inflation apportionment clamp has a test exercising the >100%-share path.

## Non-goals (YAGNI)

- **No change to the delta computation** (relabel, not recompute — a real 24h delta was declined).
- **No** changes to the ledger ranking, the Decant/build-view happy path, or the ①/② code.
- **Deferred:** lower-priority audit items (confidence-meter saturation, style-attr coercion, history
  `Math.max` spread). `docs/demo.svg`'s "24H" axis label is a generated demo asset — not worth regenerating;
  left as-is.

## Honesty guardrails

- A label must match the quantity it labels: the delta is since the last refresh, so every surface says so.
- The variant/synthesized fallback stays a clearly-labelled non-loadable `.txt` (banner + `.txt` suffix +
  toast); fixes are additive and never imply a loadable build, never fabricate a share.

## A — Relabel the trend (it's "since last refresh", not 24h)

**`index.html` user-facing (5 + 2 missed):**
- [1141] ledger hint `data-tip="Change in share over 24 hours. Reads 'baseline'…"` → `"Change in share since
  the last refresh. Reads 'baseline'…"` (note the source uses curly quotes around 'baseline' — match exactly).
- [2281] baseline cell `title="24-hour trends appear once enough hourly snapshots accumulate"` → `title="trends
  appear once enough hourly snapshots accumulate"`.
- [2377] ledger foot `Trend = 24-hour change in share.` → `Trend = change in share since the last refresh.`
  (the `trendsReady` branch only).
- [2908] Cellar disclaimer `24-hour trends read <b>baseline</b>…` → `Trends read <b>baseline</b>…`.
- [2877] CSV header `"trend_24h"` → `"trend_since_refresh"` (value cell at 2880 unchanged).
- [36] JSON-LD description `…ranked ascendancy shares, 24h trends, and per-league…` → `…since-last-refresh
  trends…`.
- [1356] data-access footer `…24-hour trends sit at baseline until snapshots accumulate.` → `…Trends sit at
  baseline until snapshots accumulate.`

**`index.html` internal (template export field):**
- [1619] `trend24h: b.delta ?? null,` → `trendSinceRefresh: b.delta ?? null,`. **Safe** — `trend24h` is the
  sole occurrence in the repo and has zero readers (it's a write-only key in `templateText`'s exported
  `.txt` JSON body). (This line lives inside `templateText`, which C also edits — coordinate.)

**`README.md` (published, user-facing):**
- [17] `…with 24-hour trend arrows that light up once a day of snapshots has accumulated.` → `…with trend
  arrows that light up once a day of snapshots has accumulated.` (keep the accumulation cadence clause).
- [33] `…computes each build's 24-hour movement by diffing the previous snapshot.` → `…computes each build's
  movement since the last refresh by diffing the previous snapshot.`
- [119] `…against the previous snapshot for the 24-hour trend arrows.` → `…against the previous snapshot for
  the trend arrows.`
- [133] `…ascendancy shares + 24h trend` → `…ascendancy shares + since-last-refresh trend`.

**`CLAUDE.md` (project memory — the actual source of the "24h trend deltas" premise):**
- The Pipeline bullet phrasing `… → 24h trend deltas (diff vs previous snapshot) …` → `… → since-last-snapshot
  trend deltas (diff vs previous snapshot) …` (one line; kills the recurring premise).

**`scripts/distill.py`: NO CHANGE** — there is no "24h" string to fix (`apply_trends` already says "previous
snapshot"). The phantom docstring task is dropped.

No behavior change — only labels/strings. The delta math (`apply_trends`) is untouched.

## B — Counterpoise per-column Decant for all ascendancies

`renderCompare` `.cmp-decant` handler (index.html:2165-2169) — today the `if (b) decant(b)` with no `else` is a
silent no-op when the slug isn't a top-N ledger build. Replace the handler body with (additive — the top-N
path is byte-identical):
```js
  wrap.querySelectorAll(".cmp-decant").forEach(btn => btn.addEventListener("click", e => {
    e.stopPropagation();
    const slug = btn.dataset.slug;
    const b = (curLeague().builds||[]).find(x => slugOf(x) === slug);
    if (b) { decant(b); return; }
    const md = META && META.byAsc && META.byAsc[slug];
    if (md) decant({ asc: md.asc, skill: "" }, slug);   // synthesize a pick; decant() manifest-gates the slug
  }));
```
`decant(b, slugOverride)` (async, index.html:1679) manifest-gates the override `slug` and serves the real
`.build` or the honest `.txt` template — so a non-reconstructed ascendancy gets the labelled template, never a
fabricated build. The stub is `{ asc, skill:"" }` (`META.byAsc` carries no `cls`; the variant precedent passes
no `cls` either). When `md` is absent the new branch is a guarded no-op (won't throw).

## C — Variant fallback names the real pick + carries real fields

In `decant()`, the honest-fallback tail (index.html:1697):
```js
  saveBlob(templateText(b), slugOf(b) + "-tincture-template.txt", "text/plain;charset=utf-8");
```
Two additive fixes (the real-build path at 1695 and `saveRealBuild` are untouched):
1. **Filename:** `slugOf(b)` → `slug` (the override-aware local from line 1680, `slugOverride || slugOf(b)`),
   so a variant exports as `<slug>-N-tincture-template.txt`, not the base slug.
2. **Enrich the body:** before building the template, fill the stub from the ascendancy's ledger row so
   `pop/n/delta/cls/tag` aren't null (a variant's asc == its primary's asc, so the lookup by asc-slug is
   correct):
   ```js
   const lrow = (curLeague().builds||[]).find(x => slugOf(x) === slugOf(b));
   if (lrow) b = { ...lrow, ...b };   // ledger share/sample/cls/tag under the stub's asc/skill
   ```
   For the 6 non-top-N (B's synthesized) picks there is no ledger row, so `pop/n/delta` stay null — honest
   (no share data exists for them); `templateText`'s `tagFor` still resolves a playstyle via `ASC_TAGS`.
The `.txt` banner / suffix / toast all keep it clearly non-loadable.

## D — `relTime` NaN guard (+ a trivial sibling)

`relTime` (index.html:1566) — add at the top, mirroring `absTime`:
```js
  if (!iso || isNaN(new Date(iso).getTime())) return "—";
```
A `"—"` sentinel reads correctly at the verified callers ("refreshed —", "reconstructed —", "as of —").
**Fold in** the analogous one-token guard the audit flagged in `animateCounters` (index.html:2940): `const
target = +el.dataset.count;` → `const target = +el.dataset.count || 0;` (matches the already-guarded
reduced-motion path at 2456, prevents a "NaN" counter). `trendHTML` is already caller-guarded — leave it.

## E — Apportionment >100%-share test

`scripts/test_distill.py` — add a third method to the existing `Apportion(unittest.TestCase)` class
(test_distill.py:300), mirroring `test_derived_n_never_sums_above_total`:
```python
    def test_derived_n_clamped_when_shares_exceed_100(self):
        # poe.ninja top-N shares can sum to >100% (overlap/rounding); the apportionment
        # clamp (target = min(total, round(sum(exacts)))) must never inflate n past the population.
        league = {"total": 1000, "statistics": [
            {"class": "Titan", "percentage": 25.0}, {"class": "Deadeye", "percentage": 25.0},
            {"class": "Lich", "percentage": 25.0}, {"class": "Invoker", "percentage": 25.0},
            {"class": "Infernalist", "percentage": 25.0}]}   # 125% total
        rows, total = distill.normalize_one(league)
        self.assertLessEqual(sum(r["n"] for r in rows), total)
```
(Goes through the public `normalize_one` — the only caller of the private `_apportion_n(rows, total)` at
distill.py:296; the clamp is at distill.py:313. Use real mapped ascendancies to avoid the unmapped-class
warning.) **Skip** the optional `+1`-tolerance tightening (the `+1` is intentional defensive slack; tightening
is low-value and risks the demo/curated edge). Python → runs in CI (`test.yml`); not locally runnable.

## Testing / verification

- **A:** preview — the ledger hint, baseline tooltip, ledger foot, Cellar disclaimer, and data-access footer
  say "since the last refresh"/no "24-hour"; CSV export header is `trend_since_refresh`. `grep -i "24.\?h"`
  across `index.html` + `README.md` + `CLAUDE.md` shows no trend "24-hour"/"24h" reference remains (demo.svg
  excepted).
- **B:** preview — compare a top-N ascendancy with a non-top-N one (e.g. Pathfinder/Amazon/Shaman if present
  in `META.byAsc`); click that column's Decant → it Decants (real `.build` or honest `.txt`), no silent
  no-op; 0 console errors.
- **C:** verify by inspection + a forced 404: a variant fallback writes `<slug>-N-tincture-template.txt` (not
  the base slug) and the template body carries the ascendancy's share/playstyle (not all-null).
- **D:** console — `relTime("nope")` → `"—"` (never "NaN"); a counter with no `data-count` shows `0`, not "NaN".
- **E:** `python scripts/test_distill.py` in CI → the new test passes, suite stays green.
- Full suites green; 0 console errors across the page.

## Rollout

Stacked on `feature/look-feel-voice` (different `index.html` regions than ①/②; `README.md`/`CLAUDE.md`/
`test_distill.py` untouched by them — no conflict). Front-end deploys with the `index.html` commit; the test
runs in CI. PR base = `feature/look-feel-voice`, retarget up the chain as ①→②→③ merge.

## Integration points (verified anchors)

- `index.html`: trend labels [1141, 2281, 2377, 2877, 2908, 36, 1356], `trend24h`→`trendSinceRefresh` [1619];
  `renderCompare` `.cmp-decant` [2165-2169]; `decant()` fallback [1697] + local `slug` [1680] +
  `templateText`/`tagFor` [1603, 1484]; `relTime` [1566-1575]; `animateCounters` [2940].
- `README.md`: [17, 33, 119, 133]. `CLAUDE.md`: the Pipeline "24h trend deltas" line.
- `scripts/distill.py`: NO change (`_apportion_n` [296], clamp [313], `normalize_one` [290] referenced by the test).
- `scripts/test_distill.py`: new method in `Apportion` [300].

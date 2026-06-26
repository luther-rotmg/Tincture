# Look, Feel & Voice — visual uniformity + confident, honest copy

**Status:** approved design (rev. 2, post adversarial verification) · **Date:** 2026-06-26 · **Type:** front-end sweep (CSS + markup + copy)
**Branch:** `feature/look-feel-voice` (stacked on `feature/earned-confidence` until ① merges)

## Overview

Workstream ② of the post-audit program. A single coherent front-end sweep of `index.html` that makes the
page read as one deliberate, uniform design and gives a newcomer a clear, confident path — while keeping the
project's honesty stance. Three layers — **LOOK** (visual uniformity + two token bugs), **FEEL** (one clear
hero action), **VOICE** (assert measured facts boldly, caveat the unmeasured once).

All changes are in `index.html` (inline CSS, markup, copy). No pipeline / data / `meta-detail.json` changes;
no `pop`/`rank`/`tier`/ledger edits. Verified locally in the browser preview.

### Verified premises (from the adversarial spec review — all anchors confirmed against the current file)

- `--bg` is genuinely never declared; used once at `.cmp-table th[scope="row"]` (line 322). `--ink-2` (#1b1610,
  "raised panels") is the right substitute.
- `.section-sub` has **no** CSS rule; the Counterpoise intro (`<p class="section-sub">`, line 1225) sits inside
  `<header class="section-head">`, so renaming the class to `sub` makes it match the defined `.section-head .sub`
  (line 559) — a **markup** one-word change.
- **`border-radius:4px` appears at TWO sites:** `.prescription` (line 942, removed by L1) **and** a dialog/modal
  panel (line 473). Both must change for "no 4px remains" to hold.
- `.prescription .gt-title` overrides to `font-family:var(--fdisplay)` (Cinzel) `font-size:21px` (line 945) — the
  find target is `var(--fdisplay)`, not a literal "Cinzel".
- The `.prescription.open{ background:… }` faint-ground grace note **does not exist yet** — it's a NEW rule; the
  current always-on gradient is on base `.prescription` (line 943), which L1 removes.
- `.still` (lines 347-350) duplicates `.section-frame` exactly except a drifted bottom pad (`46` vs `30`).
- The Prescription toggle JS (`setRx`/`openQuiz`, lines 3108-3120) reads only `#prescription`/`#rxToggle`/`.open`
  — it references nothing about the box, padding, or title, so de-boxing **cannot break the toggle**.
- The footer (line 1372) already links `#assay` and `#archive`, so removing those two hero shortcuts strands no
  navigation.
- `"actually winning"` appears once (line 1237, The Still) — **not** in the hero/JS, and **not** in README
  (the README-consistency check is a no-op).

## Honesty guardrails (load-bearing)

- Assert only what the data measures. Popularity is fact ("X% of the live ladder is on it") — state it boldly.
  Power/win-rate/survival is **not** measured — never imply it ("winning", "best", "safest", "optimal").
- **Never promise "loadable" for a pick that may fall back to the `.txt` template.** The headline pick's
  loadability depends on the `builds/index.json` manifest gate; the hero subhead must not assert it
  unconditionally.
- One honest caveat per concept, placed once. The "popularity, not a strength score" caveat survives explicitly
  in exactly one place (the quiz footnote).
- Lead with what the user got + the next action; the caveat is a forward-leaning footnote, never a dead end.

## LOOK

### L1 — The Prescription rejoins the spine (the headline ask)
Make `.prescription` (CSS 942-948) the **twin of `.guide`** (403-413):
- Base rule (942-943): remove `border`, `border-radius:4px`, `margin:34px 0`, `padding:22px 28px`, and the
  always-on `background:linear-gradient(…)`. Replace with `border-bottom:1px solid var(--hair)` (the guide's
  divider) and `margin:0`.
- `.prescription .guide-toggle{ padding:0 }` (944) → `padding:22px 0` (match `.guide-toggle`, line 406).
- `.prescription .gt-title{ font-family:var(--fdisplay); font-size:21px }` (945) → `font-family:var(--ftext);
  font-size:19px` (match `.gt-title`, line 409).
- `.prescription .rx-body` bottom spacing → match `.guide-body{ padding:0 0 40px }` (413).
- **NEW grace-note rule** (the approved B touch): `.prescription.open{ background:linear-gradient(180deg,
  rgba(200,162,74,.035), transparent); }` — a faint ground only while expanded.
- Mobile (975-979): the `.prescription{ padding:22px 16px }` override is now moot (base padding is 0) — remove
  it (or repoint to the toggle) so the collapsed mobile rhythm matches `.guide`.
- The eyebrow ("Not sure what to play?") + gold chevron keep it inviting without a box.

### L2 — Fix two undefined-token bugs (each breaks a real feature)
- **`--bg`** at `.cmp-table th[scope="row"]` (line 322) → `background:var(--ink-2)` (the frozen compare column is
  transparent today → body cells scroll under it and overlap).
- **`.section-sub`** → rename the class on the Counterpoise intro `<p>` (markup line 1225) to **`sub`** (it's
  inside `<header class="section-head">`, so it picks up the defined `.section-head .sub` — bone-dim, 16px,
  60ch cap). Today it has no rule and runs full-width/over-bright.

### L3 — One section-framing system
- **The Still** (347-350): normalize the drifted bottom padding `52px 0 46px` → `52px 0 30px` so its framing is
  identical to `.section-frame` (same margin/border already). (Minimal-risk dedup — no markup restructure.)
- **The Counterpoise** (header 1223): add a `<span class="eyebrow">…</span>` (e.g. "Weigh two essences") before
  its `<h2>`, so the eyebrow → h2 → sub grammar is uniform across Assay / Counterpoise / Cellar / Still
  (`.section-head .eyebrow` rule already exists, line 557).

### L4 — Radius scale (kept tight; eyebrow normalization explicitly out of scope)
- Standardize on **two radii** — `2px` controls, `3px` surfaces. Snap the dialog/modal panel (line 473)
  `border-radius:4px` → `3px`; the Prescription's 4px is already removed by L1. After this, no `4px` remains.
- **Out of scope (YAGNI):** the eyebrow size/letter-spacing variants (`.panel-eyebrow .22em`, the `.16em`/`.12em`
  one-offs) — they're individually defensible and forcing a single scale is churn for little gain.

### L5 — Contrast to AA
`--muted:#9b8c6f` (line 53) is ≈4.0:1 on the `--ink` ground (#14100b) — under AA 4.5:1 for the 9–12px mono text
it's used for (`.cta-note`, `.ledger-foot`, `.panel-note`, `.section-caveat`, tier legend, ~15 sites). Lift to
≈`#aa9a7d` (≈4.6:1 on `--ink`) and correct the token comment to the real ratio + ground. (The print `@media`
override of `--muted` at line 982 is unrelated — leave it.)

## FEEL

### F1 — Hero: one clear primary action (decided)
Hero CTA row markup, lines 1038-1050. The visible clutter is one gold button + four visible links
(two more, `#heroGuide`/`#exportMine`, are `hidden` by default):
- **Primary:** relabel the `#heroDecant` button "Decant the essence" (line 1041) → **"Decant this build → your
  game"** (keep the `id`; it's reassigned every render at 2410). The loadable/template nuance stays in the
  existing `.cta-note` (1050).
- **Remove** the two id-less, handler-less links — "see the analysis ↓" (`#assay`, 1047) and "access all the
  data ↓" (`#archive`, 1048). The footer already links both, so nothing is stranded.
- **Keep two secondary links:** `#rxHeroLink` "match me to a build ↓" (1046, has a smooth-scroll handler) and
  `#guideHeroLink` (1045), relabelled "new? how Decant works ↓" → **"new? how it works ↓"**.
- **Leave `#heroGuide` and `#exportMine` in place, ids intact** — both are `hidden` by default and toggled by
  `renderHero`/`SELF_EXPORT_ENABLED`; `#heroGuide` appears contextually next to the CTA when a guide URL exists
  (a single contextual link, not part of the clutter). No relocation needed.

## VOICE

### V1 — Benefit-first hero subhead (honesty-tightened)
Rewrite the `essenceSub` template (JS, line 2406; currently "The clearest signal in {league} right now. {x}% of
the tracked ladder is running it — about ~{n} characters (share × ladder size).") to lead with the verdict + the
measured fact, **without** the "safest" superlative or an unconditional "loadable" promise:
> **"The most-played build in {league} right now — {x}% of the live ladder is on it (~{n} characters). When
> you're not sure what to play, this is the safe default: start here and Decant it in one click."**
- "safe default" = popularity-framed (it's what the most players picked), not a power/survival claim.
- No "loadable" promise in the subhead — the `.cta-note` (1050) already carries the honest loadable-vs-template
  nuance for the manifest-gated picks.

### V2 — Fix the overclaim (popularity ≠ power)
The Still, line 1237: "…boil the cloud of variation down to **the consensus that's actually winning**." →
"…down to **the consensus that's actually being played**." (Removes the unmeasurable victory language; "being
played" states popularity as fact. Single in-file instance; no README echo.)

### V3 — Fix the internal contradiction (same line 1237)
"**No editorial guesswork** — just what the ladder is doing, distilled and decanted." → **"No guesswork about the
rankings — they're straight from the ladder. The playstyle notes are ours, and we say so."** (Distinguishes the
ladder-derived rankings from the editorial `ASC_TAGS` flavor.)

### V4 — De-hedge the quiz to one explicit caveat
The Prescription stacks three hedges. Keep the matching honest with exactly one caveat that **preserves
popularity ≠ power**:
- Intro `.sub` (line 1106): trim the redundant "ranked, each with an honest reason" → "ranked, with the reason
  each one matched."
- Footnote `.rx-note` (line 1117): rewrite to one reassuring-but-honest caveat that keeps the popularity-not-power
  point **explicit** (it is load-bearing): **"Matched to how you want to play and ranked by ladder share
  (popularity, not a strength score) — every result is a real pick that links to the honest ledger row and
  Decant."**
- Leave the per-card "matched on …" reasons (line 3066) and the scorer's "editorial guidance, never a power
  ranking" comment (2972) as-is, so the matching still reads as editorial, not objective ranking.

### V5 — De-jargon the newcomer touchpoints
- "**representative public-ladder character**" — both instances (`.cta-note` line 1050; guide `.lede` line 1069)
  → **"a real public-ladder player running that build (credited in the file)"** (drop "representative" *and*
  avoid "top" — "top-ladder" edges toward a quality claim; grep the phrase to catch any third instance).
- Quiz labels: "**Glass cannon**" (line 2989) → "all-out damage (fragile)"; "**Fast, zoomy clear**" (line 2984)
  → "fast — blast through packs". (Keep "Keep me alive", "Slow & steady, tanky", "Balanced".)

### V6 — Forward-leaning empty/template states
- Template-save toast (JS, line 1700): "Saved {asc} as a labelled meta template (.txt) — we haven't reconstructed
  a loadable build for this pick yet. Pair it with a community guide." → **"Saved a {asc} starter (.txt) — its
  ladder share, playstyle, and a guide link. No loadable build for this exact pick yet, so follow the linked
  guide."** (Leads with what they got; **keeps "(.txt)" and "No loadable build … yet"** so it's never mistaken
  for a loadable file.)
- Empty hero (JS, lines 2392-2393): non-curated `essenceName` "No ranked data" → **"No live ladder data yet"**;
  the `essenceSub` fallback (2393) → **"poe.ninja doesn't publish a build breakdown for {league}. Pick the live
  challenge league from the dropdown above for the full ranked meta."** (next action via the dropdown — no
  `{default}`-name accessor needed). The curated branch ("Classic archetypes") is unchanged.

## Testing / verification (browser preview — the project pattern; no JS unit harness)

- **L1:** collapsed/expanded Prescription aligns to the same left spine + divider as `.guide`; no box/gradient
  except the faint expanded-only ground; title matches the guide's; toggle still opens/closes (id-driven).
- **L2:** the Counterpoise frozen first column stays opaque on horizontal scroll (no overlap); its intro `<p>` is
  bone-dim, 16px, 60ch-capped like sibling intros.
- **L3/L4:** all four major sections show eyebrow → h2 → sub; The Still's top/bottom rhythm matches
  `.section-frame`; no `4px` radius remains (grep + spot-check the dialog).
- **L5:** spot-check the contrast ratio of `.panel-note`/`.cta-note` on `--ink` clears 4.5:1.
- **F1/V1-V6:** hero shows one primary CTA + two secondary links; the named strings ("actually winning", "No
  editorial guesswork", "Glass cannon", "representative public-ladder character", "No ranked data", the template
  toast, "safest", any "loadable" subhead promise) are gone/reworded; the quiz shows one caveat that still says
  "popularity, not a strength score". 0 console errors at each step; responsive check at mobile width.

## Rollout

Pure front-end; deploys with the next `index.html` commit. No data dependency, no CI regen. Stacked on
`feature/earned-confidence`; at finish, PR with base `feature/earned-confidence` (②-only diff), retarget to
`main` once ① merges.

## Exact current anchors (verified — for the plan's find/replace)

CSS: `--muted` :53 · dialog `border-radius:4px` :473 · `.cmp-table th[scope=row] … var(--bg)` :322 · `.still`
:347-350 · `.guide`/`.guide-toggle`/`.gt-title`/`.guide-body` :403-413 · `.section-frame` :555 ·
`.section-head .sub` :559 / `.eyebrow` :557 · `.prescription*` :942-948, mobile :975-979.
Markup: hero `.cta-row` :1038-1050 (heroDecant :1041, guideHeroLink :1045, rxHeroLink :1046, #assay :1047,
#archive :1048, `.cta-note` :1050) · Prescription intro `.sub` :1106 / footnote `.rx-note` :1117 / eyebrow :1101 ·
Counterpoise header :1223 / `section-sub` :1225 · The Still `<p>` :1237 (both V2 "actually winning" + V3 "No
editorial guesswork") · guide `.lede` "representative…" :1069 · footer nav :1372.
JS: `essenceSub` builder :2405-2406 · empty-hero `essenceName`/`essenceSub` :2392-2393 · template toast :1700 ·
quiz opts :2983-2991 (`Fast, zoomy clear` :2984, `Glass cannon` :2989) · per-card "matched on" :3066 · setRx/
openQuiz :3108-3120 · hero link handlers :2388-2411 / :3121 / :3371-3377.

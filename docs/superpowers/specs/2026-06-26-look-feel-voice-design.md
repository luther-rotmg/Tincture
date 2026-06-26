# Look, Feel & Voice — visual uniformity + confident, honest copy

**Status:** approved design · **Date:** 2026-06-26 · **Type:** front-end sweep (CSS + markup + copy)
**Branch:** `feature/look-feel-voice` (stacked on `feature/earned-confidence` until ① merges)

## Overview

Workstream ② of the post-audit program. A single coherent front-end sweep of `index.html` that makes the
page read as one deliberate, uniform design and gives a newcomer a clear, confident path — while keeping the
project's honesty stance. Three layers:

- **LOOK** — the class questionnaire ("The Prescription") stops sticking out and rejoins the page's vertical
  spine; two undefined-CSS-token bugs that break real features are fixed; the four different section-framing
  systems collapse to one; the radius/spacing scale and text contrast are tightened.
- **FEEL** — the hero gets one clear primary action and a benefit-first headline instead of one button
  drowning in six equal-weight links.
- **VOICE** — the copy asserts the *measured* facts boldly (popularity) and caveats the *unmeasured* once,
  fixing two overclaims, one internal contradiction, the over-hedged quiz, and the worst newcomer jargon.

All changes are in `index.html` (inline CSS, markup, copy), locally verifiable in the browser preview. No
pipeline, data, or `meta-detail.json` changes; no touching `pop`/`rank`/`tier`/the ledger.

## Goals

- The Prescription reads as a peer of the adjacent "guide" collapsible — same spine, same divider, same
  toggle grammar — not a floating promoted card.
- Every section announces itself the same way; no undefined CSS tokens; one radius scale; the smallest text
  clears WCAG AA contrast.
- A first-time visitor sees exactly one primary action that states its outcome, and a headline that says
  what to play and why — in plain language.
- Copy is confident about what the data proves and honest (once) about what it doesn't; no overclaim, no
  self-contradiction.

## Non-goals (YAGNI)

- **No** lower-priority a11y rework beyond the contrast fix (heading-hierarchy promotion, focus-ring
  redesign, 44px tap targets were explicitly deferred).
- **No** new sections, components, or features; **no** changes to the build-view/Decant/Assay/Counterpoise
  *logic* (workstream ① owns the build view; this sweep only restyles/recopies).
- **No** pipeline / `data.json` / `meta-detail.json` / honesty-invariant changes; **no** `pop`/`rank`/`tier`
  edits; the alchemical theme and brand verb "Decant" stay.
- **No** wholesale copy rewrite — only the specific overclaims, the contradiction, the over-hedge, and the
  named jargon touchpoints.

## Honesty guardrails (load-bearing)

- Assert only what the data measures. Popularity is a fact ("X% of the live ladder is on it") — state it with
  full confidence. Power/win-rate is **not** measured — never imply it ("winning", "best", "optimal").
- One honest caveat per concept, placed once — not stacked. The "popularity ≠ power" caveat lives in one
  place, not three.
- Distinguish hard data (ladder-derived rankings) from editorial flavor (the playstyle tags) wherever the
  copy claims objectivity.
- Lead with what the user got + the next action; the caveat is a forward-leaning footnote, never a dead end.

## LOOK

### L1 — The Prescription rejoins the spine (the headline ask)
`.prescription` (CSS ~line 942) is today the only top-level content block that is a bordered, `radius:4px`,
gradient-filled card with `margin:34px 0` and `padding:22px 28px` (content inset ~28px off the column),
plus a Cinzel-21px title override (~945) — five signals that make it read as an inserted ad between the bare
`.guide` collapsible (line 403) above and the controls below. **Make it the twin of the guide:**
- `.prescription`: `margin:0; padding:0; border:none; border-bottom:1px solid var(--hair); border-radius:0;
  background:none;` (drop the box, the gradient, the lone 4px radius, and the floating margins).
- `.prescription .guide-toggle{ padding:22px 0; }` and `.prescription .rx-body{ padding:0 0 40px; }` so the
  content aligns to the column spine like `.guide`.
- `.prescription .gt-title{ font-family:var(--ftext); font-size:19px; }` — match the guide's `.gt-title`
  (drop the Cinzel-21px outlier).
- The eyebrow ("Not sure what to play?") + gold chevron keep it inviting without a box.
- **Grace note (optional, approved):** a faint expanded-only ground —
  `.prescription.open{ background:linear-gradient(180deg, rgba(200,162,74,.035), transparent); }` — signals
  "interactive tool" only after the user opens the quiz, never advertising before.
- Reconcile the mobile rule (`@media (max-width:560px){ .prescription{ padding:22px 16px } }` ~976): the
  card padding no longer applies; align the collapsed mobile rhythm to `.guide`'s.

### L2 — Fix two undefined-token bugs (each breaks a real feature)
- **`--bg`** is used at `.cmp-table th[scope="row"]{ … background:var(--bg) … }` (line 322) but never declared
  → the sticky frozen first column of the Counterpoise compare table renders **transparent**, so body cells
  scroll under it and text overlaps. Fix: `background:var(--ink-2)` (the raised-panel ground every other
  floating element uses).
- **`.section-sub`** is used in the Counterpoise intro markup but has **no CSS rule** → that paragraph drops
  out of the type system (inherits body color/size, runs full column width while sibling intros cap at
  60ch). Fix: rename the class to `.sub` (the established section-intro class), or define `.section-sub` as
  an alias of `.sub`.

### L3 — One section-framing system
Today: `.hero`/`.masthead` use `border-bottom`; `.guide` uses `border-bottom`; `.section-frame` (Assay,
Counterpoise, Cellar) uses `border-top` + `margin:78px 0 0; padding:52px 0 30px`; `.still` (line 347)
**duplicates** `.section-frame`'s values inline (with a drifted `46` bottom pad). Collapse to one:
- Route `.still` through `.section-frame` (remove its duplicated framing values; keep only Still-specific
  rules); normalize the bottom padding to the `.section-frame` value.
- Give **The Counterpoise** a `.section-head` with an eyebrow (it currently jumps straight to `<h2>`), so the
  eyebrow → h2 → sub grammar is uniform across Assay / Counterpoise / Cellar / Still.

### L4 — Radius & spacing scale
Radii in use: 2px (chips/tiers/buttons), 3px (panels/inputs), 4px (the Prescription card — removed in L1),
50% (dots). Standardize on **two**: `2px` for controls, `3px` for surfaces; remove the lone `4px` (gone with
L1) and any stray values. Snap the most divergent card paddings toward a small spacing scale (the panels that
sit adjacent — `.panel` vs `.cross-panel` — share interior rhythm). Collapse the eyebrow size/tracking
variants to two tiers (section 11px/.34em; panel 10px/.2em).

### L5 — Contrast to AA
`--muted:#9b8c6f` (line 53) is ≈4.0:1 on the `--ink` ground — under AA 4.5:1 for the 9–12px mono text it's
used for (`.cta-note`, `.ledger-foot`, `.panel-note`, `.section-caveat`, tier legend, etc.). Lift it to
≈`#aa9a7d` (≈4.6:1 on `--ink`) — a small warm lightening that clears AA without disturbing the palette.
Update the token comment to state the real ratio.

## FEEL

### F1 — Hero: one clear primary action (decided)
The hero CTA row (markup ~1035-1047) has one gold `.decant` button plus six `.ghost-link`s of equal weight
("find a build guide", "export my own character" [hidden], "new? how Decant works", "match me to a build",
"see the analysis", "access all the data"). Refocus:
- **Primary:** the gold Decant button states its outcome — label "Decant this build → your game" with a
  sublabel/`.cta-note` "a real, loadable `.build` in one click". (Keeps the brand verb "Decant".)
- **Secondary:** exactly two `.ghost-link`s — "match me to a build ↓" and "new? how it works ↓".
- **Move out of the hero:** "see the analysis" / "access all the data" (they already anchor from their own
  sections and the footer); "find a build guide" relocates next to the build/headline as the natural
  post-Decant step (it's already a hero element — keep it adjacent to the CTA, not in the equal-weight row).
- `export my own character` stays hidden (dormant `SELF_EXPORT_ENABLED` flag) — unchanged.

## VOICE

### V1 — Benefit-first hero copy
- Headline sub / essence-sub (set in JS, `renderHero`/`essenceSub`): lead with the verdict + the fact, not
  the methodology. e.g. **"The most-played build in {league} right now — {x}% of the live ladder is on it.
  When you're not sure what to play, this is the safest start, and one click drops a real, loadable build
  into your game."** Keep "~{n} characters (share × ladder size)" as a secondary/figure, not the headline
  clause.

### V2 — Fix the overclaims (popularity ≠ power)
- "the consensus **that's actually winning**" (hero/Still/README echo) → "the consensus **that's actually
  being played**" / "what the top of the ladder is **running**." State popularity as fact; never borrow the
  language of victory the source can't measure.
- "**The clearest signal**" → lead with the measured fact ("the most-played build … {x}% of the live
  ladder").

### V3 — Fix the internal contradiction
- The Still's "**No editorial guesswork** — just what the ladder is doing" contradicts the editorial
  `ASC_TAGS` playstyle notes shown on every row. Reword to distinguish them: **"No guesswork about the
  rankings — they're straight from the ladder. The playstyle notes are ours, and we say so."**

### V4 — De-hedge the quiz; one caveat
- The Prescription stacks three hedges (intro "an honest reason", per-card "matched on …", footnote
  "editorial guidance … a starting shortlist, not a power ranking"). Keep **one** reassuring caveat
  (the footnote, reworded), and let the result speak: e.g. footnote → "Matched to how you want to play and
  ranked by what's actually on the ladder — every result is a real, honest pick." Move "popularity, not a
  strength score" to a tooltip/short tag, not a third inline hedge.
- (Result-card "why matched" reasons stay as-is for this sweep — they're driven by the quiz scorer; only the
  surrounding hedge copy changes.)

### V5 — De-jargon the newcomer touchpoints
- Quiz answer labels: "**Glass cannon**" → "all-out damage (fragile)"; "Fast, zoomy clear" → "fast — blast
  through packs". (Plain, benefit-first; keep "Keep me alive".)
- "**representative public-ladder character**" (hero `.cta-note` + guide + build view, 3×) → "a real
  top-ladder player running that build (credited in the file)".
- Pair one alchemical metaphor with a plain outcome where it's the first/only signal: the hero Decant
  `.cta-note` already added in F1 covers "Decant"; leave the deeper theme (Assay/Crucible/Cellar/Still) as
  flavor with their existing plain `.panel-note` subtitles.

### V6 — Forward-leaning empty/template states
- The curated/empty hero ("**No ranked data**") → "No live ladder data for {league} yet — switch to
  **{default league}** above for the full ranked meta." (next action, not a dead end).
- The template-save toast (leads today with "we haven't reconstructed a loadable build for this pick yet")
  → lead with what they got + the path: "Saved a **{asc}** starter — its ladder share, playstyle, and a
  guide link. No loadable build for this exact pick yet, so follow the linked guide." (Same honesty,
  forward-leaning.)

## Testing / verification

No JS unit harness for `index.html`; verify in the browser preview (the project pattern):
- **L1:** the Prescription collapsed/expanded aligns to the same left spine and divider as `.guide`; no box,
  no gradient (except the optional faint expanded ground); title matches the guide's. Visually a matched pair.
- **L2:** the Counterpoise compare table's first column stays opaque on horizontal scroll (no text overlap);
  the Counterpoise intro paragraph is bone-dim, 60ch-capped, matching sibling intros.
- **L3/L4:** all four major sections present an eyebrow → h2 → sub head; no 4px radius remains; The Still's
  top/bottom rhythm matches `.section-frame`.
- **L5:** `--muted` text passes AA (spot-check the contrast ratio of `.panel-note`/`.cta-note` on `--ink`).
- **F1/V1-V6:** the hero shows one primary CTA + two secondary links; the headline/subhead read benefit-first;
  the named strings ("actually winning", "No editorial guesswork", "Glass cannon", "representative
  public-ladder character", "No ranked data", the template toast) are gone/reworded; the quiz shows one
  caveat. 0 console errors at each step; responsive check at mobile width.
- Spot-check that the README's "actually winning" / data-source claims stay consistent with the UI copy
  (update the README echo if it repeats a fixed phrase).

## Rollout

Pure front-end; deploys with the next `index.html` commit. No data dependency, no CI regen. Stacked on
`feature/earned-confidence`; at finish, PR with base `feature/earned-confidence` (so the diff is ②-only) and
retarget to `main` once ① merges.

## Integration points (index.html — line refs approximate, verify by anchor)

- CSS: `--muted` (:53), `.cmp-table th[scope=row]` `--bg` (:322), `.still` (:347), `.guide`/`.guide-toggle`
  (:403-417), `.section-frame` (:555), `.prescription*` (:942-948, mobile :976), radius/eyebrow tokens
  throughout.
- Markup/copy: hero CTA row + `.cta-note` (~1035-1047), The Counterpoise `.section-head`/`.section-sub`
  intro, The Still "No editorial guesswork", the Prescription intro/footnote hedges, quiz answer labels,
  empty-hero "No ranked data", the template-save toast string, the "representative public-ladder character"
  instances.
- JS copy: `renderHero`/`essenceSub` (benefit-first subhead), the template-toast builder, the empty/curated
  hero state.
- `README.md`: the "actually winning" echo, if present, kept consistent.

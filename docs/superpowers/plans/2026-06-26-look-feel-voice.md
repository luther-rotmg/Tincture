# Look, Feel & Voice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A single front-end sweep of `index.html` that makes the page read as one uniform design (the Prescription quiz stops sticking out, two CSS-token bugs fixed, framing/radius/contrast tightened), gives the hero one clear primary action, and rewrites the copy to assert measured facts boldly and caveat the unmeasured once.

**Architecture:** All edits are in the single inline-CSS+JS `index.html`. Each task is a small, exact find/replace (CSS rule, markup, or a JS template string) with a known before/after. There is **no JS unit harness** for `index.html` — the verification gate is the browser preview (the project's established pattern), done by the controller during subagent-driven execution.

**Tech Stack:** Vanilla inline CSS/HTML/JS in one file; browser preview (`.claude/launch.json` server "tincture", port 8099) for verification.

## Global Constraints

- **Honesty (load-bearing):** assert only the measured (popularity) — never imply power/win-rate/survival. **No "loadable" promise in the hero subhead** (the top pick may fall back to the `.txt` template). **No "safest"/"winning"/"best"/"optimal".** The quiz footnote must keep **"popularity, not a strength score"** explicit.
- **Scope:** `index.html` only. No pipeline/`data.json`/`meta-detail.json` changes; no `pop`/`rank`/`tier`/ledger edits; no logic changes to Decant/Assay/Counterpoise/build-view (restyle/recopy only). Keep the brand verb "Decant" and the alchemical theme.
- **Preserve these element ids/classes exactly** (live JS depends on them): `#prescription`, `#rxToggle`, `.open` (Prescription toggle); `#heroDecant`, `#heroGuide`, `#exportMine`, `#guideHeroLink`, `#rxHeroLink`, `#essenceSub`, `#essenceName` (hero render). Restyle/relabel/move freely, but never drop these ids.
- **Commit `index.html` only** each task (`git add index.html`) — the working tree may carry an uncommitted data regen from ①.
- **Branch:** `feature/look-feel-voice` (stacked on `feature/earned-confidence`). Commit after every task.
- **Verified anchors** (current line numbers; match by the quoted text, not the number): see each task.

---

### Task 1: L1 — De-box The Prescription (twin of the guide)

**Files:** Modify `index.html` (CSS ~942-948, mobile ~975-979)

- [ ] **Step 1: De-box the base `.prescription` rule**

Find (lines 942-943):
```css
  .prescription{ margin:34px 0; padding:22px 28px; border:1px solid var(--hair); border-radius:4px;
    background:linear-gradient(180deg, rgba(200,162,74,.04), rgba(0,0,0,.18)); }
```
Replace with:
```css
  .prescription{ margin:0; border-bottom:1px solid var(--hair); }
```

- [ ] **Step 2: Align the toggle + body + title to the guide**

Find (line 944): `  .prescription .guide-toggle{ padding:0; }            /* the panel already pads; collapse like the guide */`
Replace: `  .prescription .guide-toggle{ padding:22px 0; }        /* align to the column spine like .guide */`

Find (line 945): `  .prescription .gt-title{ font-family:var(--fdisplay); font-size:21px; }`
Replace: `  .prescription .gt-title{ font-family:var(--ftext); font-size:19px; }`

Find (line 946): `  .prescription .rx-body{ display:none; margin-top:20px; }`
Replace: `  .prescription .rx-body{ display:none; padding:0 0 40px; }`

- [ ] **Step 3: Add the open-only grace-note ground (new rule)**

After the `.prescription.open .gt-chevron{ transform:rotate(180deg); }` line (948), add:
```css
  .prescription.open{ background:linear-gradient(180deg, rgba(200,162,74,.035), transparent); }
```

- [ ] **Step 4: Drop the now-moot mobile padding override**

Find (within `@media (max-width:560px){` ~975-979): `    .prescription{ padding:22px 16px; }`
Delete that line (base padding is now 0; the toggle owns its padding, matching the guide on mobile).

- [ ] **Step 5: Verify in preview**

Reload `http://localhost:8099`. Confirm: the Prescription (collapsed) sits flush with the same left edge and hairline divider as the "guide" section above it — no box, no border-radius, no always-on gradient; the title font/size matches the guide's title. Expand it (click the toggle): it still opens (toggle works), and a faint gold top-tint appears only while open. Resize to mobile width — still aligned, no horizontal inset. 0 console errors.

- [ ] **Step 6: Commit**
```bash
git add index.html
git commit -m "feat(ui): de-box The Prescription to twin the guide (+ open-only grace ground)"
```

---

### Task 2: L2 — Fix two undefined-token bugs

**Files:** Modify `index.html` (CSS line 322; markup line 1225)

- [ ] **Step 1: Fix the transparent compare-table frozen column (`--bg`)**

Find (line 322): `position:sticky; left:0; background:var(--bg); z-index:1; }`
Replace `var(--bg)` with `var(--ink-2)` so the line reads `... position:sticky; left:0; background:var(--ink-2); z-index:1; }`. (`--bg` is never declared; `--ink-2` is the raised-panel ground.)

- [ ] **Step 2: Fix the Counterpoise intro escaping the type system (`.section-sub`)**

Find (line 1225): `      <p class="section-sub">Weigh two or three ascendancies against each other — vitals, defences, and the build behind each. Higher isn't automatically better; survivability and damage trade off.</p>`
Replace the class only: `<p class="section-sub">` → `<p class="sub">`. (The `<p>` is inside `<header class="section-head">`, so it now matches the defined `.section-head .sub` — bone-dim, 16px, 60ch cap.)

- [ ] **Step 3: Verify in preview**

Reload. Open The Counterpoise, pick two ascendancies, scroll the compare table horizontally — the frozen first column (row labels) stays **opaque** (dark), no text overlap. The Counterpoise intro paragraph is now bone-dim, smaller, and width-capped like the Assay/Cellar intros (not full-width/over-bright). 0 console errors.

- [ ] **Step 4: Commit**
```bash
git add index.html
git commit -m "fix(ui): define compare-column bg (--bg→--ink-2) and Counterpoise intro class (.section-sub→.sub)"
```

---

### Task 3: L3 + L4 — One framing system + radius scale

**Files:** Modify `index.html` (CSS line 348, line 473; markup ~1223)

- [ ] **Step 1: Normalize The Still's drifted bottom padding**

Find (line 348): `    margin:78px 0 0; padding:52px 0 46px;`
Replace: `    margin:78px 0 0; padding:52px 0 30px;` (now identical framing to `.section-frame`, line 555).

- [ ] **Step 2: Give The Counterpoise a section eyebrow**

Find (the Counterpoise header, ~1223-1224):
```html
    <header class="section-head">
      <h2>The Counterpoise</h2>
```
Replace with:
```html
    <header class="section-head">
      <span class="eyebrow">Weigh two essences</span>
      <h2>The Counterpoise</h2>
```
(The `.section-head .eyebrow` rule already exists at line 557; this matches the Assay/Cellar header grammar.)

- [ ] **Step 3: Snap the lone remaining 4px radius to the surface scale**

Find the dialog/modal panel rule (~line 473 — the rule with `max-width:min(92vw,420px); width:100%;`): `    border-radius:4px; padding:24px 26px; max-width:min(92vw,420px); width:100%;`
Replace `border-radius:4px` → `border-radius:3px`. (After this and Task 1, no `4px` radius remains — controls are 2px, surfaces 3px.)

- [ ] **Step 4: Verify in preview**

Reload. The Still's top/bottom rhythm matches the other framed sections (Assay/Cellar). The Counterpoise now leads with a small gold "WEIGH TWO ESSENCES" eyebrow above its h2, matching the other sections. Open the dialog that uses the 4px rule (the character-picker/folder dialog if reachable) — its corners are slightly tighter (3px). Grep confirms no `border-radius:4px` remains. 0 console errors.

- [ ] **Step 5: Commit**
```bash
git add index.html
git commit -m "feat(ui): unify section framing (Still padding, Counterpoise eyebrow) + drop the lone 4px radius"
```

---

### Task 4: L5 — Lift `--muted` to WCAG AA contrast

**Files:** Modify `index.html` (CSS line 53)

- [ ] **Step 1: Lighten the token**

Find (line 53): `    --muted:#9b8c6f;        /* low-emphasis (≥4.5:1 on raised panels for AA) */`
Replace: `    --muted:#aa9a7d;        /* low-emphasis (~4.6:1 on the --ink ground for AA) */`

- [ ] **Step 2: Verify in preview**

Reload. The smallest mono text (`.cta-note`, `.panel-note`, `.ledger-foot`, tier legend, section caveats) is now a touch lighter/warmer and more legible against the dark ground, without disturbing the palette. Spot-check with the preview inspector that a `.panel-note` (or `.cta-note`) color against the page `--ink` background computes to ≥ 4.5:1. (The print `@media` override of `--muted` at line ~982 is untouched.) 0 console errors.

- [ ] **Step 3: Commit**
```bash
git add index.html
git commit -m "fix(a11y): lift --muted to ~#aa9a7d for AA contrast on the page ground"
```

---

### Task 5: F1 — Hero: one clear primary action

**Files:** Modify `index.html` (markup 1041, 1045, delete 1047-1048)

- [ ] **Step 1: Relabel the primary CTA to state its outcome**

Find (line 1041, the text inside the `#heroDecant` button): `            Decant the essence`
Replace: `            Decant this build → your game`
(Do not touch the `<button class="decant lg" id="heroDecant">` open tag or its SVG — `renderHero` reassigns this button by id every render.)

- [ ] **Step 2: Remove the two equal-weight nav shortcuts (footer already carries them)**

Delete these two lines (1047-1048):
```html
          <a href="#assay" class="ghost-link">see the analysis ↓</a>
          <a href="#archive" class="ghost-link">access all the data ↓</a>
```
(Both are id-less with no JS handler; the footer at line ~1372 links `#assay`/`#archive`, so nothing is stranded.)

- [ ] **Step 3: Plain-language the surviving "how it works" link**

Find (line 1045): `          <a href="#guide" class="ghost-link" id="guideHeroLink">new? how Decant works ↓</a>`
Replace the link text only: `new? how Decant works ↓` → `new? how it works ↓` (keep `href="#guide"` and `id="guideHeroLink"`).

(Leave `#rxHeroLink` "match me to a build ↓" at 1046, and the `hidden` `#heroGuide` (1043) / `#exportMine` (1044) exactly as they are — ids intact.)

- [ ] **Step 4: Verify in preview**

Reload. The hero now shows one gold primary button reading **"Decant this build → your game"**, then just two visible secondary links — "match me to a build ↓" and "new? how it works ↓" — no "see the analysis"/"access all the data" clutter. Both secondary links still smooth-scroll to their sections (click each). The Decant button still works (it Decants the headline pick). 0 console errors.

- [ ] **Step 5: Commit**
```bash
git add index.html
git commit -m "feat(ui): hero gets one clear primary action + two secondary links"
```

---

### Task 6: V1 — Benefit-first hero subhead (honesty-tightened)

**Files:** Modify `index.html` (JS, the `essenceSub` ranked-branch template ~2405-2406)

**Interfaces:** Consumes `L.name`, `top.pop`, `top.n` (already in scope in `renderHero`'s ranked branch); writes `#essenceSub`. No "loadable" promise, no "safest".

- [ ] **Step 1: Rewrite the subhead template string**

Find (line 2406):
```js
    `The clearest signal in <b>${esc(L.name)}</b> right now. <span class="figure">${top.pop.toFixed(1)}%</span> of the tracked ladder is running it — about <span class="figure">~${fmt(top.n)}</span> characters (share × ladder size).`;
```
Replace with:
```js
    `The most-played build in <b>${esc(L.name)}</b> right now — <span class="figure">${top.pop.toFixed(1)}%</span> of the live ladder is on it (about <span class="figure">~${fmt(top.n)}</span> characters). When you're not sure what to play, this is the safe default: start here and Decant it in one click.`;
```

- [ ] **Step 2: Verify in preview**

Reload. The hero subhead now leads with the verdict + the measured fact ("The most-played build in {league} right now — {x}% of the live ladder is on it"), keeps the "~{n} characters" figure as a parenthetical, frames it as "the safe default" (popularity, not "safest"), and makes **no** "loadable build" claim (that nuance stays in the `.cta-note` below). 0 console errors.

- [ ] **Step 3: Commit**
```bash
git add index.html
git commit -m "copy(ui): benefit-first hero subhead (most-played fact; no loadable/safest overclaim)"
```

---

### Task 7: V2 + V3 — The Still: fix the overclaim and the contradiction

**Files:** Modify `index.html` (markup, the Still `<p>` at line 1237)

- [ ] **Step 1: V2 — "actually winning" → "actually being played"**

In line 1237, find: `down to the consensus that's actually winning.`
Replace: `down to the consensus that's actually being played.`

- [ ] **Step 2: V3 — fix the "No editorial guesswork" contradiction**

In the same line 1237, find: `No editorial guesswork — just what the ladder is doing, distilled and decanted.`
Replace: `No guesswork about the rankings — they're straight from the ladder. The playstyle notes are ours, and we say so.`

- [ ] **Step 3: Verify in preview**

Reload. Scroll to The Still. Its paragraph now reads "…down to the consensus that's actually **being played**…" and ends "**No guesswork about the rankings — they're straight from the ladder. The playstyle notes are ours, and we say so.**" — no "winning", no self-contradiction with the editorial playstyle tags. 0 console errors.

- [ ] **Step 4: Commit**
```bash
git add index.html
git commit -m "copy(ui): The Still — 'being played' not 'winning'; own the editorial playstyle notes"
```

---

### Task 8: V4 — De-hedge the quiz to one explicit caveat

**Files:** Modify `index.html` (markup, intro `.sub` 1106; footnote `.rx-note` 1117)

- [ ] **Step 1: Trim the intro hedge**

Find (line 1106): `      <p class="sub">Answer a few questions and Tincture matches you to ascendancies that fit — ranked, each with an honest reason. Your answers live only in the link, so the result is shareable.</p>`
Replace the middle clause: `ranked, each with an honest reason` → `ranked, with the reason each one matched`. (Full line becomes: "…matches you to ascendancies that fit — ranked, with the reason each one matched. Your answers live only in the link, so the result is shareable.")

- [ ] **Step 2: Rewrite the footnote (keep popularity≠power explicit)**

Find (line 1117): `      <p class="rx-note">Matching is editorial guidance — from the playstyle tags plus the meta's weapons and median EHP/DPS — a starting shortlist, not a power ranking. Every result links to the honest ledger row and Decant.</p>`
Replace with: `      <p class="rx-note">Matched to how you want to play and ranked by ladder share (popularity, not a strength score) — every result is a real pick that links to the honest ledger row and Decant.</p>`

- [ ] **Step 3: Verify in preview**

Reload. Open The Prescription. The intro no longer says "each with an honest reason"; the footnote is one reassuring line that still states **"popularity, not a strength score"** explicitly (the load-bearing caveat survives, once). The per-card "matched on …" reasons are unchanged when you run the quiz. 0 console errors.

- [ ] **Step 4: Commit**
```bash
git add index.html
git commit -m "copy(ui): quiz — one honest caveat, popularity-not-power kept explicit"
```

---

### Task 9: V5 — De-jargon the newcomer touchpoints

**Files:** Modify `index.html` (markup 1050, 1069; JS quiz opts 2984, 2989)

- [ ] **Step 1: "representative public-ladder character" → plain (both instances)**

In line 1050 (`.cta-note`), find: `reconstructed from a representative public-ladder character (credited in the file)`
Replace: `reconstructed from a real public-ladder player running that build (credited in the file)`

In line 1069 (guide `.lede`), find: `reconstructed from a representative public-ladder character (passives, gems and items, with the source character credited in the file)`
Replace: `reconstructed from a real public-ladder player running that build (passives, gems and items, credited in the file)`

(Then grep `representative public-ladder` to confirm no third instance remains; if one exists, apply the same replacement.)

- [ ] **Step 2: Plain-language two quiz labels**

Find (line 2984): `    { k:'fast',  label:'Fast, zoomy clear' },`
Replace: `    { k:'fast',  label:'fast — blast through packs' },`

Find (line 2989): `    { k:'glass', label:'Glass cannon' },`
Replace: `    { k:'glass', label:'all-out damage (fragile)' },`

(Leave "Keep me alive", "Slow & steady, tanky", "Balanced".)

- [ ] **Step 3: Verify in preview**

Reload. The hero `.cta-note` and the "New here?" guide now say "a real public-ladder player running that build" (no "representative"/"top"). Open The Prescription; the pace/risk questions show "fast — blast through packs" and "all-out damage (fragile)" instead of "Fast, zoomy clear"/"Glass cannon". 0 console errors.

- [ ] **Step 4: Commit**
```bash
git add index.html
git commit -m "copy(ui): de-jargon source attribution + quiz labels for newcomers"
```

---

### Task 10: V6 — Forward-leaning empty/template states

**Files:** Modify `index.html` (JS: template toast 1700; empty hero 2392-2393)

- [ ] **Step 1: Lead the template-save toast with what they got**

Find (line 1700):
```js
  toast(`Saved <b>${esc(b.asc)}</b> as a labelled meta template (.txt) — we haven't reconstructed a loadable build for this pick yet. Pair it with a community guide.`, "ok", 7000);
```
Replace the string with:
```js
  toast(`Saved a <b>${esc(b.asc)}</b> starter (.txt) — its ladder share, playstyle, and a guide link. No loadable build for this exact pick yet, so follow the linked guide.`, "ok", 7000);
```
(Keeps "(.txt)" and "No loadable build … yet" so it's never mistaken for a loadable file. Do not alter the `saveBlob(...)` call on the line above.)

- [ ] **Step 2: Forward-leaning empty hero (non-curated)**

Find (line 2392): `    $("#essenceName").innerHTML = \`<span class="asc">${curated ? "Classic archetypes" : "No ranked data"}</span>\`;`
Replace `"No ranked data"` → `"No live ladder data yet"` (leave the `curated ? "Classic archetypes" :` branch).

Find (line 2393): `    $("#essenceSub").innerHTML = esc(L.note) || \`poe.ninja doesn't publish a build breakdown for ${esc(L.name)}.\`;`
Replace with: `    $("#essenceSub").innerHTML = esc(L.note) || \`poe.ninja doesn't publish a build breakdown for ${esc(L.name)}. Pick the live challenge league from the dropdown above for the full ranked meta.\`;`

- [ ] **Step 3: Verify in preview**

Reload. Switch the league dropdown to a non-curated league with no breakdown (e.g. an SSF/HC mode that returns no ranked data, if available) — the hero headline reads "No live ladder data yet" and the subhead points to the dropdown ("Pick the live challenge league from the dropdown above…"), not a dead "No ranked data". To check the toast: Decant a pick that has no reconstructed build (a template fallback) — the toast leads "Saved a {asc} starter (.txt) — …" and still says "No loadable build for this exact pick yet". 0 console errors.

- [ ] **Step 4: Commit**
```bash
git add index.html
git commit -m "copy(ui): forward-leaning empty-hero + template-save states (next action, still honest)"
```

---

## Self-Review

**Spec coverage** (each spec section → task): L1 → T1; L2 → T2; L3 → T3 (Still + Counterpoise eyebrow); L4 → T3 (dialog radius; eyebrow normalization explicitly out of scope per spec); L5 → T4; F1 → T5; V1 → T6; V2+V3 → T7; V4 → T8; V5 → T9; V6 → T10. All spec changes mapped.

**Placeholder scan:** none — every step has the exact old string and the exact new string, plus a concrete preview check with expected result.

**Consistency / id-preservation:** the ids the Global Constraints require kept (`#heroDecant`, `#guideHeroLink`, `#rxHeroLink`, `#heroGuide`, `#exportMine`, `#essenceSub`, `#essenceName`, `#prescription`, `#rxToggle`) are only relabeled/moved, never dropped (verified against the JS handlers at 2388-2411, 3121, 3371-3377). The honesty constraints (no "loadable"/"safest"/"winning" overclaim; "popularity, not a strength score" retained) are satisfied by T6 (subhead), T7 (Still), T8 (footnote keeps it explicit), T10 (toast keeps "(.txt)"/"No loadable build yet").

**Note on execution:** front-end tasks have no unit test; the gate is the controller's browser-preview check after each commit (subagent edits + commits `index.html` only; controller reloads :8099, runs the task's verify step, checks console). The honesty-sensitive copy tasks (T6, T7, T8, T10) each get their own review so the wording can be rejected independently.

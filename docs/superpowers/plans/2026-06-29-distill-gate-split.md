# CI Gate Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop a curation-coverage gap from freezing the hourly meta refresh — keep output-integrity tests as a hard gate on `distill.yml`, make the one live-data curation test non-blocking there (warn via a GitHub annotation), and keep it a hard gate on `test.yml`.

**Architecture:** A single env-var (`TINCTURE_DISTILL_GATE=1`) flips the one curation-coverage test to `skipTest` when `distill.yml` runs the suite as its commit gate; everywhere else (local, `test.yml`, PRs) it runs and hard-fails. `distill.yml` gains a non-blocking step that emits `::warning::` annotations for untriaged ascendancies, reusing the pipeline's pure `untriaged_*` functions.

**Tech Stack:** Python stdlib `unittest`; GitHub Actions YAML (bash `run:` on `ubuntu-latest`).

## Global Constraints

- Stdlib-only Python; no new dependencies.
- **Output-integrity invariants stay HARD gates in `distill.yml`** (schema, no inflated totals, no fabricated builds, curated-carries-no-stats, apportionment, etc.) — this change must not alter any of them.
- The env var name is exactly `TINCTURE_DISTILL_GATE` and the skip trigger is the string value `"1"`.
- The annotation step must be **non-blocking** (cannot fail the hourly job): `continue-on-error: true` + a defensive try/except in the snippet.
- Do not change `untriaged_guides`/`untriaged_leveling`/`guides_schema_errors`/`warn_missing_guides` or any `guides.json` data.
- Never stage `economy.json`, `docs/clip/*`, or `docs/shots/*`.
- The dev machine is Windows PowerShell (env-var prefix syntax differs from CI bash — see each Run command).

## File Structure

- `scripts/test_distill.py` — add one `@unittest.skipIf` decorator on `test_shipped_guides_json_valid_and_complete`. Nothing else changes.
- `.github/workflows/distill.yml` — set `env: TINCTURE_DISTILL_GATE: "1"` on the validate step; insert a non-blocking "Flag untriaged ascendancies" step before "Commit refreshed data".
- `.github/workflows/test.yml` — add `guides.json` to the `push.paths` trigger list.

---

### Task 1: Env-skip the curation-coverage test in the distill gate

**Files:**
- Modify: `scripts/test_distill.py:532` (decorate `test_shipped_guides_json_valid_and_complete`)

**Interfaces:**
- Consumes: `os` (imported at test_distill.py:15), `unittest` (imported at :17).
- Produces: the test is skipped iff `os.environ.get("TINCTURE_DISTILL_GATE") == "1"`; runs otherwise. No signature/behavior change to the test body or any other test.

- [ ] **Step 1: Add the decorator.** In `scripts/test_distill.py`, immediately above the `def test_shipped_guides_json_valid_and_complete(self):` line (currently line 532), insert the decorator so the method reads:

```python
    @unittest.skipIf(
        os.environ.get("TINCTURE_DISTILL_GATE") == "1",
        "curation coverage is enforced in test.yml (the code/data gate), not the hourly distill "
        "gate — the meta must keep refreshing even if a newly-live ascendancy isn't triaged yet",
    )
    def test_shipped_guides_json_valid_and_complete(self):
        # the committed guides.json must be well-formed AND cover every live ascendancy
        # (each in guides or unguided) — an untriaged new ascendancy fails CI, the reminder bite.
        gpath = os.path.join(ROOT, "guides.json")
```

(The method body is unchanged — only the two-line decorator is added above the existing `def`.)

- [ ] **Step 2: Verify the full suite still runs the test (test.yml mode).**

Run (PowerShell): `python scripts/test_distill.py 2>&1 | Select-Object -Last 3`
Expected: ends with `OK` and `Ran 50 tests` (the curation test RUNS — not skipped). No `skipped` markers.

- [ ] **Step 3: Verify the distill gate skips exactly that one test.**

Run (PowerShell): `$env:TINCTURE_DISTILL_GATE='1'; python scripts/test_distill.py -v 2>&1 | Select-String 'test_shipped_guides_json_valid_and_complete|skipped|^OK|^Ran'; Remove-Item Env:TINCTURE_DISTILL_GATE`
Expected: `test_shipped_guides_json_valid_and_complete ... skipped 'curation coverage is enforced...'`, and the final line is `OK (skipped=1)`. Every other test still ran (the `Ran N tests` count is unchanged; exactly 1 skipped).

- [ ] **Step 4: Commit.**

```bash
git add scripts/test_distill.py
git commit -m "test: skip the live-data curation-coverage test under TINCTURE_DISTILL_GATE (distill gate)"
```

---

### Task 2: `distill.yml` — set the env on the gate + add the non-blocking annotation step

**Files:**
- Modify: `.github/workflows/distill.yml` (the "Validate the distilled data" step + a new step before "Commit refreshed data")

**Interfaces:**
- Consumes: the env var `TINCTURE_DISTILL_GATE` (Task 1); the pure functions `distill.untriaged_guides(payload, doc)` / `distill.untriaged_leveling(payload, doc)` (both already tolerant of bad input, returning sorted slug lists).
- Produces: a distill job whose commit gate enforces output-integrity only, plus a non-blocking annotation surfacing untriaged ascendancies.

- [ ] **Step 1: Set the env on the validate step.** In `.github/workflows/distill.yml`, replace the existing validate step:

```yaml
      # Gate the commit on the honesty invariants: if the freshly-written data.json is
      # malformed or inflated, this fails the job and the commit step never runs, so the
      # live site keeps the last good data.json. Fail-safe by construction.
      - name: Validate the distilled data
        run: python scripts/test_distill.py
```

with this (adds the env so the curation-coverage test is skipped here — that lock lives in test.yml — while every output-integrity test still hard-gates the commit):

```yaml
      # Gate the commit on the OUTPUT-INTEGRITY invariants only: if the freshly-written
      # data.json is malformed/inflated/fabricated, this fails the job and the commit step
      # never runs, so the live site keeps the last good data.json. The curation-coverage
      # lock (every live ascendancy has a guide) is enforced in test.yml, NOT here — a
      # missing guide link must never freeze the meta refresh (the front end falls back to a
      # neutral search, and the next step warns).
      - name: Validate the distilled data (output-integrity gate)
        run: python scripts/test_distill.py
        env:
          TINCTURE_DISTILL_GATE: "1"
```

- [ ] **Step 2: Insert the non-blocking annotation step.** Immediately after the validate step from Step 1 and **before** the `- name: Commit refreshed data` step, insert:

```yaml
      # A REMINDER, not a gate. The meta keeps refreshing even when curation lags; the hard
      # coverage-lock lives in test.yml. Emits ::warning:: annotations so an untriaged
      # ascendancy shows on the run summary instead of being buried in the distill step's log.
      # Defensive + continue-on-error so it can never fail the hourly job.
      - name: Flag untriaged ascendancies (non-blocking)
        continue-on-error: true
        run: |
          python - <<'PY'
          import json, sys
          sys.path.insert(0, "scripts")
          import distill
          try:
              doc = json.load(open("guides.json", encoding="utf-8"))
              payload = json.load(open("data.json", encoding="utf-8"))
          except Exception as e:
              print(f"::notice::skipped guide-coverage check: {e}")
              sys.exit(0)
          for slug in distill.untriaged_guides(payload, doc):
              print(f"::warning title=Untriaged build guide::'{slug}' is live but has no build "
                    f"guide — add it to guides.json guides or unguided")
          for slug in distill.untriaged_leveling(payload, doc):
              print(f"::warning title=Untriaged leveling guide::'{slug}' is live but has no "
                    f"leveling guide — add it to guides.json leveling or levelingUnguided")
          PY
```

- [ ] **Step 3: Verify the YAML parses.**

Run (PowerShell): `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/distill.yml',encoding='utf-8')); print('distill.yml OK')"`
Expected: `distill.yml OK`. If PyYAML is not installed (`ModuleNotFoundError`), skip this and rely on the post-push Actions run; do NOT `pip install`.

- [ ] **Step 4: Verify the annotation snippet emits nothing when everything is triaged.** Run the snippet body locally against the committed data (all current ascendancies are triaged):

Run (PowerShell):
```
python -c "import json,sys; sys.path.insert(0,'scripts'); import distill; doc=json.load(open('guides.json',encoding='utf-8')); p=json.load(open('data.json',encoding='utf-8')); print('untriaged_guides:', distill.untriaged_guides(p,doc)); print('untriaged_leveling:', distill.untriaged_leveling(p,doc))"
```
Expected: `untriaged_guides: []` and `untriaged_leveling: []` (no annotations would be emitted).

- [ ] **Step 5: Commit.**

```bash
git add .github/workflows/distill.yml
git commit -m "ci(distill): output-integrity-only gate + non-blocking untriaged-ascendancy annotation"
```

---

### Task 3: `test.yml` — re-run the hard coverage-lock on curation edits

**Files:**
- Modify: `.github/workflows/test.yml` (the `push.paths` list)

**Interfaces:**
- Consumes: nothing new. `test.yml` already runs the full suite with no env var, so the curation-coverage test hard-fails there.
- Produces: `test.yml` also triggers when `guides.json` changes.

- [ ] **Step 1: Add `guides.json` to the trigger paths.** In `.github/workflows/test.yml`, replace:

```yaml
on:
  push:
    paths:
      - "scripts/**"
      - "tools/**"
      - "index.html"            # contract tests extract normKeyFE/slugOf from it
      - ".github/workflows/test.yml"
  pull_request:
  workflow_dispatch:
```

with:

```yaml
on:
  push:
    paths:
      - "scripts/**"
      - "tools/**"
      - "index.html"            # contract tests extract normKeyFE/slugOf from it
      - "guides.json"           # re-run the curation coverage-lock when a guide is added/changed
      - ".github/workflows/test.yml"
  pull_request:
  workflow_dispatch:
```

- [ ] **Step 2: Verify the YAML parses.**

Run (PowerShell): `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/test.yml',encoding='utf-8')); print('test.yml OK')"`
Expected: `test.yml OK`. If PyYAML is absent, skip and rely on the post-push Actions run.

- [ ] **Step 3: Commit.**

```bash
git add .github/workflows/test.yml
git commit -m "ci(test): re-run the suite (incl. curation coverage-lock) on guides.json changes"
```

---

## Final verification (deep quality check, after all tasks)

- [ ] **Both-mode suite:** `python scripts/test_distill.py` → `OK`, `Ran 50 tests`, 0 skipped. `$env:TINCTURE_DISTILL_GATE='1'; python scripts/test_distill.py; Remove-Item Env:TINCTURE_DISTILL_GATE` → `OK (skipped=1)` (`Ran 50 tests`) — exactly the curation test skipped, all output-integrity tests ran.

- [ ] **Simulated drift (temporary, restored after).** Edit `guides.json` to remove `"infernalist"` from `levelingUnguided` (creating an untriaged live ascendancy), then assert all three behaviors:
  1. Distill gate passes: `$env:TINCTURE_DISTILL_GATE='1'; python scripts/test_distill.py 2>&1 | Select-Object -Last 2; Remove-Item Env:TINCTURE_DISTILL_GATE` → `OK (skipped=1)` (the meta would NOT freeze).
  2. Code gate hard-fails: `python scripts/test_distill.py 2>&1 | Select-String 'infernalist|FAILED|^OK'` → a FAILED with `infernalist` (the developer-facing bite is intact).
  3. Annotation snippet warns: run the Task-2 snippet body locally → prints `::warning title=Untriaged leveling guide::'infernalist' ...`.
  Then **restore** `guides.json`: `git checkout -- guides.json` and re-confirm `python scripts/test_distill.py` → `OK`.

- [ ] **End-to-end live:** `python scripts/distill.py` (live; writes fresh data.json + bot artifacts), then `$env:TINCTURE_DISTILL_GATE='1'; python scripts/test_distill.py; Remove-Item Env:TINCTURE_DISTILL_GATE` → `OK (skipped=1)` (the gate would let the commit proceed). Then **restore** the bot artifacts: `git checkout -- data.json sitemap.xml history.json economy.json builds/index.json b/` and `git clean -fq b/` (remove any sample-only landing page). Confirm `git status` shows only the intended workflow/test files on the branch.

- [ ] **Workflow YAML lint (if PyYAML present):** both `.github/workflows/distill.yml` and `test.yml` `yaml.safe_load` clean.

- [ ] After merge: trigger `gh workflow run distill.yml`, poll to completion, expect **success** with a fresh-meta commit and (since all ascendancies are currently triaged) **no** annotation. Confirm the branch push triggered `test.yml` green.

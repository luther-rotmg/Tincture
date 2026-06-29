# Split the CI gate — output-integrity blocks the hourly distill, curation-coverage only warns

**Status:** approved design · **Date:** 2026-06-29 · **Type:** CI/pipeline change (workflows + one test decorator)
**Branch:** `feature/distill-gate-split` (off `main`)

## Problem

The hourly `distill.yml` job runs the **entire** `test_distill.py` suite as its commit gate. That suite mixes two
different kinds of checks:

1. **Output integrity** — is the freshly-written `data.json`/`builds`/`sitemap` valid and honest? (schema, no
   inflated totals, no fabricated/unloadable builds, curated-carries-no-stats, apportionment, normalize, manifest
   lockstep, ASC-map completeness, cross-lang codes.)
2. **Curation coverage** — has a human kept the static `guides.json` in step with the live meta? This is exactly
   one test: `test_shipped_guides_json_valid_and_complete` (asserts `untriaged_guides`/`untriaged_leveling` against
   the live `data.json` are empty, plus `guides_schema_errors`).

On 2026-06-29 the live meta drifted (`infernalist` entered the default-league top-N, `abyssal-lich` dropped out)
and the **curation-coverage** test failed because `infernalist` wasn't yet triaged for leveling. Because that test
gates `distill.yml`, the failure **froze the entire hourly meta refresh** — `data.json` couldn't commit at all,
for an hour, every hour, until a human curated. That's the wrong trade-off: a missing *guide link* (which the
front end already fails safe to a neutral web search for) must not stop the **meta data** from refreshing.

`distill.py` never modifies `guides.json`, so the curation-coverage check is not validating distill's *output* —
it's checking a human-maintained file against the live meta. It belongs to the code/data gate, not the data gate.

## Goal

Make the hourly meta refresh **unfreezable by a curation gap**, while keeping every *output-integrity* invariant a
hard gate and keeping the curation coverage-lock's "curate the new ascendancy" bite on code/data changes.

## Non-goals (YAGNI)

- **No** change to any output-integrity test or to what `data.json`/builds may contain.
- **No** auto-issue-filing or notification system (annotation only — the owner's chosen visibility).
- **No** change to the front end, `guides.json` data, or the `untriaged_*`/`guides_schema_errors` functions.
- **No** new dependency (stdlib + GitHub Actions only).

## Design

### 1. Skip the one curation-coverage test in the distill gate (env-var)

Decorate the single live-data curation test so it is **skipped when running as the hourly distill gate** and runs
everywhere else (local `python scripts/test_distill.py`, `test.yml`, PRs).

`scripts/test_distill.py` — add an import-time-available decorator on `test_shipped_guides_json_valid_and_complete`
(test_distill.py:532; `os` is imported at line 15, `unittest` at line 17):

```python
    @unittest.skipIf(
        os.environ.get("TINCTURE_DISTILL_GATE") == "1",
        "curation coverage is enforced in test.yml (the code/data gate), not the hourly distill "
        "gate — the meta must keep refreshing even if a newly-live ascendancy isn't triaged yet",
    )
    def test_shipped_guides_json_valid_and_complete(self):
        ...   # body unchanged
```

Rationale for env-var over alternatives: it's the idiomatic unittest mechanism, a 2-line change, keeps the test
co-located with its synthetic-fixture siblings (`test_untriaged_*`, `test_schema_errors_*`, which are
drift-independent and KEEP running in the distill gate), and the skip + reason are visible in the run log. A CLI
flag would need a custom test loader; a separate file would orphan one method and split the two workflows'
invocations.

**Deliberate consequence:** skipping this test in the distill gate also skips its `guides_schema_errors` assertion
there. That is acceptable — `distill.py` cannot introduce a `guides.json` schema error (it never writes the file);
a human edit that does is caught by `test.yml` (now also triggered by `guides.json` — see §3); and
`warn_missing_guides` still prints schema errors to stderr during the hourly run. Schema validation belongs to the
code/data gate.

### 2. `distill.yml` — set the env on the gate + add a non-blocking annotation step

`.github/workflows/distill.yml`:

- On the existing **"Validate the distilled data"** step, set `env: TINCTURE_DISTILL_GATE: "1"` (renames the step
  to clarify it's the output-integrity gate). Every output-integrity test still runs and still hard-fails the job
  (so a corrupt/inflated `data.json` still never commits — fail-safe preserved).
- Insert a new **non-blocking** step *after* validate and *before* commit that surfaces any untriaged live
  ascendancy as a GitHub `::warning::` annotation (shows on the run summary). It reuses the pipeline's pure
  functions and is defensive so it can never fail the job:

```yaml
      # A REMINDER, not a gate. The meta keeps refreshing even when curation lags; the hard
      # coverage-lock lives in test.yml. Emits ::warning:: annotations so an untriaged ascendancy
      # shows on the run summary instead of being buried in the distill step's stderr.
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

Step order becomes: Checkout → Set up Python → **Distill** → **Validate (gate, `TINCTURE_DISTILL_GATE=1`)** →
**Flag untriaged (non-blocking)** → **Commit**. If Validate fails (output integrity), the job stops before the
annotation and commit steps — correct, nothing commits. The existing `warn_missing_guides` stderr line in
`run_live` (distill.py:1001) is unchanged (useful for local `python distill.py`).

### 3. `test.yml` — keep the hard coverage-lock + validate curation edits

`.github/workflows/test.yml`:

- It already runs the full suite with **no** env var, so `test_shipped_guides_json_valid_and_complete` runs and
  hard-fails on an untriaged ascendancy (the developer-facing bite) — no change to its steps.
- Add `guides.json` to the `push` trigger `paths` (currently `scripts/**`, `tools/**`, `index.html`,
  `.github/workflows/test.yml`) so a direct curation edit re-runs the coverage-lock against the committed
  `data.json` and confirms the curation is complete.

## Resulting behavior

| Situation | distill.yml (hourly, live) | test.yml (on code/data change) |
|---|---|---|
| `data.json` corrupt/inflated/fabricated | **hard-fail, no commit** (unchanged) | hard-fail |
| New live ascendancy, not yet curated | commits the meta + a `::warning::` annotation; FE shows neutral guide/leveling links | **hard-fail** until triaged |
| Everything triaged & valid | green, commits | green |

The meta never freezes on a curation gap; the owner sees a yellow annotation on the run summary; a developer still
can't merge a change that drops a guide; the data-honesty gates are untouched.

## Honesty / safety guardrails

- Output-integrity invariants (no inflated totals, no fabricated `.build`, schema, curated-carries-no-stats) remain
  **hard gates** in `distill.yml`. This change does not weaken what may be committed to `data.json`/`builds`.
- The curation coverage-lock is not removed — it is relocated to the gate that can act on it (code/data changes),
  plus surfaced hourly as a visible reminder. Curation still can't silently rot.
- The annotation step is defensive (`continue-on-error` + try/except + reuses tolerant pure functions) so it can
  never itself break the hourly job.

## Testing & deep quality check

- **Unit/local:**
  - `python scripts/test_distill.py` → full suite green (curation test RUNS).
  - `TINCTURE_DISTILL_GATE=1 python scripts/test_distill.py` → identical pass/fail **except**
    `test_shipped_guides_json_valid_and_complete` reports **skipped** (with the reason); all output-integrity tests
    still run.
  - **Simulated drift** (temporary, restored after): remove one slug from `guides.json` `levelingUnguided` so an
    untriaged live ascendancy exists, then assert: distill-mode (`TINCTURE_DISTILL_GATE=1`) suite **passes** (the
    curation test skips), test-mode suite **hard-fails** on that ascendancy, and the annotation snippet prints a
    `::warning::` line for it. Restore `guides.json`.
- **YAML validity:** `python -c "import yaml; yaml.safe_load(open(f))"` for both workflows if PyYAML present;
  otherwise rely on the post-push Actions run.
- **End-to-end:** run `python scripts/distill.py` live, then the distill-mode validate → passes (would commit);
  trigger the real `distill.yml` via `gh workflow run` → **success**, commits the fresh meta, and (with everything
  currently triaged) emits **no** annotation. Confirm `test.yml` still green on the branch push.
- **Adversarial verification pass** over the workflow YAML diffs and the no-regression surface (the env-skip must
  not change any output-integrity test's behavior; the annotation step must be truly non-blocking).

## Integration points (verified anchors)

- `scripts/test_distill.py:532` — `@unittest.skipIf(env)` decorator on `test_shipped_guides_json_valid_and_complete`
  (body unchanged); `os` imported :15, `unittest` :17.
- `.github/workflows/distill.yml` — `env: TINCTURE_DISTILL_GATE: "1"` on the "Validate the distilled data" step;
  new non-blocking "Flag untriaged ascendancies" step before "Commit refreshed data".
- `.github/workflows/test.yml` — add `guides.json` to `push.paths`; suite step unchanged (runs full, no env).
- Reused pure functions: `distill.untriaged_guides` / `distill.untriaged_leveling` (distill.py:554+), already
  tolerant of bad payload/doc; `warn_missing_guides` (distill.py:894, called :1001) unchanged.

## Rollout

Branch off `main`; standard finish (owner's merge/PR choice). On merge the next hourly run uses the new gate.

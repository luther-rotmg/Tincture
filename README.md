# Tincture

**The current Path of Exile 2 meta, distilled from the ladder and decanted into your game with one click.**

Tincture reads what the top of the live ladder is actually playing, boils thousands of characters down to one ranked list, visualizes the whole meta, breaks down the skills, supports and passives behind every ascendancy, and **Decants any meta pick as a real, loadable `.build`** — reconstructed from a top public-ladder character and dropped straight into your in-game Build Planner in one click. It auto-refreshes hourly, so it's never out of date.

> Built for the **Runes of Aldur** league (PoE 2 patch 0.5.0). It's a single static page plus a tiny Python pipeline — no backend, no database, no tracking.

![Tincture — the live Path of Exile 2 meta, distilled and decanted](docs/demo.svg)

<!-- Placeholder above. Record a short walkthrough, save it as docs/demo.gif,
     and swap the line above to: ![Tincture](docs/demo.gif) -->

---

## Why it's different

The big sites are planners and raw stat dashboards. Tincture is a **discovery** tool with one job: get you from "what should I play?" to a confident starting point, fast — and it's honest about exactly what it knows.

- **Distilled, not dumped.** poe.ninja shows you the full spread of ladder data. Tincture serves the consensus — ranked, tiered, each row carrying an editorial playstyle note and a sample-confidence cue, with 24-hour trend arrows that light up once a day of snapshots has accumulated.
- **The whole meta, visualized.** *The Assay* charts class composition, ascendancy shares, meta concentration (HHI + effective ascendancies), tier spread, a cross-league comparison, and **The Crucible** — an ascendancy × league-mode heatmap with a *Share* ⇄ *Vs. typical* (over/under-index) toggle. All hand-rolled SVG/CSS, no libraries, computed in your browser.
- **The build behind the pick.** Expand any ledger row for that ascendancy's most popular skills, support gems, passive notables and unique items — with median EHP/DPS — aggregated from its whole ladder population. *The Dispensary* does the same for the entire meta at once.
- **All the data, yours.** *The Cellar* lays every build across every league in one sortable table, shows the raw `data.json`, and exports CSV/JSON. The static files the page reads (`data.json`, `meta-detail.json`, `builds/<slug>.build`) are the public "API" — no backend, no key.
- **One-click Decant — real loadable builds.** Every meta pick now Decants a real, loadable `.build`, reconstructed from a top public-ladder character (credited in the file), straight into your in-game Build Planner via the [File System Access API](https://developer.mozilla.org/en-US/docs/Web/API/File_System_API) or a download. Picks not yet reconstructed fall back to an honest labelled template — never a fabricated build the game would silently refuse.
- **Never stale.** A scheduled job re-distills the meta every hour, **validates** the result, and commits only if it passes. The page just reads it.

---

## How it works

```
poe.ninja PoE2 build API  ──►  scripts/distill.py  ──►  data.json  ──►  index.html
   (ladder-derived meta)       (hourly, via Actions)     (committed)     (static page)
```

1. **`scripts/distill.py`** pulls the current league's build aggregation from poe.ninja (which is itself derived from GGG's official ladder — the top 15,000 characters), normalizes it, assigns tiers, and computes each build's 24-hour movement by diffing the previous snapshot.
2. The result is written to **`data.json`** in the front end's exact schema.
3. **`.github/workflows/distill.yml`** runs that hourly and commits `data.json` when the meta moves.
4. **`index.html`** reads `data.json` (falling back to bundled sample data if it's missing), renders the ledger, and handles Decant entirely client-side.

It's stdlib-only Python — no dependencies to install — and it **fails safe**: if poe.ninja errors or returns something unexpected, the previous `data.json` is left untouched so the site never breaks.

---

## Project layout

```
Tincture/
├── index.html                  # the whole front end (HTML + CSS + JS, no build step)
├── data.json                   # the distilled meta (committed by the pipeline)
├── SCHEMA.md                   # the reverse-engineered .build file format
├── scripts/
│   ├── distill.py              # the distillation engine (meta -> data.json)
│   ├── buildfile.py            # .build serializer + validator (+ is_loadable guard)
│   ├── test_distill.py         # stdlib unit tests — the honesty invariants
│   └── ggg.py                  # GGG API client: ladder character -> .build
├── .github/workflows/
│   ├── distill.yml             # hourly refresh — validates, then commits if it passes
│   └── test.yml                # runs the test suite on code changes
├── LICENSE
└── README.md
```

---

## Run it locally

No dependencies. Python 3.9+.

```bash
# Full pipeline on bundled sample data (no network) — writes data.json:
python scripts/distill.py --demo

# Probe the live source — prints the leagues + top ascendancies it returns:
python scripts/distill.py --probe

# A real run (what the Action does):
python scripts/distill.py

# Run the test suite (stdlib unittest — no network, no pip):
python scripts/test_distill.py
python scripts/buildfile.py --selftest
```

To view the site, serve the folder and open it (the File System Access API needs `http`/`https`, not `file://`):

```bash
python -m http.server 8000   # then open http://localhost:8000
```

---

## Deploy (GitHub Pages)

1. Push this folder to a public repo.
2. **Settings → Pages → Build and deployment → Deploy from a branch → `main` / root.** It'll be live at `https://<you>.github.io/Tincture/`.
3. **Settings → Actions → General → Workflow permissions → Read and write.** (Lets the hourly job commit `data.json`.)
4. **Actions tab → Distill the meta → Run workflow** once to populate fresh data immediately.

> The one-click folder save works on the deployed HTTPS site in Chromium browsers (Chrome, Edge, Brave, Opera). Firefox/Safari fall back to a normal download with a "move it here" note.

---

## The live data source

The meta comes from poe.ninja's (undocumented but stable) PoE 2 endpoint
**`GET /poe2/api/data/build-index-state`**, wired up in `scripts/distill.py`. It
returns each current league's most-played ascendancies with a share-of-ladder %
and a trend flag. `distill.py` picks the softcore **Runes of Aldur** league
(`leagueUrl: runesofaldur`), maps each ascendancy to its base class, reconstructs
per-ascendancy character counts from the league total, tiers them, and diffs
against the previous snapshot for the 24-hour trend arrows. It needs no auth and
answers bare requests, so the GitHub Action fetches it directly.

Run `python scripts/distill.py --probe` to see exactly what it returns.

> poe.ninja ranks **ascendancies**, not individual skills, so the ledger headlines
> the ascendancy; the per-build "signature skill" arrives with the GGG character
> pull (below).

---

## Roadmap

- [x] Decode the `.build` format ([SCHEMA.md](SCHEMA.md)) + a validated serializer (`scripts/buildfile.py`)
- [x] Live meta from poe.ninja's `build-index-state` (ascendancy shares + 24h trend)
- [x] League switcher — Softcore / Hardcore / SSF / HC SSF + Standard (dropdown)
- [x] **The Assay** — class composition, ascendancy shares, meta concentration (HHI + effective ascendancies), tier spread, cross-league comparison, and **The Crucible** ascendancy × mode heatmap with a Share / over-under-index toggle (hand-rolled SVG/CSS)
- [x] **The Cellar** — every build across every league in one sortable table, raw `data.json` view, CSV/JSON export, open-data docs
- [x] Ledger enrichment — editorial playstyle tags, sample-confidence cue, honest "baseline" trends, top-N coverage footnote
- [x] **Real loadable Decant — LIVE** 🎉 — every meta ascendancy now Decants a real, loadable `.build`, reconstructed from a top public-ladder character via [`tools/build-from-ninja.cjs`](tools/build-from-ninja.cjs): passives mapped through the GGG tree export, gems via PoB2 metadata, items from the character export, then **cohesion-QA'd** before it ships. Each build credits its source character. Refreshed weekly ([`builds.yml`](.github/workflows/builds.yml)). Picks without a reconstruction yet still export the honest `.txt` template — never a fabricated build.
- [x] Test suite + CI — stdlib invariants (`scripts/test_distill.py`), and the hourly distill validates its output before committing
- [x] **Passive node-id → `.build` slug map** — derived from GGG's official skill-tree export (`scripts/treedata.py`); no GGPK extraction needed
- [x] **Ascendancy → `.build` code table** — completed and cross-confirmed from the same export (`scripts/buildfile.py`; `treedata.py --check` re-verifies per patch)
- [ ] **"Export *my* character"** — a logged-in user's own GGG character → a personal `.build` (the self-only OAuth path; complements the public-ladder reconstruction above). Needs a registered GGG OAuth client (see [docs/owner-actions.md](docs/owner-actions.md))
- [ ] **Direct GGG ladder cross-check** — a second, official source for ascendancy shares (scaffolded in `scripts/ggg.py`; needs the OAuth client). Summary-only, so it validates shares, not build content
- [ ] In-app source attribution — surface each reconstructed build's source character/account in the UI (it's already credited inside the file)
- [x] Guide pointers — a "find a guide" link on the headline and every ledger row opens a neutral, patch-specific web search for that ascendancy's community guides (honest search, not an endorsed "best guide")
- [ ] Curated guide directory — hand-pick a specific best guide per meta build (needs manual curation each league)

---

## Credits & disclaimer

Meta data via [poe.ninja](https://poe.ninja), derived from Grinding Gear Games' official ladder.

Tincture is an independent fan project and is **not affiliated with or endorsed by Grinding Gear Games**. Build files are player-driven; GGG does not curate or rank them. Judge a build on its merits before committing a league to it.

## License

MIT — see [LICENSE](LICENSE).

# Tincture

**The current Path of Exile 2 meta, distilled from the ladder and decanted into your game with one click.**

Tincture reads what the top of the live ladder is actually playing, boils thousands of characters down to one ranked list, and lets you drop any build straight into your in-game Build Planner — no alt-tabbing, no copy-paste, no spreadsheets. It auto-refreshes every hour, so it's never out of date.

> Built for the **Runes of Aldur** league (PoE 2 patch 0.5.0). It's a single static page plus a tiny Python pipeline — no backend, no database, no tracking.

![Tincture — the live Path of Exile 2 meta, distilled and decanted](docs/demo.svg)

<!-- Placeholder above. Record a short walkthrough, save it as docs/demo.gif,
     and swap the line above to: ![Tincture](docs/demo.gif) -->

---

## Why it's different

The big sites are planners and raw stat dashboards. Tincture is a **discovery** tool with one job: get you from "what should I play?" to *playing it* in a single click.

- **Distilled, not dumped.** poe.ninja shows you the full spread of ladder data. Tincture serves the consensus — ranked, tiered, with 24-hour trend arrows so you can see what's rising before everyone else.
- **One-click Decant.** Connect your `BuildPlanner` folder once, and every build writes straight into it via the [File System Access API](https://developer.mozilla.org/en-US/docs/Web/API/File_System_API). The game picks it up automatically. (Other sites just hand you a download to move yourself.)
- **Never stale.** A scheduled job re-distills the meta every hour and commits the result. The page just reads it.

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
│   ├── buildfile.py            # .build serializer + validator
│   └── ggg.py                  # GGG API client: ladder character -> .build
├── .github/workflows/
│   └── distill.yml             # hourly refresh + commit
├── LICENSE
└── README.md
```

---

## Run it locally

No dependencies. Python 3.9+.

```bash
# Full pipeline on bundled sample data (no network) — writes data.json:
python scripts/distill.py --demo

# Confirm the live poe.ninja builds endpoint (see below):
python scripts/distill.py --probe

# A real run (what the Action does):
python scripts/distill.py
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

## Finishing the live data (one thing to confirm)

poe.ninja's PoE 2 endpoints are **undocumented**, so the exact *builds* URL needs a 30-second confirmation:

1. Run `python scripts/distill.py --probe`. If one of the candidate endpoints returns JSON, you're done — note its top-level keys.
2. If not: open <https://poe.ninja/poe2/builds>, open **DevTools → Network → Fetch/XHR**, reload, and click the request whose response is the build list. Copy its URL and a snippet of the JSON.

Then update `BUILDS_ENDPOINT_CANDIDATES` and the four field lookups in `normalize_builds()` to match — everything downstream is already done and tested.

---

## Roadmap

- [x] Decode the `.build` format ([SCHEMA.md](SCHEMA.md)) + a validated serializer (`scripts/buildfile.py`)
- [ ] Confirm the poe.ninja builds endpoint + field mapping
- [ ] **Real Decant content** — pull a representative public ladder character via GGG's Character API, run it through the serializer, and commit `builds/<slug>.build` (the page already fetches those, falling back to a placeholder)
- [ ] Complete the ascendancy → code table
- [ ] **Direct GGG ladder cross-check** — a second source so the meta isn't single-sourced
- [ ] A guide directory — link out to the best community guide for each meta build
- [ ] Hardcore / SSF toggles

---

## Credits & disclaimer

Meta data via [poe.ninja](https://poe.ninja), derived from Grinding Gear Games' official ladder.

Tincture is an independent fan project and is **not affiliated with or endorsed by Grinding Gear Games**. Build files are player-driven; GGG does not curate or rank them. Judge a build on its merits before committing a league to it.

## License

MIT — see [LICENSE](LICENSE).

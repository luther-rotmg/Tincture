#!/usr/bin/env python3
"""
Tincture — the distillation engine.

Reads the current Path of Exile 2 challenge-league build meta, boils it down to a
single ranked list, and writes data.json (the file the front end reads).

Design notes
------------
* Stdlib only (urllib + json). No pip install needed, so the GitHub Action stays
  dependency-free and this runs anywhere Python 3.9+ exists.
* poe.ninja's PoE2 endpoints are UNDOCUMENTED and rate-limited (~12 req / 5 min),
  so we make only a couple of calls per run and cache nothing client-side.
* The exact *builds* endpoint + response shape are the one thing that must be
  confirmed against a live response (see README → "Confirm the builds endpoint",
  or run this script with --probe). Everything downstream of normalize_builds()
  is finished and tested via --demo.
* Fails safe: if the live fetch errors or returns an unexpected shape, we keep the
  existing data.json untouched and exit 0, so a bad upstream response never breaks
  the deployed site.

Usage
-----
  python distill.py            # live run (used by the GitHub Action)
  python distill.py --demo     # no network; runs the full pipeline on sample data
  python distill.py --probe    # try candidate builds endpoints, print what comes back
"""

import json
import sys
import os
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

# ----------------------------------------------------------------------------- #
# Config
# ----------------------------------------------------------------------------- #
LEAGUE = "Runes of Aldur"   # current challenge league (0.5.0). Case-sensitive for the API.
PATCH = "0.5.0"
MODE = "Softcore"

POE2_API = "https://poe.ninja/poe2/api"

# A descriptive User-Agent is required by GGG and is good manners for poe.ninja.
# Put a real contact in here when you publish (GGG asks for one).
USER_AGENT = "Tincture/0.1 (+https://github.com/luther-rotmg/Tincture; PoE2 meta distiller)"

# Tier cutoffs by share-of-ladder (%). Tuned so the headline builds read as S.
TIERS = [("S", 9.0), ("A", 4.5), ("B", 2.5), ("C", 0.0)]

# poe.ninja builds endpoint: UNCONFIRMED. These are ordered guesses based on the
# confirmed /poe2/api/ base. --probe will tell us which (if any) responds; the real
# one is trivial to grab from the Network tab on poe.ninja/poe2/builds (see README).
BUILDS_ENDPOINT_CANDIDATES = [
    f"{POE2_API}/builds/overview",
    f"{POE2_API}/builds",
    f"{POE2_API}/build/overview",
    f"{POE2_API}/character/overview",
]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(ROOT, "data.json")
REQUEST_TIMEOUT = 20

# ----------------------------------------------------------------------------- #
# Sample data — realistic Runes of Aldur meta. Used by --demo and as the seed
# shape. The live pipeline replaces this with real poe.ninja data.
# ----------------------------------------------------------------------------- #
SAMPLE_BUILDS = [
    {"cls": "Huntress",  "asc": "Spirit Walker",       "skill": "Whirling Slash",       "pop": 13.8, "n": 1772, "tag": "Does a bit of everything — clears fast, bosses fine"},
    {"cls": "Monk",      "asc": "Martial Artist",      "skill": "Tempest Flurry",       "pop": 11.1, "n": 1424, "tag": "Highest ceiling once geared"},
    {"cls": "Ranger",    "asc": "Deadeye",             "skill": "Lightning Arrow",      "pop": 9.7,  "n": 1245, "tag": "The league-start default"},
    {"cls": "Witch",     "asc": "Infernalist",         "skill": "Skeletal Storm Mages", "pop": 8.3,  "n": 1066, "tag": "Hands-off minion comfort"},
    {"cls": "Sorceress", "asc": "Stormweaver",         "skill": "Frost Bomb",           "pop": 6.9,  "n": 886,  "tag": "Deletes pinnacle bosses"},
    {"cls": "Ranger",    "asc": "Pathfinder",          "skill": "Ice-Tipped Arrows",    "pop": 5.4,  "n": 693,  "tag": "Tanky, flask-driven mapper"},
    {"cls": "Warrior",   "asc": "Titan",               "skill": "Earthshatter",         "pop": 4.8,  "n": 616,  "tag": "Slow, unkillable, heavy hits"},
    {"cls": "Witch",     "asc": "Lich",                "skill": "Galvanic Shards",      "pop": 4.1,  "n": 526,  "tag": "Crossbow caster, strong burst"},
    {"cls": "Monk",      "asc": "Invoker",             "skill": "Tempest Bell",         "pop": 3.6,  "n": 462,  "tag": "Combo melee, high skill floor"},
    {"cls": "Mercenary", "asc": "Gemling Legionnaire", "skill": "Galvanic Field",       "pop": 3.0,  "n": 385,  "tag": "Flexible gem-stacking shell"},
    {"cls": "Sorceress", "asc": "Chronomancer",        "skill": "Comet",                "pop": 2.4,  "n": 308,  "tag": "Spike-cast glass cannon"},
]

# ----------------------------------------------------------------------------- #
# HTTP
# ----------------------------------------------------------------------------- #
def http_get_json(url, params=None):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)

# ----------------------------------------------------------------------------- #
# Source: poe.ninja builds
# ----------------------------------------------------------------------------- #
def fetch_poeninja_builds(league):
    """
    Return a list of raw build dicts from poe.ninja, or None on failure.

    NOTE: endpoint + field names are UNCONFIRMED. normalize_builds() does the
    mapping and logs the raw keys if it can't find what it expects, so the first
    live run tells us exactly how to finish this.
    """
    last_err = None
    for url in BUILDS_ENDPOINT_CANDIDATES:
        try:
            data = http_get_json(url, {"league": league, "overview": league})
            print(f"[poe.ninja] {url} -> 200")
            return data
        except urllib.error.HTTPError as e:
            print(f"[poe.ninja] {url} -> HTTP {e.code}")
            last_err = e
        except Exception as e:  # noqa: BLE001
            print(f"[poe.ninja] {url} -> {type(e).__name__}: {e}")
            last_err = e
        time.sleep(2)  # be polite; well under the 12-per-5-min limit
    print(f"[poe.ninja] all candidate endpoints failed ({last_err})")
    return None


def normalize_builds(raw):
    """
    Map poe.ninja's response into our internal shape:
        {cls, asc, skill, pop (float %), n (int)}

    poe.ninja aggregates at the ascendancy level with a popularity percentage and
    the dominant skills. The exact field names below are placeholders keyed off the
    likely structure ('lines' of character/ascendancy stats). Adjust the four
    PICK_* lookups once --probe shows the real keys — nothing else needs to change.
    """
    if raw is None:
        return None

    # poe.ninja overviews are usually under "lines" (sometimes the root list).
    rows = raw.get("lines") if isinstance(raw, dict) else raw
    if not isinstance(rows, list) or not rows:
        print("[normalize] unexpected shape; top-level keys =",
              list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__)
        return None

    def pick(d, *keys, default=None):
        for k in keys:
            if k in d and d[k] not in (None, ""):
                return d[k]
        return default

    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        asc = pick(r, "ascendancy", "ascendancyName", "subclass", "name")
        cls = pick(r, "class", "className", "characterClass", default="")
        # "top skill" may be a list of {name, ...} or a flat field
        skill = pick(r, "mainSkill", "skill", "topSkill")
        if isinstance(skill, list) and skill:
            s0 = skill[0]
            skill = s0.get("name") if isinstance(s0, dict) else s0
        pop = pick(r, "percentage", "popularity", "share", default=None)
        n = pick(r, "count", "characters", "sampleSize", default=0)
        if asc is None or pop is None:
            continue
        try:
            out.append({
                "cls": str(cls or ""),
                "asc": str(asc),
                "skill": str(skill or "—"),
                "pop": round(float(pop), 1),
                "n": int(n or 0),
                "tag": "",
            })
        except (TypeError, ValueError):
            continue

    if not out:
        print("[normalize] matched 0 rows — sample row keys =",
              list(rows[0].keys()) if isinstance(rows[0], dict) else type(rows[0]).__name__)
        return None
    return out

# ----------------------------------------------------------------------------- #
# Distillation: tiers, trends, ranking
# ----------------------------------------------------------------------------- #
def tier_for(pop):
    for name, cutoff in TIERS:
        if pop >= cutoff:
            return name
    return "C"


def load_previous():
    if not os.path.exists(OUT_PATH):
        return None
    try:
        with open(OUT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        print(f"[trend] couldn't read previous data.json: {e}")
        return None


def key_of(b):
    return f"{b['asc']}|{b['skill']}".lower()


def apply_trends(builds, previous):
    """delta = current share - share an hour ago. 0 on first run / new builds."""
    prev_map = {}
    if previous and not previous.get("_seed") and isinstance(previous.get("builds"), list):
        for pb in previous["builds"]:
            prev_map[key_of(pb)] = pb.get("pop", 0.0)
    for b in builds:
        old = prev_map.get(key_of(b))
        b["delta"] = round(b["pop"] - old, 1) if old is not None else 0.0
    return builds


def distill(raw_builds, previous):
    builds = [b for b in raw_builds if b.get("pop", 0) > 0]
    builds.sort(key=lambda b: b["pop"], reverse=True)
    for i, b in enumerate(builds, start=1):
        b["rank"] = i
        b["tier"] = tier_for(b["pop"])
        if not b.get("tag"):
            b["tag"] = f"{b['cls']} · {b['skill']}"
    apply_trends(builds, previous)

    ascendancies = len({b["asc"] for b in builds})
    characters = sum(int(b.get("n", 0)) for b in builds)

    return {
        "league": LEAGUE,
        "patch": PATCH,
        "mode": MODE,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "totals": {
            "characters": characters,
            "sources": 1,            # bump to 2 when the GGG ladder cross-check is on
            "ascendancies": ascendancies,
        },
        "builds": [
            {k: b[k] for k in ("rank", "tier", "cls", "asc", "skill", "pop", "delta", "n", "tag")}
            for b in builds
        ],
    }


def write_data(payload):
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"[write] {OUT_PATH} — {len(payload['builds'])} builds, "
          f"{payload['totals']['characters']:,} characters")

# ----------------------------------------------------------------------------- #
# Modes
# ----------------------------------------------------------------------------- #
def run_probe():
    print(f"Probing poe.ninja PoE2 builds endpoints for league '{LEAGUE}'...\n")
    for url in BUILDS_ENDPOINT_CANDIDATES:
        try:
            data = http_get_json(url, {"league": LEAGUE, "overview": LEAGUE})
            keys = list(data.keys()) if isinstance(data, dict) else f"list[{len(data)}]"
            print(f"  OK   {url}\n       top-level: {keys}\n")
        except urllib.error.HTTPError as e:
            print(f"  {e.code}  {url}")
        except Exception as e:  # noqa: BLE001
            print(f"  ERR  {url} -> {type(e).__name__}: {e}")
        time.sleep(2)
    print("\nIf none worked: open https://poe.ninja/poe2/builds in your browser, open\n"
          "DevTools → Network → Fetch/XHR, reload, and find the request whose response\n"
          "is the build list. Paste its URL + a snippet of the JSON and I'll finalize the mapping.")


def run_demo():
    print("DEMO mode — no network. Running the full pipeline on sample data.\n")
    previous = load_previous()
    payload = distill([dict(b) for b in SAMPLE_BUILDS], previous)
    write_data(payload)
    print("\nTop of the ledger:")
    for b in payload["builds"][:5]:
        arrow = "▲" if b["delta"] > 0 else "▼" if b["delta"] < 0 else "—"
        print(f"  {b['rank']:>2}. [{b['tier']}] {b['asc']:<20} {b['skill']:<18} "
              f"{b['pop']:>5.1f}%  {arrow}{abs(b['delta']):.1f}")


def run_live():
    print(f"LIVE run — distilling '{LEAGUE}' ({MODE}, {PATCH})\n")
    previous = load_previous()
    raw = fetch_poeninja_builds(LEAGUE)
    builds = normalize_builds(raw)
    if not builds:
        print("\n[live] no usable build data this run — keeping the existing data.json. "
              "Exiting 0 so the site stays up.")
        return 0
    payload = distill(builds, previous)
    write_data(payload)
    return 0


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--probe":
        run_probe(); return 0
    if arg == "--demo":
        run_demo(); return 0
    return run_live()


if __name__ == "__main__":
    sys.exit(main())

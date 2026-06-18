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
  so we make only one call per run and cache nothing client-side.
* The builds source is the confirmed GET /poe2/api/data/build-index-state. It
  returns every current league's top ascendancies with a share-of-ladder % and a
  -1/0/1 trend flag. Verified live and reachable from a bare request, so the
  GitHub Action (Python urllib, datacenter IP) can fetch it. See --probe.
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

# poe.ninja builds source — CONFIRMED live. GET, no auth, reachable from a bare
# request (so the GitHub Action can fetch it). Returns every current league's top
# ascendancies with a share-of-ladder % and a -1/0/1 trend flag.
BUILD_INDEX_URL = f"{POE2_API}/data/build-index-state"

# Our league's url key inside that payload (softcore trade — not the HC / SSF rows).
LEAGUE_URL = "runesofaldur"

# poe.ninja ranks at the ascendancy level (its "class" field is the ascendancy name)
# and exposes no dominant skill here. Map each ascendancy to its base class for the
# front end's class filter + sub-line; ascendancies not listed fall back to "".
ASC_TO_CLASS = {
    "Titan": "Warrior", "Warbringer": "Warrior", "Smith of Kitava": "Warrior",
    "Infernalist": "Witch", "Blood Mage": "Witch", "Lich": "Witch", "Abyssal Lich": "Witch",
    "Deadeye": "Ranger", "Pathfinder": "Ranger",
    "Invoker": "Monk", "Acolyte of Chayula": "Monk", "Martial Artist": "Monk",
    "Witchhunter": "Mercenary", "Gemling Legionnaire": "Mercenary", "Tactician": "Mercenary",
    "Stormweaver": "Sorceress", "Chronomancer": "Sorceress", "Disciple of Varashta": "Sorceress",
    "Spirit Walker": "Huntress", "Amazon": "Huntress", "Ritualist": "Huntress",
    "Oracle": "Druid",
}

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
        # Not required today (the endpoint answers bare requests), but it mirrors the
        # browser and future-proofs us if poe.ninja tightens its Cloudflare rules.
        "Referer": "https://poe.ninja/poe2/builds",
    })
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)

# ----------------------------------------------------------------------------- #
# Source: poe.ninja builds
# ----------------------------------------------------------------------------- #
def fetch_poeninja_builds():
    """Return the parsed build-index-state payload, or None on any failure."""
    try:
        data = http_get_json(BUILD_INDEX_URL)
        n = len(data.get("leagueBuilds", [])) if isinstance(data, dict) else 0
        print(f"[poe.ninja] {BUILD_INDEX_URL} -> 200 ({n} leagues)")
        return data
    except urllib.error.HTTPError as e:
        print(f"[poe.ninja] {BUILD_INDEX_URL} -> HTTP {e.code}")
    except Exception as e:  # noqa: BLE001
        print(f"[poe.ninja] {BUILD_INDEX_URL} -> {type(e).__name__}: {e}")
    return None


def _select_league(leagues):
    """Pick our softcore trade league by url key, with a display-name fallback."""
    by_url = next((l for l in leagues if l.get("leagueUrl") == LEAGUE_URL), None)
    if by_url is not None:
        return by_url
    return next((l for l in leagues if l.get("leagueName") == LEAGUE), None)


def normalize_builds(raw):
    """
    Map poe.ninja's build-index-state into our internal shape:
        {cls, asc, skill, pop (float %), n (int)}

    Confirmed live shape:
        {"leagueBuilds": [
            {"leagueName": "Runes of Aldur", "leagueUrl": "runesofaldur",
             "total": 124248,
             "statistics": [{"class": "Martial Artist", "percentage": 24.5, "trend": -1}, ...]},
            ... (HC / SSF variants) ]}

    poe.ninja ranks ascendancies (its "class" field) and gives no dominant skill, so
    `skill` is left blank and the front end shows the ascendancy as the headline.
    `n` is reconstructed from the league total and each ascendancy's share.
    """
    if not isinstance(raw, dict):
        return None
    leagues = raw.get("leagueBuilds")
    if not isinstance(leagues, list) or not leagues:
        print("[normalize] unexpected shape; top-level keys =",
              list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__)
        return None

    league = _select_league(leagues)
    if league is None:
        print(f"[normalize] league {LEAGUE_URL!r} not found in",
              [l.get("leagueUrl") for l in leagues])
        return None

    total = int(league.get("total") or 0)
    out = []
    for s in league.get("statistics") or []:
        if not isinstance(s, dict):
            continue
        asc = s.get("class")
        pop = s.get("percentage")
        if not asc or pop is None:
            continue
        try:
            pop = float(pop)
        except (TypeError, ValueError):
            continue
        out.append({
            "cls": ASC_TO_CLASS.get(asc, ""),
            "asc": str(asc),
            "skill": "",  # build-index-state does not expose a dominant skill
            "pop": round(pop, 1),
            "n": round(total * pop / 100.0) if total else 0,
            "tag": "",
        })

    if not out:
        print("[normalize] matched 0 ascendancies in", league.get("leagueName"))
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


def distill(raw_builds, previous, total=None):
    builds = [b for b in raw_builds if b.get("pop", 0) > 0]
    builds.sort(key=lambda b: b["pop"], reverse=True)
    for i, b in enumerate(builds, start=1):
        b["rank"] = i
        b["tier"] = tier_for(b["pop"])
    apply_trends(builds, previous)

    ascendancies = len({b["asc"] for b in builds})
    # Prefer the source's real league population; fall back to summing the shown
    # builds (the demo path has no separate total).
    characters = int(total) if total else sum(int(b.get("n", 0)) for b in builds)

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
    print(f"Probing poe.ninja build-index-state:\n  {BUILD_INDEX_URL}\n")
    try:
        data = http_get_json(BUILD_INDEX_URL)
    except Exception as e:  # noqa: BLE001
        print(f"  failed: {type(e).__name__}: {e}")
        return
    leagues = data.get("leagueBuilds", []) if isinstance(data, dict) else []
    print(f"  OK — {len(leagues)} leagues returned:")
    for l in leagues:
        mark = "  <-- ours" if l.get("leagueUrl") == LEAGUE_URL else ""
        print(f"    {str(l.get('leagueUrl')):<22} {str(l.get('leagueName')):<24} "
              f"total={l.get('total'):>7}  ascendancies={len(l.get('statistics') or [])}{mark}")
    ours = _select_league(leagues)
    if ours:
        print(f"\n  Top of {ours.get('leagueName')}:")
        for s in (ours.get('statistics') or [])[:5]:
            print(f"    {str(s.get('class')):<22} {float(s.get('percentage', 0)):.1f}%  "
                  f"trend={s.get('trend')}")


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
    raw = fetch_poeninja_builds()
    builds = normalize_builds(raw)
    if not builds:
        print("\n[live] no usable build data this run — keeping the existing data.json. "
              "Exiting 0 so the site stays up.")
        return 0
    leagues = raw.get("leagueBuilds", []) if isinstance(raw, dict) else []
    league = _select_league(leagues)
    total = int(league.get("total") or 0) if league else 0
    payload = distill(builds, previous, total=total or None)
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

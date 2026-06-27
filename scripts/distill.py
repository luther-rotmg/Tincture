#!/usr/bin/env python3
"""
Tincture — the distillation engine.

Reads the current Path of Exile 2 build meta across every league variant, boils
each down to a ranked list, and writes data.json (the file the front end reads).

Design notes
------------
* Stdlib only (urllib + json). No pip install needed, so the GitHub Action stays
  dependency-free and this runs anywhere Python 3.9+ exists.
* The builds source is the confirmed GET /poe2/api/data/build-index-state. One call
  returns *every* current league with its top ascendancies (share-of-ladder % and a
  -1/0/1 trend flag) plus a league total. Verified live and reachable from a bare
  request, so the Action (Python urllib, datacenter IP) can fetch it. See --probe.
* We surface the current challenge league's four variants (Softcore / Hardcore /
  SSF / HC SSF) plus permanent Standard. poe.ninja does NOT break down permanent
  leagues, so Standard comes back with no statistics — we keep it in the dropdown
  with an honest empty state rather than inventing data.
* Fails safe: if the live fetch errors or no league has usable builds, we keep the
  existing data.json untouched and exit 0, so a bad upstream response never breaks
  the deployed site.

Usage
-----
  python distill.py            # live run (used by the GitHub Action)
  python distill.py --demo     # no network; runs the full pipeline on sample data
  python distill.py --probe    # dump the live leagues + their top ascendancies
"""

import json
import sys
import os
import re
import html as _html
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

# ----------------------------------------------------------------------------- #
# Config
# ----------------------------------------------------------------------------- #
PATCH = "0.5.3"

POE2_API = "https://poe.ninja/poe2/api"

# A descriptive, contactable User-Agent — good manners for poe.ninja (which has no public
# terms or rate-limit headers, so politeness is the only signal we can send). Names the
# project, its purpose, cadence, and a real contact so the maintainer can reach us rather
# than just block the IP. Mirrors GGG's documented UA convention minus the OAuth prefix.
USER_AGENT = ("Tincture/0.5.0 (+https://github.com/luther-rotmg/Tincture; "
             "contact: ryan.duke360@gmail.com) PoE2 meta distiller, hourly, stdlib-urllib")

# Tier cutoffs by share-of-ladder (%). Tuned so the headline builds read as S.
TIERS = [("S", 9.0), ("A", 4.5), ("B", 2.5), ("C", 0.0)]

# poe.ninja builds source — CONFIRMED live. GET, no auth, reachable from a bare
# request (so the GitHub Action can fetch it). Returns every current league's top
# ascendancies with a share-of-ladder % and a -1/0/1 trend flag.
BUILD_INDEX_URL = f"{POE2_API}/data/build-index-state"

# poe.ninja currency EXCHANGE — CONFIRMED live (plain JSON, no auth). index-state gives the
# current snapshot version + the economy league's DISPLAY name (the exchange endpoint requires
# the display name, e.g. "Runes of Aldur", NOT the url slug). Then:
#   GET /poe2/api/economy/exchange/{version}/overview?league={DisplayName}&type=Currency
# -> {core:{rates,primary,secondary}, items:[{id,name}], lines:[{id,primaryValue(=Divine),
#     volumePrimaryValue, sparkline:{totalChange,...}}]}.
INDEX_STATE_URL = f"{POE2_API}/data/index-state"

# The current challenge league family. Its variants share this url stem + a suffix.
# When a new league launches, update these two lines and the rest follows.
LEAGUE_FAMILY = "runesofaldur"
FAMILY_NAME = "Runes of Aldur"

# (url suffix, mode label) for the four challenge-league variants, in dropdown order.
VARIANTS = [("", "Softcore"), ("hc", "Hardcore"), ("ssf", "SSF"), ("hcssf", "HC SSF")]

# Permanent leagues to always surface. poe.ninja publishes no ranked build breakdown
# for these, so they show up empty (with a note) — kept because users ask for them.
PERMANENT = [("standard", "Standard", "Standard")]  # (url, name, mode)

NO_BREAKDOWN_NOTE = (
    "poe.ninja doesn't publish a ranked build breakdown for permanent leagues. "
    "Pick a Runes of Aldur league for the live meta."
)

# poe.ninja doesn't rank Standard, so instead of an empty tab we surface a short,
# hand-picked set of evergreen archetypes. These are NOT live ladder data (no %, no
# trend) — just classic, beginner-friendly starting points. Edit freely.
CURATED_NOTE = (
    "Standard isn't ranked by poe.ninja, so these are hand-picked evergreen "
    "archetypes — classic, beginner-friendly starting points, not live ladder data."
)
CURATED = {
    "standard": [
        {"cls": "Witch",     "asc": "Infernalist", "tag": "Evergreen minion summoner — hands-off, beginner-friendly"},
        {"cls": "Ranger",    "asc": "Deadeye",     "tag": "Classic bow / projectiles — fast clear"},
        {"cls": "Warrior",   "asc": "Titan",       "tag": "Slow, tanky slam melee — very forgiving"},
        {"cls": "Sorceress", "asc": "Stormweaver", "tag": "Elemental spellcaster — strong bossing"},
        {"cls": "Monk",      "asc": "Invoker",     "tag": "Elemental strike melee — high mobility"},
        {"cls": "Mercenary", "asc": "Witchhunter", "tag": "Crossbow generalist — flexible, anti-caster"},
    ],
}


def target_leagues():
    """The leagues we surface, in dropdown order: challenge variants then permanent."""
    out = [{"url": LEAGUE_FAMILY + suffix, "name": FAMILY_NAME, "mode": mode,
            "label": f"{FAMILY_NAME} · {mode}"} for suffix, mode in VARIANTS]
    out += [{"url": url, "name": name, "mode": mode, "label": name}
            for url, name, mode in PERMANENT]
    return out


TARGET_LEAGUES = target_leagues()

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
    "Oracle": "Druid", "Shaman": "Druid",
}

# EDITORIAL, not derived from ladder data. A short, present-tense archetype description
# per ascendancy — purely so live ledger rows aren't blank. These describe how a build
# FEELS, never how it ranks (no "best"/"meta"/"S-tier"). Mirrors the Standard CURATED
# tags. Unknown ascendancies fall back to "" and the front end degrades gracefully.
ASC_TAGS = {
    "Martial Artist": "Combo melee striker — high mobility, high skill ceiling",
    "Invoker": "Elemental strike monk — fast, dodge-heavy",
    "Acolyte of Chayula": "Chaos/darkness monk — sustains through leech",
    "Spirit Walker": "Spear-and-spirit hybrid — clears fast, bosses fine",
    "Amazon": "Spear skirmisher — crit and mobility",
    "Ritualist": "Ailment-stacking huntress — damage over time",
    "Deadeye": "Classic bow / projectiles — fast clear, league-start friendly",
    "Pathfinder": "Flask-driven mapper — tanky, sustained",
    "Titan": "Slow, tanky slam melee — very forgiving",
    "Warbringer": "Warcry-driven warrior — bursty, group-friendly",
    "Smith of Kitava": "Armour-stacking warrior — durable frontline",
    "Infernalist": "Hands-off minion summoner — beginner-friendly",
    "Blood Mage": "Life-fuelled spellcaster — high risk, high burst",
    "Lich": "Chaos / energy-shield caster — strong burst",
    "Abyssal Lich": "Darkness-scaling caster — sustained chaos damage",
    "Stormweaver": "Elemental spellcaster — strong bossing",
    "Chronomancer": "Time-bending caster — spike-cast glass cannon",
    "Disciple of Varashta": "Ailment caster — control and scaling damage",
    "Witchhunter": "Crossbow generalist — flexible, anti-caster",
    "Gemling Legionnaire": "Gem-stacking shell — scales with investment",
    "Tactician": "Tactical crossbow — utility and team play",
    "Oracle": "Hybrid druid — adaptable, summon/transform flex",
    "Shaman": "Totem-and-spirit druid — elemental, summon-leaning",
}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(ROOT, "data.json")
SITEMAP_PATH = os.path.join(ROOT, "sitemap.xml")
SITE_URL = "https://tincturepoe2.com/"
SITE = SITE_URL.rstrip("/")
ECONOMY_PATH = os.path.join(ROOT, "economy.json")
HISTORY_PATH = os.path.join(ROOT, "history.json")
HISTORY_CAP = 240                       # ~10 days at hourly; append-only, deduped
LANDING_DIR = os.path.join(ROOT, "b")   # per-ascendancy SEO landing pages
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


def index_by_url(raw):
    """{leagueUrl: league_obj} from a build-index-state payload. Skips entries with a falsy
    leagueUrl (they'd collide under a None key) and warns rather than silently overwriting on a
    duplicate, so a quirk in the feed can't make a league resolve to the wrong object."""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for l in raw.get("leagueBuilds", []):
        if not isinstance(l, dict):
            continue
        url = l.get("leagueUrl")
        if not url:
            continue
        if url in out:
            print(f"[warn] duplicate leagueUrl {url!r} in feed — keeping the first")
            continue
        out[url] = l
    return out


def normalize_one(league_obj):
    """
    One poe.ninja league object -> (build rows, league total).

    A league object looks like:
        {"leagueName": "...", "leagueUrl": "...", "total": 124248,
         "statistics": [{"class": "Martial Artist", "percentage": 24.5, "trend": -1}, ...]}

    poe.ninja ranks ascendancies (its "class" field) and gives no dominant skill, so
    `skill` is left blank and the front end shows the ascendancy as the headline.
    `n` is reconstructed from the league total and each ascendancy's share. Permanent
    leagues return an empty statistics list -> we return ([], total).
    """
    # Coerce defensively (mirror percentage): a non-numeric/odd upstream total ("124,248")
    # should skip-to-0, not abort the whole run with a ValueError.
    try:
        total = int(float(league_obj.get("total") or 0))
    except (TypeError, ValueError):
        total = 0
    out = []
    for s in league_obj.get("statistics") or []:
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
        cls = ASC_TO_CLASS.get(asc, "")
        if not cls:
            # Observability: a new/renamed ascendancy a future patch adds before it's
            # mapped will still render (in "All") but won't get a class chip. Surface it
            # in the Action log instead of degrading silently.
            print(f"[warn] unmapped ascendancy {asc!r} -> class left blank (add it to ASC_TO_CLASS)")
        out.append({
            "cls": cls,
            "asc": str(asc),
            "skill": "",  # build-index-state does not expose a dominant skill
            "pop": round(pop, 1),
            "_popf": pop,  # unrounded share, used only for the largest-remainder apportionment below
            "tag": ASC_TAGS.get(asc, ""),  # editorial archetype note; "" if unknown
        })
    _apportion_n(out, total)
    for r in out:
        del r["_popf"]
    return out, total


def _apportion_n(rows, total):
    """Set each row's derived n = share x league total via LARGEST-REMAINDER rounding.

    n is DERIVED (not a measured per-ascendancy headcount; the front end labels it "~"/"est.").
    Rounding each row independently with round() biases upward, so the headcounts can sum ABOVE
    the real population — a mild inflation the honesty ethos warns against. Largest-remainder
    apportionment floors every row then hands the leftover characters to the largest fractional
    remainders, so the derived counts never sum past the population while staying share-accurate.
    When the source shares themselves sum above 100%, the exact counts are first scaled down
    proportionally to at most the population, so even the floors can't overshoot.
    """
    if not rows:
        return
    if not total:
        for r in rows:
            r["n"] = 0
        return
    exacts = [total * r["_popf"] / 100.0 for r in rows]
    # poe.ninja top-N shares can sum to >100% (overlapping categories or independent rounding).
    # Scale exacts down proportionally so they sum to at most `total` before flooring — otherwise
    # the floors alone can exceed the real population and the clamp below has no effect.
    raw_sum = sum(exacts)
    if raw_sum > total:
        scale = total / raw_sum
        exacts = [e * scale for e in exacts]
    floors = [int(e) for e in exacts]                 # int() == floor for non-negative shares
    target = min(total, round(sum(exacts)))           # never exceed the real population
    deficit = max(0, target - sum(floors))            # always < len(rows) (sum of fractions)
    order = sorted(range(len(rows)), key=lambda i: exacts[i] - floors[i], reverse=True)
    ns = floors[:]
    for i in order[:deficit]:
        ns[i] += 1
    for r, n in zip(rows, ns):
        r["n"] = n

# ----------------------------------------------------------------------------- #
# Distillation: tiers, trends, ranking — per league
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
    # .get() so a malformed/foreign previous data.json (a build row missing asc/skill) yields a
    # harmless key and just loses its baseline (delta=None) instead of crashing the whole run.
    return f"{b.get('asc', '')}|{b.get('skill', '')}".lower()


def prev_builds_for(previous, url):
    """The previous run's build rows for one league url (empty if absent / old shape)."""
    if not isinstance(previous, dict):
        return []
    for league in previous.get("leagues", []) or []:
        if league.get("url") == url:
            return league.get("builds", []) or []
    return []


def apply_trends(builds, prev_builds):
    """delta = current share - the matching share in the previous snapshot.

    Honest about history: a build with NO matching previous value (first run for this
    league, or a newly-appearing ascendancy) gets delta=None — "no baseline yet" — not
    a fabricated 0.0. Only a build with a real prior value gets a number (which CAN be
    0.0, meaning genuinely flat). The front end renders None as an empty/baseline cell
    and only shows trend arrows once some delta is actually non-zero.
    """
    prev_map = {key_of(pb): pb.get("pop") for pb in (prev_builds or [])}
    for b in builds:
        old = prev_map.get(key_of(b))
        b["delta"] = round(b["pop"] - old, 1) if old is not None else None
    return builds


def distill_league(raw_builds, prev_builds, total, meta):
    """Rank + tier + trend one league's builds and wrap with its metadata."""
    builds = [b for b in raw_builds if b.get("pop", 0) > 0]
    builds.sort(key=lambda b: b["pop"], reverse=True)
    for i, b in enumerate(builds, start=1):
        b["rank"] = i
        b["tier"] = tier_for(b["pop"])
    apply_trends(builds, prev_builds)

    ascendancies = len({b["asc"] for b in builds})
    # Prefer the source's real league population; fall back to summing shown builds
    # (the demo path has no separate total).
    characters = int(total) if total else sum(int(b.get("n", 0)) for b in builds)

    league = {
        "url": meta["url"],
        "name": meta["name"],
        "mode": meta["mode"],
        "label": meta["label"],
        "totals": {"characters": characters, "ascendancies": ascendancies},
        "builds": [
            {k: b[k] for k in ("rank", "tier", "cls", "asc", "skill", "pop", "delta", "n", "tag")}
            for b in builds
        ],
    }
    if not league["builds"]:
        league["note"] = NO_BREAKDOWN_NOTE
    return league


def curated_league(meta, total):
    """A non-ladder, hand-picked archetype list for a league poe.ninja doesn't rank.
    Builds carry no pop/delta/tier (null) so the front end renders them as a labeled
    reference list, not a ranked ledger."""
    picks = CURATED.get(meta["url"], [])
    builds = [{
        "rank": i, "tier": "", "cls": c["cls"], "asc": c["asc"],
        "skill": "", "pop": None, "delta": None, "n": None, "tag": c["tag"],
    } for i, c in enumerate(picks, start=1)]
    return {
        "url": meta["url"], "name": meta["name"], "mode": meta["mode"], "label": meta["label"],
        "curated": True,
        "note": CURATED_NOTE,
        "totals": {"characters": int(total or 0), "ascendancies": len({c["asc"] for c in picks})},
        "builds": builds,
    }


def build_payload(leagues):
    return {
        "patch": PATCH,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": 1,            # bump to 2 when the GGG ladder cross-check is on
        "default": LEAGUE_FAMILY,  # the softcore challenge league
        "leagues": leagues,
    }


BUILDS_DIR = os.path.join(ROOT, "builds")
MANIFEST_PATH = os.path.join(BUILDS_DIR, "index.json")


def write_builds_manifest():
    """Refresh builds/index.json — the slugs that have a real, loadable .build file.

    The front end fetches this first and only attempts builds/<slug>.build for listed
    slugs, so it never pays a guaranteed 404 for a pick without one. Populated from the
    committed builds/*.build files (the weekly builds.yml reconstructor writes them).
    Fails safe — a filesystem hiccup here must never break a distill run."""
    try:
        slugs = []
        if os.path.isdir(BUILDS_DIR):
            slugs = sorted(name[:-len(".build")] for name in os.listdir(BUILDS_DIR)
                           if name.endswith(".build"))
        os.makedirs(BUILDS_DIR, exist_ok=True)
        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(slugs, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"[write] {MANIFEST_PATH} — {len(slugs)} loadable build(s)")
    except OSError as e:  # noqa: BLE001
        print(f"[warn] could not write builds manifest: {e}")


def _sitemap_xml(lastmod, asc_slugs=None):
    """The sitemap XML string: the homepage + each per-ascendancy /b landing page. A JSON data file
    (data.json) is NOT a crawlable page, so it is deliberately excluded. Pure — no IO."""
    def url_block(loc, prio, freq="hourly"):
        return (f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>{lastmod}</lastmod>\n"
                f"    <changefreq>{freq}</changefreq>\n    <priority>{prio}</priority>\n  </url>\n")
    blocks = url_block(SITE_URL, "1.0")
    for slug in sorted(asc_slugs or []):
        blocks += url_block(f"{SITE_URL}b/{slug}.html", "0.6", "weekly")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + blocks + "</urlset>\n")


def write_sitemap(updated_iso, asc_slugs=None):
    """Rewrite sitemap.xml with a <lastmod> matching data.json's update day, turning the
    'refreshed hourly' claim into a verifiable crawler freshness signal. Date granularity keeps
    the file (and its commits) from churning every hour. Includes the per-ascendancy landing
    pages. Fail-safe — a hiccup never breaks a run."""
    lastmod = (updated_iso or "")[:10] or datetime.now(timezone.utc).date().isoformat()
    xml = _sitemap_xml(lastmod, asc_slugs)
    try:
        tmp = SITEMAP_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(xml)
        os.replace(tmp, SITEMAP_PATH)
        print(f"[write] {SITEMAP_PATH} — lastmod {lastmod}")
    except OSError as e:  # noqa: BLE001
        print(f"[warn] could not write sitemap: {e}")


def slugify_asc(asc):
    """Ascendancy -> the front end's blank-skill slug (matches index.html slugOf)."""
    return re.sub(r"[^a-z0-9]+", "-", (str(asc) + "-").lower()).strip("-")


def guides_schema_errors(doc):
    """Return a list of human-readable problems with a guides.json doc; [] means valid.
    The `leveling`/`levelingUnguided` keys are OPTIONAL (additive) — absent is valid."""
    errs = []
    if not isinstance(doc, dict):
        return ["guides.json is not an object"]

    def _map_errs(m, label):
        out = []
        for slug, e in m.items():
            if not isinstance(e, dict):
                out.append(f"{label}['{slug}'] is not an object"); continue
            url = e.get("url")
            if not (isinstance(url, str) and (url.startswith("http://") or url.startswith("https://"))):
                out.append(f"{label}['{slug}'] has a missing/invalid url")
            if not (isinstance(e.get("source"), str) and e.get("source").strip()):
                out.append(f"{label}['{slug}'] has a missing/empty source")
        return out

    guides = doc.get("guides")
    if not isinstance(guides, dict):
        errs.append("'guides' is missing or not an object")
        guides = {}
    errs += _map_errs(guides, "guides")
    ung = doc.get("unguided", [])
    if not isinstance(ung, list) or not all(isinstance(s, str) for s in ung):
        errs.append("'unguided' must be a list of slug strings")
        ung = [s for s in (ung if isinstance(ung, list) else []) if isinstance(s, str)]
    both = set(guides) & set(ung)
    if both:
        errs.append(f"slug(s) in both guides and unguided: {sorted(both)}")

    # leveling (optional) — same shape as guides; absent keys are valid
    lvl = doc.get("leveling")
    lvl_map = {}
    if lvl is not None:
        if not isinstance(lvl, dict):
            errs.append("'leveling' must be an object")
        else:
            lvl_map = lvl
            errs += _map_errs(lvl, "leveling")
    lung = doc.get("levelingUnguided", [])
    if not isinstance(lung, list) or not all(isinstance(s, str) for s in lung):
        errs.append("'levelingUnguided' must be a list of slug strings")
        lung = [s for s in (lung if isinstance(lung, list) else []) if isinstance(s, str)]
    lboth = set(lvl_map) & set(lung)
    if lboth:
        errs.append(f"slug(s) in both leveling and levelingUnguided: {sorted(lboth)}")
    return errs


def untriaged_guides(payload, doc):
    """Sorted slugs of live (non-curated) default-league ascendancies handled by neither
    guides nor unguided — i.e. new ascendancies that need a curation decision."""
    payload = payload if isinstance(payload, dict) else {}
    guides = (doc.get("guides") or {}) if isinstance(doc, dict) else {}
    ung = set((doc.get("unguided") or []) if isinstance(doc, dict) else [])
    handled = set(guides) | ung
    default_url = payload.get("default")
    out = set()
    for lg in payload.get("leagues", []):
        if lg.get("url") != default_url or lg.get("curated"):
            continue
        for b in lg.get("builds", []):
            asc = b.get("asc")
            if asc:
                slug = slugify_asc(asc)
                if slug not in handled:
                    out.add(slug)
    return sorted(out)


def _history_append(points, point, cap):
    """Pure: append `point` unless it duplicates the last snapshot's shares; cap the length.
    Append-only history is honest (real accumulated data) — poe.ninja's timeMachine param is
    ignored by build-index-state, so we can't backfill; history grows from now."""
    points = list(points or [])
    if points and points[-1].get("shares") == point.get("shares"):
        return points                      # unchanged since last snapshot — skip the duplicate
    points.append(point)
    return points[-cap:]


def fetch_economy():
    """Fetch the current-league currency exchange (CONFIRMED live JSON). index-state gives the
    snapshot version + the economy league's DISPLAY name (the exchange endpoint requires the
    display name, e.g. 'Runes of Aldur', NOT the url slug). Returns the raw overview, or None."""
    try:
        idx = http_get_json(INDEX_STATE_URL)
        sv = idx.get("snapshotVersions") or []
        ver = sv[0].get("version") if sv and isinstance(sv[0], dict) else None
        league_name = None
        for e in (idx.get("economyLeagues") or []):
            if isinstance(e, dict) and e.get("url") == LEAGUE_FAMILY:
                league_name = e.get("name") or e.get("displayName")
                break
        if not ver or not league_name:
            print("[economy] no version / league name in index-state — skipping")
            return None
        q = urllib.parse.urlencode({"league": league_name, "type": "Currency"}, quote_via=urllib.parse.quote)
        url = f"{POE2_API}/economy/exchange/{ver}/overview?{q}"
        data = http_get_json(url)
        print(f"[economy] {url} -> {len((data or {}).get('lines') or [])} currencies")
        return data
    except urllib.error.HTTPError as e:
        print(f"[economy] HTTP {e.code}")
    except Exception as e:  # noqa: BLE001
        print(f"[economy] {type(e).__name__}: {e}")
    return None


def _economy_payload(raw, updated):
    """Raw exchange overview -> compact economy.json: cross-rates + each currency's Divine value,
    trade volume and 7-day change. Pure (testable)."""
    core = (raw or {}).get("core") or {}
    items = {it.get("id"): it for it in ((raw or {}).get("items") or []) if isinstance(it, dict) and it.get("id")}
    currencies = []
    for l in ((raw or {}).get("lines") or []):
        if not isinstance(l, dict) or not l.get("id"):
            continue
        it = items.get(l["id"]) or {}
        currencies.append({
            "id": l["id"],
            "name": it.get("name") or l["id"],
            "divine": l.get("primaryValue"),               # value in Divine Orbs (primary reference)
            "volume": l.get("volumePrimaryValue"),
            "change7d": (l.get("sparkline") or {}).get("totalChange"),
        })
    return {
        "updated": updated,
        "league": FAMILY_NAME,
        "primary": core.get("primary"),                    # "divine"
        "secondary": core.get("secondary"),                # "chaos"
        "rates": core.get("rates") or {},                  # units per 1 divine, e.g. {"exalted":208.5,"chaos":8.55}
        "currencies": currencies,
    }


def write_economy():
    """Fetch + write economy.json (currency exchange) — independent of the build meta and fail-safe:
    a network/parse failure leaves the existing economy.json untouched. Atomic write."""
    raw = fetch_economy()
    if not raw or not raw.get("lines"):
        return
    payload = _economy_payload(raw, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    if not payload["currencies"]:
        return
    try:
        tmp = ECONOMY_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            f.write("\n")
        os.replace(tmp, ECONOMY_PATH)
        print(f"[write] {ECONOMY_PATH} — {len(payload['currencies'])} currencies")
    except OSError as e:  # noqa: BLE001
        print(f"[warn] could not write economy: {e}")


def write_history(payload):
    """Append the DEFAULT (SC challenge) league's ascendancy shares to history.json so the front
    end can draw a real multi-day rise/fall chart. Lean (one league, deduped, capped), atomic,
    fail-safe — never breaks a run."""
    try:
        leagues = {l.get("url"): l for l in payload.get("leagues", [])}
        dl = leagues.get(payload.get("default")) or (payload.get("leagues") or [None])[0]
        if not dl or dl.get("curated"):
            return
        shares = {b["asc"]: b["pop"] for b in dl.get("builds", []) if b.get("pop") is not None}
        if not shares:
            return
        point = {"t": payload.get("updated"),
                 "total": (dl.get("totals") or {}).get("characters"),
                 "shares": shares}
        hist = {}
        if os.path.exists(HISTORY_PATH):
            try:
                with open(HISTORY_PATH, encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    hist = loaded
            except Exception:  # noqa: BLE001 — a corrupt prior file just starts fresh
                hist = {}
        pts = _history_append(hist.get("points") if isinstance(hist.get("points"), list) else [], point, HISTORY_CAP)
        out = {"league": dl.get("url"), "updated": payload.get("updated"), "points": pts}
        tmp = HISTORY_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
            f.write("\n")
        os.replace(tmp, HISTORY_PATH)
        print(f"[write] {HISTORY_PATH} — {len(pts)} points")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] could not write history: {e}")


def _esc(s):
    return _html.escape(str(s), quote=True)


WEAPON_DOMINANT_PCT = 30   # below this share there's no single "build weapon" worth naming on a /b page


def _dominant_weapon(entry):
    """The ascendancy's weapon to name on its /b page — only a clearly dominant, classified one.
    None when the plurality is weak (< WEAPON_DOMINANT_PCT) or the weaponmode is unclassified ('Unknown')."""
    w = (entry.get("weapons") or [{}])[0]
    name = w.get("name")
    if not name or "Unknown" in name or (w.get("pct") or 0) < WEAPON_DOMINANT_PCT:
        return None
    return name


def landing_html(asc, cls, tag, skills=None, uniques=None, notables=None, weapon=None, siblings=None):
    """A real-content (not doorway) SEO page for one ascendancy: class, playstyle, common skills,
    signature uniques, key notables, a self-canonical, JSON-LD, and a link into the live SPA deep
    link. Stable content (no volatile share) so it doesn't churn hourly. Only called for
    ascendancies present in a NON-curated (live) league."""
    slug = slugify_asc(asc)
    url = f"{SITE}/b/{slug}.html"
    deep = f"{SITE}/#asc={slug}"
    title = f"{asc} build meta — Path of Exile 2 (Runes of Aldur) | Tincture"
    wbit = f" Most-played weapon: {weapon}." if weapon else ""
    desc = (f"{asc}" + (f" ({cls})" if cls else "") + f" in Path of Exile 2 {PATCH} — "
            + (tag or "a current ladder ascendancy") + "." + wbit
            + " See its live ladder share, popular skills and uniques, and a loadable build on Tincture.")
    ld = json.dumps({
        "@context": "https://schema.org", "@type": "WebPage", "name": title, "description": desc,
        "url": url, "isPartOf": {"@type": "WebSite", "name": "Tincture", "url": SITE + "/"},
        "about": {"@type": "Thing", "name": f"{asc} (Path of Exile 2 ascendancy)"},
    }, ensure_ascii=False).replace("<", "\\u003c")   # neutralize any literal </script> in upstream names
    def ul(heading, items):
        items = [i for i in (items or []) if i][:6]
        return ("<h2>" + heading + "</h2>\n<ul>" + "".join(f"<li>{_esc(i)}</li>" for i in items) + "</ul>") if items else ""
    def sib_nav(sibs):
        # internal links to every other landing page (relative siblings in /b/), so the SEO pages
        # form a connected cluster rather than only being reachable from the SPA + sitemap.
        items = [f'<a href="{_esc(s)}.html" style="color:#c8a24a;text-decoration:none">{_esc(name)}</a>'
                 for s, name in (sibs or []) if s != slug]
        if not items:
            return ""
        return ('<nav class="b-siblings" aria-label="Other ascendancies" style="margin-top:32px;'
                'padding-top:16px;border-top:1px solid #2a2018;font-size:14px;line-height:2.0;color:#877a62">'
                '<b style="color:#a8946a">Other ascendancies:</b> ' + " &middot; ".join(items) + '</nav>')
    parts = [
        "<!DOCTYPE html>", '<html lang="en"><head>', '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        # Tighter CSP than the SPA: these pages have no executable script (the ld+json is a data
        # block, unaffected by script-src), no external resources, only inline style attributes and
        # the system font. So: nothing loads except same-origin images (favicon) and inline styles.
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; base-uri 'self'; form-action 'none'\">",
        f"<title>{_esc(title)}</title>",
        f'<meta name="description" content="{_esc(desc)}">',
        f'<link rel="canonical" href="{_esc(url)}">',
        '<meta name="robots" content="index,follow">',
        f'<meta property="og:title" content="{_esc(title)}">',
        f'<meta property="og:description" content="{_esc(desc)}">',
        f'<meta property="og:url" content="{_esc(url)}">',
        f'<meta property="og:image" content="{SITE}/docs/og.png">',
        '<meta property="og:image:type" content="image/png">',
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{_esc(title)}">',
        f'<meta name="twitter:description" content="{_esc(desc)}">',
        f'<meta name="twitter:image" content="{SITE}/docs/og.png">',
        '<meta property="og:type" content="article">',
        '<meta name="theme-color" content="#14100b">',
        '<link rel="icon" type="image/svg+xml" href="/favicon.svg">',
        f'<script type="application/ld+json">{ld}</script>',
        '</head>',
        '<body style="font-family:Georgia,serif;max-width:680px;margin:40px auto;padding:0 18px;'
        'background:#14100b;color:#ece3d0;line-height:1.65">',
        f'<p><a href="{SITE}/" style="color:#c8a24a;text-decoration:none">&#8592; Tincture</a> '
        '&middot; the Path of Exile&nbsp;2 build meta, distilled</p>',
        f'<h1 style="color:#e6c47a">{_esc(asc)}</h1>',
        f"<p><b>Class:</b> {_esc(cls or 'unknown')} &middot; Path of Exile&nbsp;2 {PATCH} (Runes of Aldur)"
        + (f" &middot; <b>{_esc(weapon)}</b>" if weapon else "") + "</p>",
        (f"<p><i>{_esc(tag)}</i></p>" if tag else ""),
        ul("Commonly plays", skills),
        ul("Signature uniques", uniques),
        ul("Key passive notables", notables),
        f'<p style="margin-top:26px"><a href="{_esc(deep)}" style="color:#5b8a7e;font-size:18px">'
        f"See the live {_esc(asc)} meta &mdash; ladder share, trend, and a loadable build on Tincture &#8594;</a></p>",
        '<p style="color:#877a62;font-size:13px;margin-top:34px">Tincture is an independent fan project, '
        'not affiliated with or endorsed by Grinding Gear Games. Build data is reconstructed from the '
        'public poe.ninja ladder and credited to its source character.</p>',
        sib_nav(siblings),
        "</body></html>",
    ]
    return "\n".join(p for p in parts if p) + "\n"


def _landing_ascendancies(payload):
    """asc -> (cls, tag) for every ascendancy in a NON-curated (live ladder) league. Curated picks
    carry no live share/trend, so they get no landing page — a 'live ladder share' page for a
    curated-only ascendancy would be false and its deep link would land on a null curated row."""
    info = {}
    for l in payload.get("leagues", []):
        if l.get("curated"):
            continue
        for b in l.get("builds", []):
            a = b.get("asc")
            if a and a not in info:
                info[a] = (b.get("cls") or "", b.get("tag") or ASC_TAGS.get(a, ""))
    return info


def generate_landing_pages(payload):
    """Emit one real-content static page per ascendancy under /b/ for long-tail SEO the SPA can't
    rank for. Content from data.json (class, tag) + meta-detail.json (common skills) when present.
    Returns the slug list (for the sitemap). Fail-safe."""
    try:
        info = _landing_ascendancies(payload)
        meta_by = {}
        mdp = os.path.join(ROOT, "meta-detail.json")
        if os.path.exists(mdp):
            try:
                with open(mdp, encoding="utf-8") as f:
                    md = json.load(f)
                for _slug, e in (md.get("byAsc") or {}).items():
                    if e.get("asc"):
                        meta_by[e["asc"]] = e
            except Exception:  # noqa: BLE001
                pass
        names = lambda arr: [x.get("name") for x in (arr or []) if isinstance(x, dict) and x.get("name")]
        os.makedirs(LANDING_DIR, exist_ok=True)
        siblings = sorted((slugify_asc(a), a) for a in info)   # (slug, asc) for cross-linking every page
        slugs = []
        for asc, (cls, tag) in sorted(info.items()):
            slug = slugify_asc(asc)
            e = meta_by.get(asc) or {}
            weapon = _dominant_weapon(e)
            page = landing_html(asc, cls, tag, names(e.get("skills")), names(e.get("uniques")), names(e.get("notables")), weapon, siblings=siblings)
            tmp = os.path.join(LANDING_DIR, slug + ".html.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(page)
            os.replace(tmp, os.path.join(LANDING_DIR, slug + ".html"))
            slugs.append(slug)
        # prune landing pages whose ascendancy dropped out of the live leagues (e.g. a curated-only
        # Infernalist/Invoker) so a stale page can't keep promising "live ladder share".
        keep = set(slugs)
        for fn in os.listdir(LANDING_DIR):
            if fn.endswith(".html") and fn[:-len(".html")] not in keep:
                try:
                    os.remove(os.path.join(LANDING_DIR, fn))
                except OSError:
                    pass
        # Manifest of slugs that have a landing page, so the SPA links to /b/<slug>.html only
        # when the page actually exists (a pruned/uncovered ascendancy gets no dead link).
        try:
            mtmp = os.path.join(LANDING_DIR, "index.json.tmp")
            with open(mtmp, "w", encoding="utf-8") as f:
                json.dump({"updated": payload.get("updated"), "slugs": sorted(slugs)}, f, separators=(",", ":"))
            os.replace(mtmp, os.path.join(LANDING_DIR, "index.json"))
        except Exception as e:  # noqa: BLE001
            print(f"[warn] could not write {LANDING_DIR}/index.json: {e}")
        print(f"[write] {LANDING_DIR} — {len(slugs)} landing pages")
        return slugs
    except Exception as e:  # noqa: BLE001
        print(f"[warn] could not write landing pages: {e}")
        return []


def write_data(payload):
    # Atomic write: serialize to a temp file then os.replace() so a crash mid-write (disk full,
    # encoding error on an exotic upstream string, interrupted process) can NEVER truncate the
    # live data.json the deployed site reads. The replace is atomic on the same filesystem.
    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, OUT_PATH)
    leagues = payload.get("leagues", [])
    nb = sum(len(l.get("builds", [])) for l in leagues)
    print(f"[write] {OUT_PATH} — {len(leagues)} leagues, {nb} builds total")
    write_builds_manifest()
    slugs = generate_landing_pages(payload)
    write_sitemap(payload.get("updated"), slugs)
    write_history(payload)


def warn_missing_guides(payload):
    """Non-blocking: log new/un-triaged ascendancies + patch drift for guides.json. Never raises."""
    try:
        path = os.path.join(ROOT, "guides.json")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        for e in guides_schema_errors(doc):
            print(f"[warn] guides.json: {e}", file=sys.stderr)
        missing = untriaged_guides(payload, doc)
        for slug in missing:
            print(f"[warn] ascendancy '{slug}' is in the meta but has no guide "
                  f"(add it to guides.json or its unguided list)", file=sys.stderr)
        gp, dp = doc.get("patch"), payload.get("patch")
        if gp and dp and gp != dp:
            print(f"[warn] guides.json patch {gp} is behind data.json patch {dp} — re-vet the guides",
                  file=sys.stderr)
        return missing
    except Exception as e:  # noqa: BLE001
        print(f"[warn] could not check guides.json: {e}", file=sys.stderr)
        return []


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
    targets = {m["url"] for m in TARGET_LEAGUES}
    print(f"  OK — {len(leagues)} leagues returned (we surface {len(targets)}):")
    for l in leagues:
        mark = "  <-- surfaced" if l.get("leagueUrl") in targets else ""
        print(f"    {str(l.get('leagueUrl')):<22} {str(l.get('leagueName')):<26} "
              f"total={str(l.get('total')):>7}  ascendancies={len(l.get('statistics') or [])}{mark}")


def run_demo():
    print("DEMO mode — no network. Running the full pipeline on sample data.\n")
    previous = load_previous()
    meta = {"url": LEAGUE_FAMILY, "name": FAMILY_NAME, "mode": "Softcore",
            "label": f"{FAMILY_NAME} · Softcore"}
    sc = distill_league([dict(b) for b in SAMPLE_BUILDS],
                        prev_builds_for(previous, LEAGUE_FAMILY), total=None, meta=meta)
    payload = build_payload([sc])
    write_data(payload)
    print("\nTop of the ledger:")
    for b in sc["builds"][:5]:
        d = b["delta"]
        # delta is None when there's no matching previous snapshot (the honest "no
        # baseline yet" state) — render it safely rather than comparing None to int.
        if d is None:
            trend = "baseline"
        elif d > 0:
            trend = f"▲{d:.1f}"
        elif d < 0:
            trend = f"▼{abs(d):.1f}"
        else:
            trend = "— 0.0"
        print(f"  {b['rank']:>2}. [{b['tier']}] {b['asc']:<20} {b['skill']:<18} "
              f"{b['pop']:>5.1f}%  {trend}")


def run_live():
    print(f"LIVE run — distilling {FAMILY_NAME} variants + Standard ({PATCH})\n")
    previous = load_previous()
    write_economy()                 # currency exchange — independent of the build meta, fail-safe
    raw = fetch_poeninja_builds()
    if not isinstance(raw, dict):
        print("\n[live] no data this run — keeping the existing data.json. Exiting 0.")
        return 0

    feed = index_by_url(raw)
    leagues_out = []
    for meta in TARGET_LEAGUES:
        league_obj = feed.get(meta["url"])
        if league_obj is None:
            print(f"[live] {meta['url']} not in feed — skipping")
            continue
        rows, total = normalize_one(league_obj)
        if rows:
            league = distill_league(rows, prev_builds_for(previous, meta["url"]), total, meta)
        elif meta["url"] in CURATED:
            league = curated_league(meta, total)
        else:
            league = distill_league([], prev_builds_for(previous, meta["url"]), total, meta)
        kind = "curated" if league.get("curated") else "builds"
        print(f"[live] {meta['label']:<28} {len(league['builds']):>2} {kind}, "
              f"{league['totals']['characters']:>7,} characters")
        leagues_out.append(league)

    if not any(l["builds"] for l in leagues_out if not l.get("curated")):
        print("\n[live] no ranked league had usable build data — keeping the existing data.json. "
              "Exiting 0 so the site stays up.")
        return 0

    payload = build_payload(leagues_out)
    write_data(payload)
    warn_missing_guides(payload)
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

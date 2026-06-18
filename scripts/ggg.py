#!/usr/bin/env python3
"""
ggg.py — pull a public ladder character from GGG's official API and turn it into a
valid `.build` (via buildfile.serialize_build). This is the "real Decant content" path.

HONEST STATE (read before trusting this):
  * I wrote this against GGG's documented API (https://www.pathofexile.com/developer/docs)
    but COULD NOT run it against live GGG servers from the build sandbox. The HTTP/OAuth
    plumbing, rate-limit handling, item->text mapping, and serialization are complete and
    tested offline (`--demo`). Two mappings genuinely need a real response to finalize:
      1. passive hash -> .build slug  (needs the PoE2 passive-tree JSON; see map_passives)
      2. gem -> Metadata/Items/Gems/... path (PoE2 skill/gem shape unconfirmed; see extract_skills)
    Run `python scripts/ggg.py --probe <account> <character>` on a networked machine to
    dump a real character; paste the shape back and these two get finished in minutes.

SETUP (required for live use):
  * Register a GGG API client (OAuth) — see the developer docs. Confidential/service
    client with ladder + character scopes for an unattended job.
  * Export credentials before running live:
      GGG_CLIENT_ID=...  GGG_CLIENT_SECRET=...  python scripts/ggg.py build <account> <character>
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

# buildfile lives alongside this file
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import buildfile  # noqa: E402

# --------------------------------------------------------------------------- #
# Config  (URLs/scopes per the GGG developer docs — confirm against your client)
# --------------------------------------------------------------------------- #
OAUTH_TOKEN_URL = "https://www.pathofexile.com/oauth/token"
API_BASE = "https://api.pathofexile.com"
LEAGUE = "Runes of Aldur"
REALM = "poe2"  # PoE2 realm; confirm the exact value the API expects

# GGG requires a descriptive User-Agent: "OAuth {clientid}/{version} (contact: {email})"
USER_AGENT = "OAuth tincture/0.1 (contact: ryan.duke360@gmail.com)"

GGG_CLIENT_ID = os.environ.get("GGG_CLIENT_ID")
GGG_CLIENT_SECRET = os.environ.get("GGG_CLIENT_SECRET")

# GGG item inventoryId -> our .build inventory_id  (see SCHEMA.md vocabulary)
SLOT_MAP = {
    "Weapon": "Weapon1", "Weapon2": "Weapon2", "Offhand": "Weapon2", "Offhand2": "Weapon2",
    "Helm": "Helm1", "BodyArmour": "BodyArmour1", "Gloves": "Gloves1", "Boots": "Boots1",
    "Belt": "Belt1", "Amulet": "Amulet1", "Ring": "Ring1", "Ring2": "Ring2",
    "Flask": "Flask1", "Charm": "Charm1",
}
FRAME_UNIQUE = 3
FRAME_GEM = 4


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #
class GggClient:
    def __init__(self, client_id=GGG_CLIENT_ID, client_secret=GGG_CLIENT_SECRET):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = None

    def _auth(self):
        if self._token:
            return self._token
        if not (self.client_id and self.client_secret):
            raise RuntimeError("Set GGG_CLIENT_ID and GGG_CLIENT_SECRET (register a client in the GGG developer docs).")
        body = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "service:leagues service:psapi",  # confirm the scopes your client is granted
        }).encode()
        req = urllib.request.Request(OAUTH_TOKEN_URL, data=body,
                                     headers={"User-Agent": USER_AGENT,
                                              "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=20) as r:
            tok = json.loads(r.read().decode())
        self._token = tok["access_token"]
        return self._token

    def _get(self, path, params=None):
        url = API_BASE + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Authorization": f"Bearer {self._auth()}",
            "Accept": "application/json",
        })
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=25) as r:
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                if e.code == 429:  # rate limited — respect Retry-After and back off
                    wait = int(e.headers.get("Retry-After", "10"))
                    print(f"[ggg] 429, waiting {wait}s")
                    time.sleep(wait)
                    continue
                raise
        raise RuntimeError(f"giving up on {path} after repeated rate limits")

    # --- endpoints (confirm exact paths for PoE2 against the docs) ---
    def ladder(self, league=LEAGUE, limit=50):
        # top of the league ladder; entries include character + account
        return self._get(f"/league/{urllib.parse.quote(league)}/ladder",
                         {"realm": REALM, "limit": limit})

    def character(self, account, character):
        # full character: equipment, passives, skills (public profiles only)
        return self._get(f"/character/{urllib.parse.quote(account)}/{urllib.parse.quote(character)}",
                         {"realm": REALM})


# --------------------------------------------------------------------------- #
# Mapping: GGG character JSON -> buildfile components
# --------------------------------------------------------------------------- #
def _mods(item):
    out = []
    for key in ("implicitMods", "runeMods", "explicitMods"):
        out.extend(item.get(key, []) or [])
    return out


def map_items(char):
    """COMPLETE: GGG items -> .build inventory_slots (rare = text, unique = name)."""
    items = char.get("items") or char.get("equipment") or []
    slots = []
    for it in items:
        slot = SLOT_MAP.get(it.get("inventoryId"))
        if not slot:
            continue  # sockets/jewels/flasks-beyond-1/etc. — skip for now
        if it.get("frameType") == FRAME_UNIQUE:
            slots.append(buildfile.make_item(it.get("name") or it.get("typeLine", "Unique"),
                                             slot=slot, unique=True))
        else:
            base = it.get("baseType") or it.get("typeLine") or it.get("name") or "Item"
            slots.append(buildfile.make_item(base, slot=slot, mods=_mods(it)))
    return slots


def extract_skills(char):
    """
    SCAFFOLD: pull skill gems + supports.

    PoE1 sockets gems inside items (item.socketedItems, frameType 4). PoE2's skill/gem
    system is different and the exact field is UNCONFIRMED here — finish this once
    `--probe` shows where gems live and what names/metadata are exposed. The
    name->metadata mapping (buildfile.gem_path) also needs checking against the real
    `Metadata/Items/Gem(s)/...` strings (note the singular/plural inconsistency).
    """
    skills = []
    for it in (char.get("items") or []):
        for soc in (it.get("socketedItems") or []):
            if soc.get("frameType") != FRAME_GEM:
                continue
            name = (soc.get("typeLine") or soc.get("baseType") or "").replace(" ", "")
            if not name:
                continue
            is_support = "support" in (soc.get("typeLine") or "").lower()
            if is_support and skills:
                skills[-1].setdefault("support_skills", []).append(
                    {"id": buildfile.gem_path(name, support=True), "level_interval": [1, 100]})
            elif not is_support:
                skills.append(buildfile.make_skill(name))
    return skills  # likely empty/partial for PoE2 until confirmed


def map_passives(char, slug_map=None):
    """
    SCAFFOLD: GGG returns allocated nodes as hashes; the `.build` format uses named
    slugs (e.g. 'attack_speed25'). Provide slug_map = {node_hash: slug} built from the
    PoE2 passive-tree JSON to translate. Without it we can't emit passives (and the
    file won't be loadable), so this returns [] and warns.
    """
    hashes = (char.get("passives") or {}).get("hashes") or char.get("hashes") or []
    if not slug_map:
        if hashes:
            print(f"[ggg] {len(hashes)} passive nodes found but no slug_map — passives skipped. "
                  f"Provide the PoE2 tree map to translate hashes -> slugs.")
        return []
    return [slug_map[h] for h in hashes if h in slug_map]


def character_to_build(char, *, author="Tincture", name=None, slug_map=None):
    asc = char.get("ascendancy") or (char.get("character") or {}).get("class") or char.get("class") or ""
    return buildfile.serialize_build(
        author=author,
        ascendancy=asc,  # mapped via buildfile.ASCENDANCY_CODES when a name is known
        name=name or char.get("name") or f"{asc} build",
        items=map_items(char),
        passives=map_passives(char, slug_map),
        skills=extract_skills(char),
    )


def build_for_character(account, character, out_path=None, slug_map=None):
    client = GggClient()
    raw = client.character(account, character)
    build = character_to_build(raw, name=f"{character} — via Tincture", slug_map=slug_map)
    errs = buildfile.validate(build)
    if errs:
        print("[ggg] WARNING — serialized build has issues:", errs)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(buildfile.to_text(build))
        print(f"[ggg] wrote {out_path}")
    return build


# --------------------------------------------------------------------------- #
# Modes
# --------------------------------------------------------------------------- #
SAMPLE_CHAR = {
    "name": "DemoExile",
    "ascendancy": "Martial Artist",
    "items": [
        {"inventoryId": "Weapon", "frameType": 2, "baseType": "Sinister Quarterstaff",
         "explicitMods": ["Adds 130 to 198 Fire Damage", "+4.4% to Critical Hit Chance"]},
        {"inventoryId": "Boots", "frameType": 2, "baseType": "Wrapped Sandals",
         "implicitMods": ["10% increased Movement Speed"]},
        {"inventoryId": "Belt", "frameType": 3, "name": "Shavronne's Satchel"},
    ],
    "passives": {"hashes": [101, 202, 303]},
}


def run_demo():
    print("DEMO — no network. Mapping a synthetic character through to a .build.\n")
    build = character_to_build(SAMPLE_CHAR, name="Whirling Assault — demo")
    errs = buildfile.validate(build)
    print("ascendancy code :", build["ascendancy"])
    print("inventory slots :", len(build["inventory_slots"]),
          "(", ", ".join(s["inventory_id"] for s in build["inventory_slots"]), ")")
    print("passives        :", len(build["passives"]), "(needs tree slug_map — see warning above)")
    print("validate()      :", "OK" if not errs else errs)
    print("\nsample output:\n", json.dumps(build, indent=2)[:700])


def run_probe(account, character):
    raw = GggClient().character(account, character)
    print("Top-level keys:", list(raw.keys()))
    print(json.dumps(raw, indent=2)[:2000])


def main():
    args = sys.argv[1:]
    if args and args[0] == "--demo":
        return run_demo()
    if args and args[0] == "--probe" and len(args) == 3:
        return run_probe(args[1], args[2])
    if len(args) >= 3 and args[0] == "build":
        out = args[3] if len(args) > 3 else None
        build_for_character(args[1], args[2], out_path=out)
        return
    print(__doc__)


if __name__ == "__main__":
    main()

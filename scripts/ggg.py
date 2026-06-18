#!/usr/bin/env python3
"""
ggg.py — talk to GGG's OFFICIAL Path of Exile 2 API. Two honest uses, one dead end.

  1. LADDER CROSS-CHECK (works unattended). GET /league/<league>/ladder?realm=poe2 with a
     service:leagues:ladder token (client_credentials, confidential client). An OFFICIAL
     second source for ascendancy/class shares to cross-check poe.ninja. BUT each ladder
     entry is SUMMARY ONLY — rank, account, and a minimal character {name, level, class}.
     It carries NO passives/equipment/skills, so it CANNOT build a loadable .build.
     (Open question to confirm live: whether the entry `class` is the full ascendancy or
     only the base class.)

  2. DECANT YOUR OWN CHARACTER (works with per-user consent). GET /character/poe2/<name>
     with an account:characters token (authorization_code + PKCE). Returns the character
     WITH passives + equipment, which `treedata.slug_map()` turns into real .build slugs ->
     a loadable .build. The catch: account:characters is SELF-ONLY — it reads only the
     consenting account's own characters, never an arbitrary public player. So this powers
     "export MY build", not "decant any ladder player's build".

  DEAD END: there is NO GGG endpoint that returns an arbitrary public ladder character's
  passives/equipment. The aggregate site meta therefore stays an honest ascendancy
  template; loadable Decant is a per-user, self-character feature.

Auth (per https://www.pathofexile.com/developer/docs):
  * Register a client by emailing oauth@grindinggear.com — see docs/ggg-oauth-application.md.
    GGG immediately rejects low-effort/LLM-generated applications; write it yourself.
  * Service token (ladder): confidential client + secret, grant=client_credentials,
    scope=service:leagues:ladder. Provide GGG_CLIENT_ID / GGG_CLIENT_SECRET.
  * User token (own character): authorization_code + PKCE, scope=account:characters. The
    user consents in a browser at https://www.pathofexile.com/oauth/authorize; the access
    token is per-user. Provide it via GGG_USER_TOKEN. (This module does not run the
    interactive consent dance — that needs your registered HTTPS/local redirect URI.)
  * Every request needs User-Agent: "OAuth {clientId}/{version} (contact: {email})".

Offline: `python scripts/ggg.py --demo` maps a synthetic character through to a real .build.
Untested against live GGG servers from this sandbox — the shapes follow the current docs;
run `--ladder` / `--character` on a networked machine with a registered client to confirm.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

# buildfile + treedata live alongside this file
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import buildfile  # noqa: E402

# --------------------------------------------------------------------------- #
# Config (confirmed against the GGG developer docs, 2026-06)
# --------------------------------------------------------------------------- #
OAUTH_TOKEN_URL = "https://www.pathofexile.com/oauth/token"
OAUTH_AUTHORIZE_URL = "https://www.pathofexile.com/oauth/authorize"  # user-consent (PKCE)
API_BASE = "https://api.pathofexile.com"
REALM = "poe2"
LEAGUE = "Runes of Aldur"
VERSION = "0.5.0"
CONTACT = "ryan.duke360@gmail.com"

GGG_CLIENT_ID = os.environ.get("GGG_CLIENT_ID", "tincture")
GGG_CLIENT_SECRET = os.environ.get("GGG_CLIENT_SECRET")   # confidential client (ladder)
GGG_USER_TOKEN = os.environ.get("GGG_USER_TOKEN")         # account:characters (own character)

# GGG requires this exact shape: "OAuth {clientid}/{version} (contact: {email})"
USER_AGENT = f"OAuth {GGG_CLIENT_ID}/{VERSION} (contact: {CONTACT})"

# GGG item inventoryId -> our .build inventory_id (see SCHEMA.md vocabulary)
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
def _note_rate_limits(headers):
    """Surface GGG's DYNAMIC rate-limit state — read the headers, never hardcode limits."""
    rules = headers.get("X-Rate-Limit-Rules")
    if not rules:
        return
    for rule in (r.strip() for r in rules.split(",") if r.strip()):
        state = headers.get(f"X-Rate-Limit-{rule}-State")
        if state:
            print(f"[ggg] rate {rule}: {state}", file=sys.stderr)


class GggClient:
    def __init__(self, client_id=GGG_CLIENT_ID, client_secret=GGG_CLIENT_SECRET,
                 user_token=GGG_USER_TOKEN):
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_token = user_token
        self._service_token = None

    def service_token(self):
        """client_credentials token for service:* scopes (the ladder). Confidential client."""
        if self._service_token:
            return self._service_token
        if not (self.client_id and self.client_secret):
            raise RuntimeError("Set GGG_CLIENT_ID and GGG_CLIENT_SECRET — register a "
                               "confidential client (see docs/ggg-oauth-application.md).")
        body = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "service:leagues:ladder",
        }).encode()
        req = urllib.request.Request(OAUTH_TOKEN_URL, data=body, headers={
            "User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=20) as r:
            self._service_token = json.loads(r.read().decode())["access_token"]
        return self._service_token

    def _get(self, path, token, params=None):
        url = API_BASE + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        })
        for _ in range(4):
            try:
                with urllib.request.urlopen(req, timeout=25) as r:
                    _note_rate_limits(r.headers)
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                if e.code == 429:  # respect Retry-After and back off
                    wait = int(e.headers.get("Retry-After", "10"))
                    print(f"[ggg] 429 rate-limited, waiting {wait}s", file=sys.stderr)
                    time.sleep(wait)
                    continue
                raise
        raise RuntimeError(f"giving up on {path} after repeated rate limits")

    # --- endpoints (PoE2 realm) ---
    def ladder(self, league=LEAGUE, limit=200, offset=0):
        """Official PoE2 ladder (service token). SUMMARY entries only — no build content."""
        return self._get(f"/league/{urllib.parse.quote(league)}/ladder", self.service_token(),
                         {"realm": REALM, "limit": limit, "offset": offset})

    def my_characters(self):
        """The consenting account's own PoE2 characters (summaries). Needs GGG_USER_TOKEN."""
        return self._get(f"/character/{REALM}", self._require_user())

    def character(self, name):
        """The consenting account's OWN PoE2 character WITH passives + equipment.
        account:characters is SELF-ONLY — it cannot read an arbitrary public player."""
        return self._get(f"/character/{REALM}/{urllib.parse.quote(name)}", self._require_user())

    def _require_user(self):
        if not self.user_token:
            raise RuntimeError("Set GGG_USER_TOKEN — an account:characters access token from "
                               "the user-consent (authorization_code + PKCE) flow.")
        return self.user_token


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
    items = char.get("equipment") or char.get("items") or []
    slots = []
    for it in items:
        slot = SLOT_MAP.get(it.get("inventoryId"))
        if not slot:
            continue  # sockets/jewels/extra flasks/etc. — skip for now
        if it.get("frameType") == FRAME_UNIQUE:
            slots.append(buildfile.make_item(it.get("name") or it.get("typeLine", "Unique"),
                                             slot=slot, unique=True))
        else:
            base = it.get("baseType") or it.get("typeLine") or it.get("name") or "Item"
            slots.append(buildfile.make_item(base, slot=slot, mods=_mods(it)))
    return slots


def extract_skills(char):
    """
    SCAFFOLD: pull skill gems + supports. PoE2's gem system differs from PoE1 and the
    exact `skills` shape is UNCONFIRMED here — finish once a live `--character` response
    shows where gems live and what metadata is exposed (also verify buildfile.gem_path
    against the real Metadata/Items/Gem(s)/... strings, note the singular/plural quirk).
    """
    skills = []
    for it in (char.get("equipment") or char.get("items") or []):
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
    return skills  # likely partial for PoE2 until confirmed live


def map_passives(char, slug_map=None):
    """GGG returns allocated passives as NUMERIC node hashes; the .build format uses string
    slugs (e.g. 'attack_speed25'). treedata.slug_map() (from GGG's public tree export) is
    the translation. Pass slug_map explicitly (offline), or leave None to fetch the export.
    Without a map we cannot emit passives (file won't be loadable) — so we return [] and
    warn, never fabricate."""
    hashes = (char.get("passives") or {}).get("hashes") or char.get("hashes") or []
    if not hashes:
        return []
    if slug_map is None:
        try:
            import treedata
            slug_map = treedata.slug_map(treedata.load_export())
        except Exception as e:  # noqa: BLE001
            print(f"[ggg] no tree slug map ({type(e).__name__}: {e}); passives skipped — "
                  f"file won't be loadable.", file=sys.stderr)
            return []
    import treedata
    slugs = treedata.hashes_to_slugs(hashes, slug_map)
    if len(slugs) < len(hashes):
        print(f"[ggg] {len(hashes) - len(slugs)} of {len(hashes)} passive ids absent from the "
              f"tree export (version mismatch?) — dropped, not invented.", file=sys.stderr)
    return slugs


def character_to_build(char, *, author="Tincture", name=None, slug_map=None):
    # PoE2 character `class` is expected to carry the ascendancy display name (e.g.
    # "Martial Artist"); serialize_build maps it to the .build code and REFUSES an unknown
    # one, so a base-class-only value would correctly raise rather than ship unloadable.
    asc = (char.get("class") or char.get("ascendancy")
           or (char.get("character") or {}).get("class") or "")
    return buildfile.serialize_build(
        author=author,
        ascendancy=asc,
        name=name or char.get("name") or f"{asc} build",
        items=map_items(char),
        passives=map_passives(char, slug_map),
        skills=extract_skills(char),
    )


def build_for_character(name, out_path=None, slug_map=None):
    """Fetch the consenting user's own character and serialize it to a .build."""
    raw = GggClient().character(name)
    build = character_to_build(raw, name=f"{name} — via Tincture", slug_map=slug_map)
    errs = buildfile.validate(build)
    if errs:
        print("[ggg] WARNING — serialized build has issues:", errs, file=sys.stderr)
    elif not buildfile.is_loadable(build):
        print("[ggg] NOTE — valid but not loadable (needs a confirmed ascendancy + passives).",
              file=sys.stderr)
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
    "class": "Martial Artist",
    "equipment": [
        {"inventoryId": "Weapon", "frameType": 2, "baseType": "Sinister Quarterstaff",
         "explicitMods": ["Adds 130 to 198 Fire Damage", "+4.4% to Critical Hit Chance"]},
        {"inventoryId": "Boots", "frameType": 2, "baseType": "Wrapped Sandals",
         "implicitMods": ["10% increased Movement Speed"]},
        {"inventoryId": "Belt", "frameType": 3, "name": "Shavronne's Satchel"},
    ],
    "passives": {"hashes": [101, 202, 303]},
}
# offline demo slug map so --demo never touches the network
DEMO_SLUG_MAP = {101: "strength18", 202: "attack_speed25", 303: "lightning14"}


def run_demo():
    print("DEMO — no network. Mapping a synthetic character through to a loadable .build.\n")
    build = character_to_build(SAMPLE_CHAR, name="Whirling Assault — demo", slug_map=DEMO_SLUG_MAP)
    errs = buildfile.validate(build)
    print("ascendancy code :", build["ascendancy"], "(Martial Artist -> Monk1)")
    print("inventory slots :", len(build["inventory_slots"]),
          "(", ", ".join(s["inventory_id"] for s in build["inventory_slots"]), ")")
    print("passives        :", len(build["passives"]), "->", build["passives"])
    print("validate()      :", "OK" if not errs else errs)
    print("is_loadable()   :", buildfile.is_loadable(build))
    print("\nsample output:\n", json.dumps(build, indent=2)[:700])


def run_ladder(league=LEAGUE):
    data = GggClient().ladder(league=league, limit=20)
    entries = (data.get("ladder") or data).get("entries", []) if isinstance(data, dict) else []
    print(f"Top of {league} (PoE2 ladder — summary only, no build content):")
    for e in entries[:20]:
        c = e.get("character", {})
        print(f"  {e.get('rank'):>3}. {c.get('name','?'):<24} L{c.get('level','?'):<3} {c.get('class','?')}")


def run_character(name):
    raw = GggClient().character(name)
    print("Top-level keys:", list(raw.keys()))
    print(json.dumps(raw, indent=2)[:2000])


def main():
    args = sys.argv[1:]
    if args and args[0] == "--demo":
        return run_demo()
    if args and args[0] == "--ladder":
        return run_ladder(args[1] if len(args) > 1 else LEAGUE)
    if args and args[0] == "--character" and len(args) >= 2:
        return run_character(args[1])
    if len(args) >= 2 and args[0] == "build":
        build_for_character(args[1], out_path=args[2] if len(args) > 2 else None)
        return
    print(__doc__)


if __name__ == "__main__":
    main()

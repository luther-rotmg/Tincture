#!/usr/bin/env python3
"""
buildfile.py — write (and validate) PoE 2 `.build` files.

The `.build` format is documented in SCHEMA.md. This module is the *writer*: give it
structured build components and it emits a byte-valid `.build` dict. Where the
components come from is a separate concern — the plan is to pull a representative
public ladder character from GGG's Character API and map it through here (see the
repo roadmap). The serializer below is complete and tested via `--selftest`.

  python scripts/buildfile.py --selftest
"""

import json
import re
import sys

# Ascendancy display name -> .build code (usually "{Class}{slot}", e.g. "Monk1").
# Derived from the OFFICIAL GGG PoE2 skill-tree export
# (github.com/grindinggear/poe2-skilltree-export, tag 0.5.2) — classes[].ascendancies[].id
# is exactly the code the .build "ascendancy" field uses. Martial Artist -> Monk1 is
# additionally cross-confirmed against a real .build export, which validates that the
# export's ascendancyId == the .build code for the rest. Note Abyssal Lich -> "Witch3b"
# (a lettered variant, not "{Class}{digit}"). `scripts/treedata.py` re-derives this map
# from the live export so it can be refreshed per patch without re-vendoring GGG data.
ASCENDANCY_CODES = {
    # Monk
    "Martial Artist": "Monk1", "Invoker": "Monk2", "Acolyte of Chayula": "Monk3",
    # Ranger
    "Deadeye": "Ranger1", "Pathfinder": "Ranger3",
    # Warrior
    "Titan": "Warrior1", "Warbringer": "Warrior2", "Smith of Kitava": "Warrior3",
    # Witch
    "Infernalist": "Witch1", "Blood Mage": "Witch2", "Lich": "Witch3", "Abyssal Lich": "Witch3b",
    # Sorceress
    "Stormweaver": "Sorceress1", "Chronomancer": "Sorceress2", "Disciple of Varashta": "Sorceress3",
    # Mercenary
    "Tactician": "Mercenary1", "Witchhunter": "Mercenary2", "Gemling Legionnaire": "Mercenary3",
    # Huntress
    "Amazon": "Huntress1", "Spirit Walker": "Huntress2", "Ritualist": "Huntress3",
    # Druid
    "Oracle": "Druid1", "Shaman": "Druid2",
}

VALID_SLOTS = {
    "Weapon1", "Weapon2", "Helm1", "BodyArmour1", "Gloves1", "Boots1",
    "Belt1", "Amulet1", "Ring1", "Ring2", "Charm1", "Flask1",
}


def gem_path(name_or_path, support=False):
    """Accept either a bare gem name ('WhirlingAssault') or a full metadata path."""
    if "/" in name_or_path:
        return name_or_path
    kind = "SupportGem" if support else "SkillGem"
    return f"Metadata/Items/Gems/{kind}{name_or_path}"


def _interval(lo, hi):
    return [int(lo), int(hi)]


def make_item(name, *, slot, mods=None, min_level=1, max_level=100,
              unique=False, x=0, y=0):
    """
    Two real shapes:
      * rare/magic/normal -> described by additional_text + level_interval gating
      * unique            -> identified by unique_name only (no text, no gating)
    """
    if slot not in VALID_SLOTS:
        raise ValueError(f"unknown inventory slot {slot!r}; expected one of {sorted(VALID_SLOTS)}")
    if unique:
        return {
            "inventory_id": slot,
            "unique_name": name,
            "slot_x": int(x),
            "slot_y": int(y),
        }
    lines = [name] + [f"{i}. {m}" for i, m in enumerate(mods or [], start=1)]
    return {
        "additional_text": "\n".join(lines),
        "inventory_id": slot,
        "level_interval": _interval(min_level, max_level),
        "slot_x": int(x),
        "slot_y": int(y),
    }


def make_skill(gem, *, supports=None, min_level=1, max_level=100):
    return {
        "id": gem_path(gem),
        "level_interval": _interval(min_level, max_level),
        "support_skills": [
            {"id": gem_path(s["gem"], support=True),
             "level_interval": _interval(s.get("min_level", 1), s.get("max_level", 100))}
            for s in (supports or [])
        ],
    }


# A real ascendancy code is "{Class}{slot}" — letters then a digit, optionally a lettered
# variant (e.g. "Monk1", "Sorceress2", "Witch3b").
_CODE_RE = re.compile(r"^[A-Za-z]+[0-9]+[a-z]?$")


def resolve_ascendancy(ascendancy):
    """Display name -> confirmed code, or accept an already code-shaped value.

    Refuses an UNMAPPED display name (e.g. 'Stormweaver') rather than passing it through
    as the code. A display name in the `ascendancy` field is structurally valid but the
    game silently refuses to load it — exactly the failure we must never ship. Only
    confirmed names (in ASCENDANCY_CODES) or code-shaped strings get through.
    """
    if ascendancy in ASCENDANCY_CODES:
        return ASCENDANCY_CODES[ascendancy]
    if ascendancy and (ascendancy in ASCENDANCY_CODES.values() or _CODE_RE.match(ascendancy)):
        return ascendancy
    raise ValueError(
        f"ascendancy {ascendancy!r} has no confirmed .build code. Mapped: "
        f"{sorted(ASCENDANCY_CODES)}. Emitting it would produce a file the game "
        f"silently refuses — confirm the code from a real export first."
    )


def serialize_build(*, author, ascendancy, name, items=None, passives=None, skills=None):
    """
    Build a `.build` dict. `ascendancy` may be a confirmed display name (mapped via
    ASCENDANCY_CODES) or an already-resolved code like 'Monk1'. An unmapped display
    name raises (see resolve_ascendancy) — we never emit an unloadable file.
    """
    code = resolve_ascendancy(ascendancy)
    return {
        "author": author,
        "ascendancy": code,
        "name": name[:40],
        "inventory_slots": list(items or []),
        "passives": [{"id": p} for p in (passives or [])],
        "skills": list(skills or []),
    }


def to_text(build):
    """Serialize to the on-disk string (minified, like real exports)."""
    return json.dumps(build, separators=(",", ":"), ensure_ascii=False)


REQUIRED_TOP = {"author", "ascendancy", "name", "inventory_slots", "passives", "skills"}


def validate(build):
    """Return a list of problems; empty list means it matches the schema."""
    errs = []
    if not isinstance(build, dict):
        return ["root is not an object"]
    missing = REQUIRED_TOP - set(build)
    if missing:
        errs.append(f"missing top-level keys: {sorted(missing)}")
    if not isinstance(build.get("ascendancy", ""), str) or not build.get("ascendancy"):
        errs.append("ascendancy must be a non-empty string")
    # validate() is the safety net is_loadable() and the tests rely on, so it must REPORT bad
    # input, never throw on it: guard every collection and entry type before subscripting.
    for key in ("inventory_slots", "passives", "skills"):
        if key in build and not isinstance(build[key], list):
            errs.append(f"{key} must be a list")
    slots = build.get("inventory_slots") if isinstance(build.get("inventory_slots"), list) else []
    for i, it in enumerate(slots):
        if not isinstance(it, dict):
            errs.append(f"inventory_slots[{i}] is not an object")
            continue
        if it.get("inventory_id") not in VALID_SLOTS:
            errs.append(f"inventory_slots[{i}].inventory_id invalid: {it.get('inventory_id')!r}")
        is_unique = "unique_name" in it and "additional_text" not in it
        if not is_unique:
            if "additional_text" not in it:
                errs.append(f"inventory_slots[{i}] needs additional_text (rare) or unique_name (unique)")
            li = it.get("level_interval")
            if not (isinstance(li, list) and len(li) == 2):
                errs.append(f"inventory_slots[{i}].level_interval must be [min,max] for a stat item")
    passives = build.get("passives") if isinstance(build.get("passives"), list) else []
    for i, p in enumerate(passives):
        if not isinstance(p, dict):
            errs.append(f"passives[{i}] is not an object")
        elif "id" not in p:
            errs.append(f"passives[{i}] missing id")
    skills = build.get("skills") if isinstance(build.get("skills"), list) else []
    for i, s in enumerate(skills):
        if not isinstance(s, dict):
            errs.append(f"skills[{i}] is not an object")
            continue
        if "id" not in s:
            errs.append(f"skills[{i}] missing id")
        if not isinstance(s.get("support_skills", []), list):
            errs.append(f"skills[{i}].support_skills must be a list")
    return errs


CONFIRMED_CODES = set(ASCENDANCY_CODES.values())


def is_loadable(build):
    """Stricter than validate(): a build is LOADABLE in-game only if it is structurally
    valid AND its ascendancy is a CONFIRMED code AND it has at least one passive node.
    Aggregate meta stats can't satisfy this — which is the point. Use this (not just
    validate()) to gate anything that claims to produce a real, loadable .build."""
    if validate(build):
        return False
    if build.get("ascendancy") not in CONFIRMED_CODES:
        return False
    if not build.get("passives"):
        return False
    return True


def _selftest():
    build = serialize_build(
        author="Tincture",
        ascendancy="Martial Artist",
        name="Whirling Assault — Martial Artist (sample)",
        items=[
            make_item("Sinister Quarterstaff", slot="Weapon1",
                      mods=["Adds 130 to 198 Fire Damage", "+4.4% to Critical Hit Chance"],
                      min_level=42),
            make_item("Wrapped Sandals", slot="Boots1",
                      mods=["10% increased Movement Speed"], min_level=11),
            make_item("Shavronne's Satchel", slot="Belt1", unique=True),
        ],
        passives=["attack_speed25", "shadow_monk_notable1", "intelligence10"],
        skills=[
            make_skill("WhirlingAssault", min_level=42, supports=[
                {"gem": "RageThree"},
                {"gem": "PinpointCritical", "min_level": 15},
            ]),
            make_skill("KillingPalm"),
        ],
    )
    errs = validate(build)
    print("ascendancy code:", build["ascendancy"])
    print("top-level keys :", sorted(build.keys()))
    print("on-disk bytes  :", len(to_text(build)))
    print("validate()     :", "OK" if not errs else errs)
    # also confirm it survives a JSON round-trip
    assert json.loads(to_text(build)) == build
    print("round-trip     : OK")

    ok = not errs
    # no-fabrication guard: an unmapped display name must REFUSE to serialize
    try:
        serialize_build(author="x", ascendancy="Definitely Not An Ascendancy", name="nope")
        print("unmapped guard : FAIL (unmapped ascendancy did not raise)"); ok = False
    except ValueError:
        print("unmapped guard : OK (refused unconfirmed ascendancy)")
    # the front-end meta-template shape must NOT pass as a real .build
    template = {"_tool": "tincture", "_kind": "meta-template",
                "ascendancy": "Martial Artist", "class": "Monk"}
    if validate(template):
        print("template guard : OK (meta-template rejected by validate)")
    else:
        print("template guard : FAIL (meta-template passed validate)"); ok = False
    # is_loadable: the confirmed sample build qualifies; a no-passives build does not
    print("is_loadable    :", "OK" if is_loadable(build) else "FAIL"); ok = ok and is_loadable(build)
    bare = serialize_build(author="x", ascendancy="Monk1", name="bare", passives=[])
    if is_loadable(bare):
        print("loadable guard : FAIL (empty-passives build marked loadable)"); ok = False
    else:
        print("loadable guard : OK (empty-passives build not loadable)")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(__doc__)

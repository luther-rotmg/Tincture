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
import sys

# Ascendancy display name -> .build code ("{Class}{slot}").
# Only Martial Artist is confirmed from real exports; fill the rest by exporting one
# build per ascendancy and reading the "ascendancy" field (tracked in the README TODO).
ASCENDANCY_CODES = {
    "Martial Artist": "Monk1",
    # "Invoker": "Monk?",  "Acolyte of Chayula": "Monk?",
    # "Deadeye": "Ranger?", "Pathfinder": "Ranger?",
    # "Titan": "Warrior?",  "Warbringer": "Warrior?",
    # "Infernalist": "Witch?", "Blood Mage": "Witch?", "Lich": "Witch?",
    # "Stormweaver": "Sorceress?", "Chronomancer": "Sorceress?",
    # "Witchhunter": "Mercenary?", "Gemling Legionnaire": "Mercenary?",
    # "Spirit Walker": "Huntress?",
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


def serialize_build(*, author, ascendancy, name, items=None, passives=None, skills=None):
    """
    Build a `.build` dict. `ascendancy` may be a display name (mapped via
    ASCENDANCY_CODES) or an already-resolved code like 'Monk1'.
    """
    code = ASCENDANCY_CODES.get(ascendancy, ascendancy)
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
    for i, it in enumerate(build.get("inventory_slots", [])):
        if it.get("inventory_id") not in VALID_SLOTS:
            errs.append(f"inventory_slots[{i}].inventory_id invalid: {it.get('inventory_id')!r}")
        is_unique = "unique_name" in it and "additional_text" not in it
        if not is_unique:
            if "additional_text" not in it:
                errs.append(f"inventory_slots[{i}] needs additional_text (rare) or unique_name (unique)")
            li = it.get("level_interval")
            if not (isinstance(li, list) and len(li) == 2):
                errs.append(f"inventory_slots[{i}].level_interval must be [min,max] for a stat item")
    for i, p in enumerate(build.get("passives", [])):
        if "id" not in p:
            errs.append(f"passives[{i}] missing id")
    for i, s in enumerate(build.get("skills", [])):
        if "id" not in s:
            errs.append(f"skills[{i}] missing id")
        if not isinstance(s.get("support_skills", []), list):
            errs.append(f"skills[{i}].support_skills must be a list")
    return errs


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
    return 0 if not errs else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(__doc__)

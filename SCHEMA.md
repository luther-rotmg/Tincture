# The PoE 2 `.build` file format

Reverse-engineered from real `0.5.0` exports. This is the format the in-game Build
Planner reads from `Documents/My Games/Path of Exile 2/BuildPlanner/`. It's plain
JSON (UTF-8, minified in practice), schema **version 1 (experimental)** — corrupted
or malformed text makes the game silently refuse to load the file.

## Top level

Six required keys, plus an optional `description` (the game tolerates it; Tincture's
reconstructed builds use it for source attribution):

```jsonc
{
  "author":          "string",   // build creator
  "ascendancy":      "Monk1",    // class-coded ascendancy (see below)
  "name":            "string",   // display name; the game truncates the DISPLAY around 40 chars
  "description":     "string",   // optional — Tincture credits the source character + poe.ninja here
  "inventory_slots": [ /* items */ ],
  "passives":        [ /* allocated passive nodes */ ],
  "skills":          [ /* skill gems + their supports */ ]
}
```

> `scripts/buildfile.py` emits the six required keys; the poe.ninja reconstructor
> (`tools/build-from-ninja.cjs`) also writes `description`. Names aren't truncated at
> write time — the game truncates only what it displays.

### `ascendancy`

A class code plus the ascendancy's slot index, e.g. `Monk1`. The complete map lives in
`scripts/buildfile.py` `ASCENDANCY_CODES`, re-derived from GGG's official tree export by
`scripts/treedata.py` (run `--check` to re-verify it):

| Class | Ascendancies (code) |
| ----- | ------------------- |
| Monk | Martial Artist `Monk1`, Invoker `Monk2`, Acolyte of Chayula `Monk3` |
| Ranger | Deadeye `Ranger1`, Pathfinder `Ranger3` |
| Warrior | Titan `Warrior1`, Warbringer `Warrior2`, Smith of Kitava `Warrior3` |
| Witch | Infernalist `Witch1`, Blood Mage `Witch2`, Lich `Witch3`, Abyssal Lich `Witch3b` |
| Sorceress | Stormweaver `Sorceress1`, Chronomancer `Sorceress2`, Disciple of Varashta `Sorceress3` |
| Mercenary | Tactician `Mercenary1`, Witchhunter `Mercenary2`, Gemling Legionnaire `Mercenary3` |
| Huntress | Amazon `Huntress1`, Spirit Walker `Huntress2`, Ritualist `Huntress3` |
| Druid | Oracle `Druid1`, Shaman `Druid2` |

> Note the lettered variant `Witch3b` (Abyssal Lich) — not the usual `{Class}{digit}` shape.

### `inventory_slots[]`

One entry per equipped item, in one of **two shapes**. Items are guidance text, not
real transferable items.

**Rare / magic / normal** — described by stats, with level gating:

```jsonc
{
  "additional_text": "Sinister Quarterstaff\n1. Adds 130 to 198 Fire Damage\n2. +4.4% to Critical Hit Chance",
  "inventory_id":    "Weapon1",
  "level_interval":  [42, 100],     // [min, max] — when this item appears in the guide
  "slot_x":          0,
  "slot_y":          0
}
```

**Unique** — identified by name only (no `additional_text`, no `level_interval`):

```jsonc
{
  "inventory_id": "Belt1",
  "unique_name":  "Shavronne's Satchel",
  "slot_x":       0,
  "slot_y":       0
}
```

`additional_text` convention (rares): first line is the item base/name, then numbered
mod lines (`1. …`, `2. …`) separated by `\n`. In one real progression, 80 of 91 slots
were the rare shape and 11 were uniques.

**`inventory_id` vocabulary** (observed):
`Weapon1`, `Weapon2`, `Helm1`, `BodyArmour1`, `Gloves1`, `Boots1`, `Belt1`,
`Amulet1`, `Ring1`, `Ring2`, `Charm1`, `Flask1`.

### `passives[]`

The allocated passive-tree nodes, as **named slugs** (not numeric hashes):

```jsonc
[ { "id": "attack_speed25" }, { "id": "shadow_monk_notable1" }, { "id": "intelligence10" } ]
```

Slugs follow loose families: `attack_speed*`, `attack_damage*`, `criticals*`,
`intelligence*`, `dexterity*`, `attributes*`, and `*_notable*` / class-prefixed
notables like `shadow_monk_notable1`.

A node may also carry an optional `weapon_set` (`1` or `2`) for a weapon-set-specific
allocation (PoE2's dual weapon-set trees); absent/null means the shared selection.
The reconstructor emits these from the source character's `passiveSelectionSet1/2`.

### `skills[]`

Each skill gem and its support gems, identified by **metadata path**:

```jsonc
{
  "id": "Metadata/Items/Gems/SkillGemWhirlingAssault",
  "level_interval": [42, 100],
  "support_skills": [
    { "id": "Metadata/Items/Gems/SupportGemRageThree",       "level_interval": [1, 100] },
    { "id": "Metadata/Items/Gems/SupportGemPinpointCritical","level_interval": [15, 100] }
  ]
}
```

Notes:
- Paths look like `Metadata/Items/Gems/SkillGem<Name>` and
  `Metadata/Items/Gems/SupportGem<Name>`.
- The segment is **inconsistent** in real data — both `…/Items/Gems/…` and
  `…/Items/Gem/…` (singular) appear, sometimes within the same file. Preserve
  whatever the source provides rather than normalizing.
- `level_interval` on a skill/support is what produces the leveling guide: a gem with
  `[42, 100]` only shows once the character reaches level 42.

## The leveling progression

A "build" is usually shipped as several `.build` files, one per stage, each a fuller
snapshot than the last (more passives, more gems unlocked, better gear). Example
counts from one real progression:

| Stage              | passives | skills | items |
| ------------------ | -------: | -----: | ----: |
| Lvl 1–23           |       29 |      8 |     6 |
| Act 3–6            |      109 |      9 |    10 |
| Campaign End       |      136 |     12 |    13 |
| Early Endgame      |      151 |     10 |    12 |
| Uber Endgame       |      158 |     10 |    12 |

## Generating one

Producing a **valid, loadable** `.build` requires real build data — passive slugs,
gem metadata paths, item text, and the ascendancy code — which is **not** present in
aggregate meta stats. Tincture's live generator is `tools/build-from-ninja.cjs`: it
reconstructs a loadable build from a public-ladder character (passives via the GGG tree
export, gems via PoB2 `Gems.lua`, items → text), cohesion-QA's it (including a check
that the build runs the ascendancy's dominant meta weapon), and writes
`builds/<slug>.build` plus a sibling `<slug>.pob` (Path of Building export). GGG's own
Character API is a **self-only** "export *my* character" path (`scripts/ggg.py`), not
the meta source. `scripts/buildfile.py` is the lower-level serializer/validator.

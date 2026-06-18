#!/usr/bin/env python3
"""
treedata.py — derive the passive node-id <-> .build-slug map (and the ascendancy-code
table) from GGG's OFFICIAL public PoE2 skill-tree export, WITHOUT vendoring GGG's data.

Why this exists: a loadable `.build` needs allocated passives as named slugs (e.g.
"attack_speed25"), while the GGG Character API returns a character's passives as NUMERIC
node ids. GGG's public skill-tree export
(github.com/grindinggear/poe2-skilltree-export) carries BOTH on every node — the node's
object key / `skill` is the numeric id, and `id` is the slug — so it is a complete
numeric<->slug map. It also exposes `classes[].ascendancies[].id`, which is exactly the
`.build` ascendancy code (e.g. "Martial Artist" -> "Monk1"). This module downloads that
export on demand and builds those lookups.

It does NOT commit GGG's data into the repo: the export carries no licence, so deriving
from it for tooling (as PoB and friends do) is fine, but re-publishing it is not. Keep
the derived maps out of version control; refresh them per patch by re-running this.

  python scripts/treedata.py --slugs        # download + report the numeric<->slug map
  python scripts/treedata.py --codes        # print ascendancy name -> .build code
  python scripts/treedata.py --check        # cross-check buildfile.ASCENDANCY_CODES vs the export
  python scripts/treedata.py --check --file tree-export.json   # offline: --file is a local copy of
                                            # GGG's export data.json, NOT the repo's own data.json

Stdlib only, fail-safe, no third-party deps — consistent with the rest of the pipeline.
"""
import argparse
import json
import os
import sys
import urllib.request

# Pinned to the export tag the committed ascendancy codes were derived from, so the data is
# reproducible and `--check` is a true regression test. Bump this (and re-run --check/--codes,
# then update buildfile.ASCENDANCY_CODES) when GGG ships a new tree.
EXPORT_URL = "https://raw.githubusercontent.com/grindinggear/poe2-skilltree-export/0.5.2/data.json"
USER_AGENT = ("Tincture/0.5.0 (+https://github.com/luther-rotmg/Tincture; "
             "contact: ryan.duke360@gmail.com) tree-export reader")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def load_export(url=EXPORT_URL, path=None):
    """Return the parsed tree-export JSON — from a local file if `path` is given, else
    downloaded. Raises on network/parse failure (callers decide how to fail safe)."""
    if path:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def slug_map(export):
    """numeric node id (int) -> .build slug (str).

    The Character API's allocated-passive `hashes` are these numeric ids; the `.build`
    format references the slugs. Skips the synthetic 'root' node and anything missing a
    slug or numeric id. Slugs are opaque strings ("attack_speed25", "passive_keystone_
    zealots_oath", "AscendancyMonk1Notable3", "energy_shield34_") — do not parse them."""
    out = {}
    for key, node in (export.get("nodes") or {}).items():
        if key == "root" or not isinstance(node, dict):
            continue
        slug, skill = node.get("id"), node.get("skill")
        if slug is None or skill is None:
            continue
        out[int(skill)] = str(slug)
    return out


def ascendancy_codes(export):
    """ascendancy display name -> .build code, from classes[].ascendancies[]
    (e.g. 'Martial Artist' -> 'Monk1'). Skips unnamed/placeholder entries (name is null)."""
    out = {}
    for cls in export.get("classes") or []:
        for asc in cls.get("ascendancies") or []:
            name, code = asc.get("name"), asc.get("id")
            if name and code:
                out[str(name)] = str(code)
    return out


def hashes_to_slugs(hashes, smap):
    """Translate a Character API passive `hashes` list (numeric ids) to `.build` slugs,
    dropping any id absent from the export (e.g. a tree-version mismatch — surfaced by the
    caller, never silently invented)."""
    out = []
    for h in (hashes or []):
        try:
            n = int(h)
        except (TypeError, ValueError):
            continue
        if n in smap:
            out.append(smap[n])
    return out


def _main():
    ap = argparse.ArgumentParser(
        description="Derive the PoE2 passive slug / ascendancy-code maps from GGG's tree export.")
    ap.add_argument("--file", help="use a local data.json export instead of downloading")
    ap.add_argument("--slugs", action="store_true", help="report the numeric<->slug map")
    ap.add_argument("--codes", action="store_true", help="print ascendancy name -> .build code")
    ap.add_argument("--check", action="store_true",
                    help="cross-check buildfile.ASCENDANCY_CODES against the live export")
    args = ap.parse_args()
    if not (args.slugs or args.codes or args.check):
        ap.print_help()
        return 0
    try:
        export = load_export(path=args.file)
    except Exception as e:  # noqa: BLE001
        print(f"[treedata] could not load export: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    if args.slugs:
        smap = slug_map(export)
        sample = next(iter(smap.items())) if smap else None
        print(f"[treedata] {len(smap)} numeric<->slug entries (e.g. {sample})")
    if args.codes:
        for name, code in sorted(ascendancy_codes(export).items()):
            print(f"  {name!r}: {code!r}")
    if args.check:
        import buildfile
        live = ascendancy_codes(export)
        ours = buildfile.ASCENDANCY_CODES
        ok = True
        for name, code in ours.items():
            if live.get(name) != code:
                print(f"[mismatch] {name!r}: buildfile={code!r} export={live.get(name)!r}")
                ok = False
        unmapped = sorted(n for n in live if n not in ours)
        print(f"[treedata] {len(ours)} mapped locally; export names {len(live)} ascendancies; "
              f"{'ALL MATCH' if ok else 'MISMATCHES above'}.")
        if unmapped:
            print(f"[treedata] in export but not in buildfile (add when released): {unmapped}")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())

#!/usr/bin/env python3
"""
Stdlib unit tests for the Tincture pipeline — no network, no pip.

Run from the repo root:
    python -m unittest discover -s scripts -v
or directly:
    python scripts/test_distill.py

These lock in Tincture's honesty invariants so a future change can't quietly break
them: ascendancy -> class completeness, the data.json schema, no inflated totals,
curated rows carrying no ladder stats, and no fabricated/unloadable .build files.
"""
import json
import os
import sys
import unittest
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import distill    # noqa: E402
import buildfile  # noqa: E402
import treedata   # noqa: E402

DATA_PATH = os.path.join(ROOT, "data.json")

# The mappings the project promises. Frozen so a new/renamed ascendancy a future patch
# adds trips a test instead of silently rendering with no class.
LOCKED = {
    "Martial Artist": "Monk", "Spirit Walker": "Huntress", "Smith of Kitava": "Warrior",
    "Deadeye": "Ranger", "Gemling Legionnaire": "Mercenary", "Oracle": "Druid",
    "Disciple of Varashta": "Sorceress", "Abyssal Lich": "Witch", "Titan": "Warrior",
    "Invoker": "Monk", "Infernalist": "Witch", "Witchhunter": "Mercenary",
}
BUILD_KEYS = {"rank", "tier", "cls", "asc", "skill", "pop", "delta", "n", "tag"}
BANNED_IN_TAGS = ("best", "s-tier", "meta", "optimal", "strongest", " op ")


def load_data():
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


class AscMap(unittest.TestCase):
    def test_locked_mappings(self):
        for asc, cls in LOCKED.items():
            self.assertEqual(distill.ASC_TO_CLASS.get(asc), cls, f"{asc!r} should map to {cls!r}")

    def test_sample_builds_all_mapped(self):
        for b in distill.SAMPLE_BUILDS:
            self.assertTrue(distill.ASC_TO_CLASS.get(b["asc"]), f"{b['asc']!r} unmapped in ASC_TO_CLASS")

    def test_every_mapped_ascendancy_has_a_tag(self):
        for asc in distill.ASC_TO_CLASS:
            self.assertIn(asc, distill.ASC_TAGS, f"{asc!r} missing an editorial tag")

    def test_class_and_tag_tables_cover_the_same_ascendancies(self):
        # the two hand-maintained meta tables must stay in lockstep, so an ascendancy added to
        # one but not the other (the Shaman/Druid drift the audit caught) trips a test.
        self.assertEqual(set(distill.ASC_TO_CLASS), set(distill.ASC_TAGS))

    def test_tags_are_descriptive_not_rankings(self):
        for asc, tag in distill.ASC_TAGS.items():
            self.assertIsInstance(tag, str)
            self.assertTrue(tag.strip(), f"{asc!r} has an empty tag")
            low = f" {tag.lower()} "
            for banned in BANNED_IN_TAGS:
                self.assertNotIn(banned, low, f"tag for {asc!r} reads as a ranking: {tag!r}")


class Normalize(unittest.TestCase):
    def test_normalize_one_shape(self):
        rows, total = distill.normalize_one({
            "total": 1000,
            "statistics": [{"class": "Martial Artist", "percentage": 24.54},
                           {"class": "Deadeye", "percentage": 10.0}],
        })
        self.assertEqual(total, 1000)
        self.assertEqual(rows[0]["cls"], "Monk")
        self.assertEqual(rows[0]["asc"], "Martial Artist")
        self.assertEqual(rows[0]["skill"], "")                       # ascendancy-level only
        self.assertEqual(rows[0]["pop"], 24.5)                       # rounded display share
        self.assertEqual(rows[0]["n"], round(1000 * 24.54 / 100))    # derived from unrounded share
        self.assertTrue(rows[0]["tag"])                              # editorial tag filled

    def test_unmapped_ascendancy_blank_class_does_not_crash(self):
        rows, _ = distill.normalize_one({"total": 100, "statistics": [{"class": "Future Asc", "percentage": 5.0}]})
        self.assertEqual(rows[0]["cls"], "")                         # blank, but still present

    def test_first_run_delta_is_none_not_zero(self):
        meta = {"url": "x", "name": "X", "mode": "SC", "label": "X"}
        rows = [{"cls": "Monk", "asc": "Martial Artist", "skill": "", "pop": 24.5, "n": 245, "tag": ""}]
        league = distill.distill_league([dict(r) for r in rows], prev_builds=[], total=1000, meta=meta)
        self.assertIsNone(league["builds"][0]["delta"])             # no baseline -> None, never a fake 0.0

    def test_real_delta_when_baseline_exists(self):
        meta = {"url": "x", "name": "X", "mode": "SC", "label": "X"}
        prev = [{"asc": "Martial Artist", "skill": "", "pop": 23.0}]
        rows = [{"cls": "Monk", "asc": "Martial Artist", "skill": "", "pop": 24.5, "n": 245, "tag": ""}]
        league = distill.distill_league([dict(r) for r in rows], prev_builds=prev, total=1000, meta=meta)
        self.assertAlmostEqual(league["builds"][0]["delta"], 1.5, places=1)


class DataJson(unittest.TestCase):
    def setUp(self):
        if not os.path.exists(DATA_PATH):
            self.skipTest("data.json not present")
        self.data = load_data()

    def test_top_level(self):
        for k in ("patch", "updated", "sources", "default", "leagues"):
            self.assertIn(k, self.data)
        self.assertIsInstance(self.data["leagues"], list)
        self.assertTrue(self.data["leagues"])
        self.assertIsInstance(self.data["sources"], int)        # a source count, never a string
        datetime.fromisoformat(self.data["updated"])            # must be a parseable ISO timestamp
        urls = {L.get("url") for L in self.data["leagues"]}
        self.assertIn(self.data["default"], urls, "default must name an existing league")

    def test_trend_keys_unique_per_league(self):
        # apply_trends keys the previous snapshot on asc|skill; a duplicate key would
        # silently drop a build's baseline, so each league's (asc, skill) must be unique.
        for L in self.data["leagues"]:
            keys = [(b["asc"], b.get("skill", "")) for b in L["builds"]]
            self.assertEqual(len(keys), len(set(keys)), f"{L['url']} has duplicate (asc,skill) keys")

    def test_league_and_build_schema(self):
        for L in self.data["leagues"]:
            for k in ("url", "name", "mode", "label", "totals", "builds"):
                self.assertIn(k, L, f"league missing {k!r}")
            self.assertIn("characters", L["totals"])
            self.assertIn("ascendancies", L["totals"])
            ranks = []
            for b in L["builds"]:
                self.assertTrue(BUILD_KEYS.issubset(b), f"build missing keys: {BUILD_KEYS - set(b)}")
                self.assertTrue(b["pop"] is None or (0 <= b["pop"] <= 100), f"bad pop {b['pop']!r}")
                self.assertTrue(b["n"] is None or b["n"] >= 0, f"bad n {b['n']!r}")
                self.assertTrue(b["delta"] is None or isinstance(b["delta"], (int, float)))
                ranks.append(b["rank"])
            self.assertEqual(ranks, sorted(ranks), f"{L['url']} ranks not ascending")
            if ranks:
                self.assertEqual(ranks[0], 1)

    def test_no_inflated_totals(self):
        for L in self.data["leagues"]:
            if L.get("curated"):
                continue
            shown = [b for b in L["builds"] if b["pop"] is not None]
            sum_n = sum(b["n"] for b in shown if b["n"] is not None)
            self.assertLessEqual(sum_n, L["totals"]["characters"] + 1, f"{L['url']} sum(n) exceeds total")
            self.assertLessEqual(sum(b["pop"] for b in shown), 100.0 + 0.5, f"{L['url']} shares exceed 100%")
            distinct = len({b["asc"] for b in L["builds"]})
            self.assertEqual(L["totals"]["ascendancies"], distinct, f"{L['url']} ascendancy count mismatch")

    def test_curated_carries_no_ladder_stats(self):
        for L in self.data["leagues"]:
            if not L.get("curated"):
                continue
            self.assertTrue(L.get("note"), "curated league must carry a note")
            for b in L["builds"]:
                self.assertIsNone(b["pop"])
                self.assertIsNone(b["delta"])
                self.assertIsNone(b["n"])

    def test_classes_match_the_map(self):
        for L in self.data["leagues"]:
            for b in L["builds"]:
                if b["cls"]:
                    self.assertEqual(distill.ASC_TO_CLASS.get(b["asc"]), b["cls"],
                                     f"{b['asc']!r} class disagrees with ASC_TO_CLASS")


class NoFabrication(unittest.TestCase):
    def test_unmapped_ascendancy_refused(self):
        # an ascendancy with no confirmed .build code must still refuse to serialize
        with self.assertRaises(ValueError):
            buildfile.serialize_build(author="x", ascendancy="Definitely Not An Ascendancy", name="nope")

    def test_confirmed_ascendancy_serializes(self):
        b = buildfile.serialize_build(author="Tincture", ascendancy="Martial Artist",
                                      name="ok", passives=["attack_speed25"])
        self.assertEqual(b["ascendancy"], "Monk1")
        self.assertEqual(buildfile.validate(b), [])

    def test_every_meta_ascendancy_has_a_build_code(self):
        # every ascendancy the meta map knows must be serialisable (have a .build code),
        # so Decant never refuses a real ladder ascendancy. Codes come from the official
        # GGG tree export; this locks the two tables in sync.
        for asc in distill.ASC_TO_CLASS:
            self.assertIn(asc, buildfile.ASCENDANCY_CODES, f"{asc!r} has no .build ascendancy code")

    def test_ascendancy_codes_are_well_formed(self):
        import re
        for asc, code in buildfile.ASCENDANCY_CODES.items():
            self.assertRegex(code, r"^[A-Za-z]+[0-9]+[a-z]?$", f"{asc!r} code {code!r} is malformed")

    def test_meta_template_is_not_a_valid_build(self):
        template = {"_tool": "tincture", "_kind": "meta-template", "ascendancy": "Martial Artist"}
        self.assertTrue(buildfile.validate(template), "front-end meta template must NOT pass as a .build")

    def test_is_loadable_requires_passives(self):
        bare = buildfile.serialize_build(author="x", ascendancy="Monk1", name="bare", passives=[])
        self.assertFalse(buildfile.is_loadable(bare))

    def test_committed_build_files_validate(self):
        builds_dir = os.path.join(ROOT, "builds")
        if not os.path.isdir(builds_dir):
            self.skipTest("no builds/ directory yet")
        seen = 0
        for name in os.listdir(builds_dir):
            if not name.endswith(".build"):
                continue
            seen += 1
            with open(os.path.join(builds_dir, name), encoding="utf-8") as f:
                build = json.load(f)
            self.assertEqual(buildfile.validate(build), [], f"{name} fails the .build schema")
            self.assertTrue(buildfile.is_loadable(build), f"{name} is structurally valid but not loadable")
        if not seen:
            self.skipTest("builds/ has no .build files yet")


MINI_EXPORT = {
    "nodes": {
        "root": {},
        "4": {"skill": 4, "id": "lightning14", "name": "Shock Chance"},
        "55": {"skill": 55, "id": "ailments38", "name": "Fast Acting Toxins"},
        "9999": {"skill": 9999, "name": "node with no slug"},   # missing id -> skipped
    },
    "classes": [
        {"name": "Monk", "ascendancies": [
            {"name": "Martial Artist", "id": "Monk1"},
            {"name": None, "id": "MonkX"},                       # unnamed -> skipped
        ]},
        {"name": "Witch", "ascendancies": [{"name": "Abyssal Lich", "id": "Witch3b"}]},
    ],
}


class TreeData(unittest.TestCase):
    """Lock the export-parsing logic offline (no network) on a synthetic fixture."""
    def test_slug_map_skips_root_and_slugless(self):
        self.assertEqual(treedata.slug_map(MINI_EXPORT), {4: "lightning14", 55: "ailments38"})

    def test_ascendancy_codes_skips_unnamed(self):
        codes = treedata.ascendancy_codes(MINI_EXPORT)
        self.assertEqual(codes, {"Martial Artist": "Monk1", "Abyssal Lich": "Witch3b"})

    def test_hashes_to_slugs_drops_unknown(self):
        smap = treedata.slug_map(MINI_EXPORT)
        self.assertEqual(treedata.hashes_to_slugs([4, 55, 123, "55"], smap),
                         ["lightning14", "ailments38", "ailments38"])

    def test_export_codes_agree_with_buildfile(self):
        # the codes we ship must match what the (fixture-shaped) export would derive
        codes = treedata.ascendancy_codes(MINI_EXPORT)
        for name, code in codes.items():
            self.assertEqual(buildfile.ASCENDANCY_CODES.get(name), code,
                             f"{name!r}: buildfile disagrees with the export")


class FailSafe(unittest.TestCase):
    """The pipeline's most important promise: a bad upstream NEVER breaks the deployed site.
    These lock that contract (asserted only in prose before)."""

    def _run_live_with_fetch(self, fake_fetch):
        import io
        import contextlib
        before = None
        if os.path.exists(DATA_PATH):
            with open(DATA_PATH, "rb") as f:
                before = f.read()
        orig = distill.fetch_poeninja_builds
        distill.fetch_poeninja_builds = fake_fetch
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                rc = distill.run_live()
        finally:
            distill.fetch_poeninja_builds = orig
        after = None
        if os.path.exists(DATA_PATH):
            with open(DATA_PATH, "rb") as f:
                after = f.read()
        return rc, before, after

    def test_failed_fetch_keeps_data_json_and_exits_zero(self):
        rc, before, after = self._run_live_with_fetch(lambda: None)
        self.assertEqual(rc, 0)
        self.assertEqual(before, after, "a failed fetch must leave data.json byte-for-byte unchanged")

    def test_empty_feed_keeps_data_json_and_exits_zero(self):
        # parseable-but-useless upstream: no ranked league has builds -> keep the last good file
        rc, before, after = self._run_live_with_fetch(lambda: {"leagueBuilds": []})
        self.assertEqual(rc, 0)
        self.assertEqual(before, after, "an empty feed must leave data.json byte-for-byte unchanged")


class SitemapXml(unittest.TestCase):
    def test_excludes_data_json_keeps_home_and_landing(self):
        xml = distill._sitemap_xml("2026-06-27", ["deadeye", "titan"])
        self.assertNotIn("data.json", xml)                                  # a data file is not a crawlable page
        self.assertIn("<loc>https://tincturepoe2.com/</loc>", xml)
        self.assertIn("<loc>https://tincturepoe2.com/b/deadeye.html</loc>", xml)
        self.assertIn("<loc>https://tincturepoe2.com/b/titan.html</loc>", xml)
        self.assertIn("<lastmod>2026-06-27</lastmod>", xml)
        self.assertTrue(xml.endswith("</urlset>\n"))


class Apportion(unittest.TestCase):
    def test_derived_n_never_sums_above_total(self):
        # largest-remainder rounding: per-row round() can bias the headcounts above the real
        # population; apportionment must keep sum(n) <= total while staying share-accurate.
        league = {"total": 1000, "statistics": [
            {"class": "Martial Artist", "percentage": 24.567},
            {"class": "Deadeye", "percentage": 24.567},
            {"class": "Titan", "percentage": 24.567},
            {"class": "Lich", "percentage": 24.567},   # 4 x 24.567 = 98.268% -> naive round() inflates
        ]}
        rows, total = distill.normalize_one(league)
        self.assertLessEqual(sum(r["n"] for r in rows), total)
        for r in rows:                                  # each still within 1 of its exact share
            self.assertLessEqual(abs(r["n"] - total * 24.567 / 100.0), 1.0)

    def test_derived_n_clamped_when_shares_exceed_100(self):
        # poe.ninja top-N shares can sum to >100% (overlapping categories + independent rounding);
        # _apportion_n scales the exact counts down to <= total before flooring, so the derived
        # sample counts never inflate past the real ladder population.
        league = {"total": 1000, "statistics": [
            {"class": "Titan", "percentage": 25.0}, {"class": "Deadeye", "percentage": 25.0},
            {"class": "Lich", "percentage": 25.0}, {"class": "Invoker", "percentage": 25.0},
            {"class": "Infernalist", "percentage": 25.0}]}   # shares sum to 125%
        rows, total = distill.normalize_one(league)
        self.assertLessEqual(sum(r["n"] for r in rows), total)

    def test_zero_total_yields_zero_n(self):
        rows, _ = distill.normalize_one({"total": 0, "statistics": [{"class": "Titan", "percentage": 5.0}]})
        self.assertEqual(rows[0]["n"], 0)


class CrossLang(unittest.TestCase):
    def test_js_ascendancy_codes_match_python(self):
        # tools/build-from-ninja.cjs hand-maintains its own copy of ASCENDANCY_CODES; if it drifts
        # from buildfile.py the reconstructor can emit a code the validator/front end rejects.
        import re
        cjs = os.path.join(ROOT, "tools", "build-from-ninja.cjs")
        if not os.path.exists(cjs):
            self.skipTest("reconstructor not present")
        with open(cjs, encoding="utf-8") as f:
            src = f.read()
        m = re.search(r"const ASCENDANCY_CODES\s*=\s*\{(.*?)\}", src, re.S)
        self.assertTrue(m, "could not find ASCENDANCY_CODES in the reconstructor")
        js = dict(re.findall(r"'([^']+)'\s*:\s*'([^']+)'", m.group(1)))
        self.assertEqual(js, buildfile.ASCENDANCY_CODES,
                         "tools/build-from-ninja.cjs ASCENDANCY_CODES drifted from buildfile.py")


class HistoryAndSEO(unittest.TestCase):
    def test_history_append_dedupes_and_caps(self):
        pts = []
        p1 = {"t": "t1", "shares": {"A": 10.0}}
        pts = distill._history_append(pts, p1, 3)
        self.assertEqual(len(pts), 1)
        pts = distill._history_append(pts, dict(p1), 3)        # same shares -> skipped
        self.assertEqual(len(pts), 1)
        pts = distill._history_append(pts, {"t": "t2", "shares": {"A": 11.0}}, 3)
        pts = distill._history_append(pts, {"t": "t3", "shares": {"A": 12.0}}, 3)
        pts = distill._history_append(pts, {"t": "t4", "shares": {"A": 13.0}}, 3)
        self.assertEqual([p["t"] for p in pts], ["t2", "t3", "t4"])   # capped, oldest dropped
        self.assertEqual(pts[-1]["shares"]["A"], 13.0)

    def test_slugify_asc_matches_frontend_slugof(self):
        self.assertEqual(distill.slugify_asc("Martial Artist"), "martial-artist")
        self.assertEqual(distill.slugify_asc("Acolyte of Chayula"), "acolyte-of-chayula")
        self.assertEqual(distill.slugify_asc("Smith of Kitava"), "smith-of-kitava")

    def test_landing_page_is_real_content_not_a_doorway(self):
        h = distill.landing_html("Martial Artist", "Monk", "Combo melee striker", ["Tempest Flurry", "Falling Thunder"])
        self.assertIn("<title>", h)
        self.assertIn("Martial Artist", h)
        self.assertIn('rel="canonical" href="https://tincturepoe2.com/b/martial-artist.html"', h)
        self.assertIn("#asc=martial-artist", h)              # links into the SPA deep link
        self.assertIn("Tempest Flurry", h)                   # genuine content (common skills)
        self.assertIn("not affiliated", h)                   # honesty disclaimer
        self.assertNotIn('http-equiv="refresh"', h)          # NOT an auto-redirect doorway

    def test_landing_skips_curated_only_ascendancies(self):
        payload = {"default": "sc", "leagues": [
            {"url": "sc", "name": "SC", "builds": [{"asc": "Deadeye", "cls": "Ranger", "tag": "bow"}]},
            {"url": "standard", "curated": True, "builds": [
                {"asc": "Infernalist", "cls": "Witch", "tag": "minions"},
                {"asc": "Deadeye", "cls": "Ranger", "tag": "bow"}]},
        ]}
        info = distill._landing_ascendancies(payload)
        self.assertIn("Deadeye", info)            # present in a live league
        self.assertNotIn("Infernalist", info)     # curated-only -> no "live share" page

    def test_landing_html_escapes_untrusted_name(self):
        h = distill.landing_html("Evil</script><b>x", "Witch", "t", ["Spark"], ["Heart of the Well"], ["Eldritch Battery"], "Wand / Focus")
        self.assertNotIn("Evil</script>", h)      # neither JSON-LD nor body emits the raw injection
        self.assertIn("Heart of the Well", h)     # enrichment: signature uniques
        self.assertIn("Eldritch Battery", h)      # enrichment: notables
        self.assertIn("Wand / Focus", h)          # enrichment: weapon

    def test_landing_html_security_and_crosslink_invariants(self):
        sibs = [("deadeye", "Deadeye"), ("titan", "Titan"), ("oracle", "Oracle")]
        h = distill.landing_html("Titan", "Warrior", "tanky slam", weapon="Mace", siblings=sibs)
        # the tight CSP + favicon shipped on every landing page must not silently disappear
        self.assertIn('http-equiv="Content-Security-Policy"', h)
        self.assertIn("default-src 'none'", h)
        self.assertIn('rel="icon"', h)
        self.assertIn("/favicon.svg", h)
        self.assertIn('name="theme-color"', h)
        # the ONLY <script> is the JSON-LD data block — no executable inline JS — so the page's
        # script-src 'none' is safe. If real JS ever creeps in, this fails before the CSP breaks it.
        self.assertEqual(h.count("<script"), 1)
        self.assertIn('type="application/ld+json"', h)
        # cross-link footer: links to the OTHER ascendancies, NEVER a self-link (relative hrefs)
        self.assertIn('class="b-siblings"', h)
        self.assertIn('href="deadeye.html"', h)   # a sibling is linked
        self.assertIn(">Oracle</a>", h)
        self.assertNotIn('href="titan.html"', h)  # but the page never links to itself


class Economy(unittest.TestCase):
    def test_economy_payload_shape(self):
        raw = {
            "core": {"primary": "divine", "secondary": "chaos", "rates": {"exalted": 208.5, "chaos": 8.55}},
            "items": [{"id": "alch", "name": "Orb of Alchemy"}, {"id": "exalted", "name": "Exalted Orb"}],
            "lines": [
                {"id": "alch", "primaryValue": 0.0031, "volumePrimaryValue": 334.4, "sparkline": {"totalChange": 37.56}},
                {"id": "exalted", "primaryValue": 0.0048, "volumePrimaryValue": 9000},
                {"id": None},                         # malformed line is skipped
            ],
        }
        p = distill._economy_payload(raw, "2026-06-19T00:00:00+00:00")
        self.assertEqual(p["primary"], "divine")
        self.assertEqual(p["rates"], {"exalted": 208.5, "chaos": 8.55})
        self.assertEqual(len(p["currencies"]), 2)     # the None-id line dropped
        alch = next(c for c in p["currencies"] if c["id"] == "alch")
        self.assertEqual(alch["name"], "Orb of Alchemy")   # joined from items[]
        self.assertEqual(alch["divine"], 0.0031)
        self.assertEqual(alch["change7d"], 37.56)

    def test_economy_payload_failsafe_on_empty(self):
        p = distill._economy_payload({}, "2026-06-19T00:00:00+00:00")
        self.assertEqual(p["currencies"], [])
        self.assertEqual(p["rates"], {})


class ArtifactLockstep(unittest.TestCase):
    def test_manifest_matches_build_files_and_variants_resolve(self):
        builds_dir = os.path.join(ROOT, "builds")
        mani_path = os.path.join(builds_dir, "index.json")
        if not os.path.exists(mani_path):
            self.skipTest("no manifest")
        with open(mani_path, encoding="utf-8") as f:
            manifest = set(json.load(f))
        files = {n[:-len(".build")] for n in os.listdir(builds_dir) if n.endswith(".build")}
        self.assertEqual(manifest, files, "builds/index.json must list exactly the .build files (no orphans)")
        mdp = os.path.join(ROOT, "meta-detail.json")
        if os.path.exists(mdp):
            with open(mdp, encoding="utf-8") as f:
                md = json.load(f)
            for _slug, e in (md.get("byAsc") or {}).items():
                for v in (e.get("variants") or []):
                    self.assertIn(v["slug"], manifest, f"variant {v['slug']} not in manifest")
                    self.assertTrue(os.path.exists(os.path.join(builds_dir, v["slug"] + ".build")),
                                    f"variant {v['slug']} has no .build file")


class Guides(unittest.TestCase):
    def test_schema_errors_catches_bad_entries(self):
        ok = {"patch":"0.5.0","guides":{"deadeye":{"url":"https://x.gg","source":"Maxroll"}},"unguided":["lich"]}
        self.assertEqual(distill.guides_schema_errors(ok), [])
        bad = {"guides":{"deadeye":{"url":"ftp://x","source":""}, "titan":{"source":"M"}}, "unguided":"nope"}
        errs = distill.guides_schema_errors(bad)
        self.assertTrue(any("deadeye" in e for e in errs))   # bad url + empty source
        self.assertTrue(any("titan" in e for e in errs))     # missing url
        self.assertTrue(any("unguided" in e for e in errs))  # not a list
        # a slug in both guides and unguided is an error
        both = {"guides":{"deadeye":{"url":"https://x","source":"M"}}, "unguided":["deadeye"]}
        self.assertTrue(any("both" in e.lower() for e in distill.guides_schema_errors(both)))
        # leveling keys are OPTIONAL — a doc with none still validates clean
        self.assertEqual(distill.guides_schema_errors(
            {"guides":{"deadeye":{"url":"https://x.gg","source":"Maxroll"}}}), [])
        # a valid leveling map + levelingUnguided validates clean
        okl = {"guides":{"deadeye":{"url":"https://x.gg","source":"Maxroll"}},
               "leveling":{"deadeye":{"url":"https://x.gg/lvl","source":"Maxroll"}},
               "levelingUnguided":["titan"]}
        self.assertEqual(distill.guides_schema_errors(okl), [])
        # bad leveling: non-http url + empty source, and a non-list levelingUnguided
        badl = {"guides":{"deadeye":{"url":"https://x.gg","source":"M"}},
                "leveling":{"oracle":{"url":"ftp://x","source":""}},
                "levelingUnguided":"nope"}
        el = distill.guides_schema_errors(badl)
        self.assertTrue(any("oracle" in e for e in el))            # bad url + empty source
        self.assertTrue(any("levelingUnguided" in e for e in el))  # not a list
        # a slug in both leveling and levelingUnguided is an error
        bothl = {"guides":{"deadeye":{"url":"https://x","source":"M"}},
                 "leveling":{"oracle":{"url":"https://x","source":"M"}},
                 "levelingUnguided":["oracle"]}
        self.assertTrue(any("both leveling" in e.lower()
                            for e in distill.guides_schema_errors(bothl)))

    def test_untriaged_lists_only_unhandled_live_ascendancies(self):
        payload = {"default":"sc","leagues":[
            {"url":"sc","builds":[{"asc":"Deadeye"},{"asc":"Titan"},{"asc":"Smith of Kitava"}]},
            {"url":"std","curated":True,"builds":[{"asc":"Lich"}]},
        ]}
        doc = {"guides":{"deadeye":{"url":"https://x","source":"M"}}, "unguided":["titan"]}
        # Deadeye guided, Titan unguided, Smith untriaged, Lich is curated-only (ignored)
        self.assertEqual(distill.untriaged_guides(payload, doc), ["smith-of-kitava"])

    def test_untriaged_tolerates_bad_payload(self):
        self.assertEqual(distill.untriaged_guides(None, {"guides":{}, "unguided":[]}), [])
        self.assertEqual(distill.untriaged_guides({}, None), [])

    def test_shipped_guides_json_valid_and_complete(self):
        # the committed guides.json must be well-formed AND cover every live ascendancy
        # (each in guides or unguided) — an untriaged new ascendancy fails CI, the reminder bite.
        gpath = os.path.join(ROOT, "guides.json")
        if not os.path.exists(gpath):
            self.skipTest("guides.json not present")
        with open(gpath, encoding="utf-8") as f:
            doc = json.load(f)
        self.assertEqual(distill.guides_schema_errors(doc), [], "guides.json has schema errors")
        if os.path.exists(DATA_PATH):
            payload = load_data()
            self.assertEqual(distill.untriaged_guides(payload, doc), [],
                             "every live ascendancy must be in guides.json's guides or unguided — add the new one(s)")


class LandingTwitter(unittest.TestCase):
    def test_landing_html_has_twitter_card(self):
        h = distill.landing_html("Deadeye", "Ranger", "bow striker", ["Lightning Arrow"], weapon="Bow / Quiver")
        self.assertIn('name="twitter:card" content="summary_large_image"', h)
        self.assertIn('name="twitter:title"', h)
        self.assertIn('name="twitter:description"', h)
        self.assertIn('name="twitter:image" content="https://tincturepoe2.com/docs/og.png"', h)


class WeaponLabel(unittest.TestCase):
    def test_dominant_weapon_gates_weak_and_unknown(self):
        self.assertEqual(distill._dominant_weapon({"weapons": [{"name": "Bow / Quiver", "pct": 87.6}]}), "Bow / Quiver")
        self.assertEqual(distill._dominant_weapon({"weapons": [{"name": "Crossbow", "pct": 30.0}]}), "Crossbow")  # exactly at threshold
        self.assertIsNone(distill._dominant_weapon({"weapons": [{"name": "Staff", "pct": 15}]}))                 # weak plurality
        self.assertIsNone(distill._dominant_weapon({"weapons": [{"name": "Unknown / Sceptre", "pct": 45}]}))     # unclassified main
        self.assertIsNone(distill._dominant_weapon({"weapons": [{"name": "Dual Unknown", "pct": 41.7}]}))
        self.assertIsNone(distill._dominant_weapon({"weapons": []}))
        self.assertIsNone(distill._dominant_weapon({}))

    def test_landing_html_weapon_wording_is_honest(self):
        dom = distill.landing_html("Deadeye", "Ranger", "bow", ["Lightning Arrow"], weapon="Bow / Quiver")
        self.assertIn("Most-played weapon: Bow / Quiver.", dom)
        self.assertNotIn("Typically a", dom)
        none = distill.landing_html("Titan", "Warrior", "slam", ["Sunder"], weapon=None)
        self.assertNotIn("Most-played weapon", none)
        self.assertNotIn("Typically a", none)
        self.assertNotIn("Unknown", none)


if __name__ == "__main__":
    unittest.main(verbosity=2)

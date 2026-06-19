#!/usr/bin/env node
/*
 * build-from-ninja.cjs — reconstruct a LOADABLE GGG .build from a public poe.ninja
 * PoE2 ladder character, then QA it for cohesion. This is the engine behind real Decant.
 *
 * Why node (not the stdlib-Python pipeline): this generator is developed + tested locally
 * (Python isn't installed here), it is NOT on the hourly path, and its output is static
 * committed builds/*.build files the front end already serves. Keep it isolated from the
 * Python meta pipeline.
 *
 * Data sources (all public, fetched at runtime — nothing vendored):
 *   - Build:  GET https://poe.ninja/poe2/api/builds/{version}/character?overview=&account=&name=
 *             (open/unauth; passiveSelection = numeric GGG node ids, full skills + items)
 *   - Passive slug map:  GGG skill-tree export (node.skill -> node.id slug)
 *   - Gem metadata paths: PoB2 src/Data/Gems.lua (display name -> gameId)
 *   - Ascendancy codes:  inlined, cross-confirmed from the tree export (matches buildfile.py)
 *
 * Honesty (per the legal sweep): a per-character build is public-ladder data identified by
 * its character name — we IDENTIFY the source (character + account + poe.ninja link) in the
 * build's author/description, never byline it as Tincture's own. GGG owns the IP.
 *
 * Usage:
 *   node tools/build-from-ninja.cjs --account <acct> --name <char> --slug <out-slug> [--league runesofaldur]
 *   node tools/build-from-ninja.cjs --from-cache <char.json> --slug <out-slug>   (offline dev)
 */
'use strict';
const https = require('https');
const fs = require('fs');
const path = require('path');

const UA = 'Tincture/0.5.0 (+https://github.com/luther-rotmg/Tincture; contact: ryan.duke360@gmail.com) build-reconstructor';
const TREE_URL = 'https://raw.githubusercontent.com/grindinggear/poe2-skilltree-export/0.5.2/data.json';
const GEMS_URL = 'https://raw.githubusercontent.com/PathOfBuildingCommunity/PathOfBuilding-PoE2/dev/src/Data/Gems.lua';
const BASEITEMS_URL = 'https://repoe-fork.github.io/poe2/base_items.json'; // live-game BaseItemTypes dump — authoritative gem-id keys for QA
const REPO = path.resolve(__dirname, '..');
const CACHE_DIR = path.join(__dirname, '.cache'); // gitignored; the Action runs fresh

// disk cache for tools/.cache. `producer` is an async () => Buffer|string fetched on a miss.
// Safe for CONTENT-ADDRESSED entries (snapshot-keyed searches, hash-keyed dictionaries) and the
// rarely-changing data dumps — never for index-state (must stay live to detect new snapshots).
async function diskCached(file, producer, bin) {
  const p = path.join(CACHE_DIR, file);
  if (fs.existsSync(p)) return bin ? fs.readFileSync(p) : fs.readFileSync(p, 'utf8');
  const d = await producer();
  fs.mkdirSync(CACHE_DIR, { recursive: true });
  fs.writeFileSync(p, d);
  return d;
}

// ---- meta-weapon matching ----
// poe.ninja's "weaponmode" is a "Main / Offhand" family name (e.g. "Mace / Shield",
// "Quarterstaff", "Wand / Sceptre"); base_items' item_class splits a weapon by hand
// ("One Hand Mace"/"Two Hand Mace") and calls the quarterstaff a "Warstaff". So to tell
// whether a character runs the dominant meta weapon, normalise BOTH sides to a single
// weapon FAMILY and compare those — substring matching against the raw strings silently
// (a) rejects every mace/sword/axe build (multi-word item_class) and (b) accepts offhands.
const OFFHAND = new Set(['Focus', 'Shield', 'Buckler', 'Quiver']); // never the "main weapon"
const weaponFamily = cls => {
  if (!cls) return null;
  const f = String(cls).replace(/^(?:One|Two) Hand /, '');
  return f === 'Warstaff' ? 'Quarterstaff' : f; // base_items name -> poe.ninja name
};
// poe.ninja weaponmode -> dominant MAIN-HAND family (token before " / "); null when the
// source can't classify it ("Unknown") — we then DON'T enforce the meta-weapon invariant.
const metaWeaponFamily = name => {
  const main = String(name || '').split('/')[0].trim();
  return !main || main === 'Unknown' ? null : weaponFamily(main);
};
// the character's main-hand weapon family (main set preferred, then the weapon swap); null
// if the only weapon-slot item is an offhand or its base type doesn't map to a class.
const charWeaponFamily = (char, weaponClass) => {
  if (!weaponClass) return null;
  const items = (char.items || []).map(it => it.itemData || it);
  for (const id of ['Weapon', 'Weapon2']) { // exact slots — /^Weapon/ also caught the swap (Weapon2) out of order
    const d = items.find(x => (x.inventoryId || '') === id && x.baseType);
    const fam = d && weaponFamily(weaponClass[d.baseType]);
    if (fam && !OFFHAND.has(fam)) return fam;
  }
  return null;
};

// ascendancy display name -> .build code (same table as scripts/buildfile.py ASCENDANCY_CODES)
const ASCENDANCY_CODES = {
  'Martial Artist':'Monk1','Invoker':'Monk2','Acolyte of Chayula':'Monk3',
  'Deadeye':'Ranger1','Pathfinder':'Ranger3',
  'Titan':'Warrior1','Warbringer':'Warrior2','Smith of Kitava':'Warrior3',
  'Infernalist':'Witch1','Blood Mage':'Witch2','Lich':'Witch3','Abyssal Lich':'Witch3b',
  'Stormweaver':'Sorceress1','Chronomancer':'Sorceress2','Disciple of Varashta':'Sorceress3',
  'Tactician':'Mercenary1','Witchhunter':'Mercenary2','Gemling Legionnaire':'Mercenary3',
  'Amazon':'Huntress1','Spirit Walker':'Huntress2','Ritualist':'Huntress3',
  'Oracle':'Druid1','Shaman':'Druid2',
};
// poe.ninja item.inventoryId -> .build inventory_id (main weapon set only; runes/2nd set skipped)
const SLOT_MAP = {
  Weapon:'Weapon1', Weapon2:'Weapon2', Helm:'Helm1', BodyArmour:'BodyArmour1',
  Gloves:'Gloves1', Boots:'Boots1', Belt:'Belt1', Amulet:'Amulet1', Ring:'Ring1', Ring2:'Ring2',
};

function get(url, binary, attempt) {
  attempt = attempt || 0;
  return new Promise((res, rej) => {
    const u = new URL(url);
    let settled = false, hard;
    const ok   = v => { if (settled) return; settled = true; clearTimeout(hard); res(v); };
    const fail = e => { if (settled) return; settled = true; clearTimeout(hard); rej(e); };
    const retry = wait => { if (settled) return; settled = true; clearTimeout(hard); setTimeout(() => get(url, binary, attempt + 1).then(res, rej), wait); };
    const req = https.get({ hostname:u.hostname, path:u.pathname+u.search, headers:{ 'User-Agent':UA, 'Accept':'*/*', 'Referer':'https://poe.ninja/poe2/builds' } }, r => {
      if (r.statusCode >= 300 && r.statusCode < 400 && r.headers.location) { if (settled) return; settled = true; clearTimeout(hard); return get(new URL(r.headers.location, url).href, binary, attempt).then(res, rej); }
      const ch = []; r.on('data', c => ch.push(c)); r.on('end', () => {
        const b = Buffer.concat(ch);
        if (r.statusCode === 429 && attempt < 5) { // respect the throttle: capped backoff + retry
          const ra = Number(r.headers['retry-after']);  // seconds (or NaN for an HTTP-date / absent)
          return retry(Math.min(60000, (ra > 0 ? ra : 3 * (attempt + 1)) * 1000));  // CAP so a hostile Retry-After can't freeze the run for an hour
        }
        if (r.statusCode !== 200) return fail(new Error('HTTP ' + r.statusCode));
        ok(binary ? b : b.toString('utf8'));
      });
    });
    req.on('error', fail);
    // HARD wall-clock cap: req.setTimeout is socket-IDLE only, which a slow byte-drip dodges
    // forever (the real cause of the 40-min freeze). This timer fires regardless of activity.
    hard = setTimeout(() => { req.destroy(new Error('request timeout')); fail(new Error('request timeout')); }, 30000);
  });
}

// ---- data maps ----
function slugMapFromTree(tree) {
  const m = {};
  for (const [k, n] of Object.entries(tree.nodes)) if (k !== 'root' && n && n.id != null && n.skill != null) m[n.skill] = String(n.id);
  return m;
}
function gemMapFromLua(lua) {
  const m = {};
  const re = /\[\s*"([^"]+)"\s*\]\s*=\s*\{([\s\S]*?)\n\t\},/g; // tab-indented entry close
  let x;
  while ((x = re.exec(lua))) {
    const body = x[2];
    const name = (body.match(/name\s*=\s*"([^"]*)"/) || [])[1];
    const gameId = (body.match(/gameId\s*=\s*"([^"]*)"/) || [])[1];
    // Copy gameId VERBATIM — it is the live game's BaseItemTypes id and is
    // authoritative per gem. Verified against the BaseItemTypes dump
    // (repoe-fork base_items.json): the singular/plural split (Items/Gem vs
    // Items/Gems) is real and fixed per gem, AND the lowercase-`items` form
    // (SkillGemStaffConsecrate / SkillGemStaffUnleash) is genuine game data, not a
    // PoB typo. Normalizing either the casing or the plural makes the id miss the
    // game's table, so the planner can't scope the skill and shows the FULL gem
    // catalog. Never normalize. Only require that it's a real gem metadata path
    // (either Items/items casing); never fall back to the Lua key x[1] (not loadable).
    if (name && /^Metadata\/[Ii]tems\/Gems?\//.test(gameId || '')) m[name] = gameId;
  }
  return m;
}

// ---- conversion ----
function itemText(d) {
  // rare/magic/normal: base type + identifiable mod lines (implicit then explicit)
  const lines = [d.baseType || d.typeLine || d.name || 'Item'];
  const mods = [].concat(d.implicitMods || [], d.explicitMods || [], d.runeMods || []);
  mods.forEach((mm, i) => lines.push(`${i + 1}. ${mm}`));
  return lines.join('\n');
}

function convert(char, { slug, gem, account, name, league }) {
  const ascName = char.class || '';
  const code = ASCENDANCY_CODES[ascName];
  if (!code) throw new Error(`unmapped ascendancy ${JSON.stringify(ascName)} — refusing (would be unloadable)`);

  // passives: shared selection (no weapon_set) + per-weapon-set additions
  const passives = [];
  const pushNodes = (ids, ws) => (ids || []).forEach(id => {
    const s = slug[id];
    if (s == null) return; // never invent — drop an unmapped id (and the QA flags coverage)
    const p = { id: s };
    if (ws) p.weapon_set = ws;
    passives.push(p);
  });
  pushNodes(char.passiveSelection, 0);
  pushNodes(char.passiveSelectionSet1, 1);
  pushNodes(char.passiveSelectionSet2, 2);

  // the plain character-Level requirement (poe.ninja itemData.requirements type 62, NOT the
  // "(gem)" row); gates when a gem/item appears in the in-game leveling guide. 1 when absent.
  const levelReq = itemData => {
    const r = ((itemData || {}).requirements || []).find(q => (q.type === 62 || q.name === 'Level') && !/\(gem\)/.test(q.suffix || ''));
    const n = parseInt(r && r.values && r.values[0] && r.values[0][0], 10);
    return Number.isInteger(n) && n > 1 ? n : 1;
  };

  // skills: each group = one active SkillGem + its SupportGems. Track the highest-DPS
  // group's gem as the headline "main skill" for naming (ascendancy buffs like Hollow
  // Focus report ~0 dps, so they won't be mistaken for the main skill).
  const skills = [], dpsOf = [], byActive = {};
  let mainSkillName = '', bestDps = -1;
  (char.skills || []).forEach(group => {
    // level_interval [min,100] = "appears in the leveling plan from character level min".
    // Gate by each gem's REAL Level requirement so the plan stops slotting endgame gems at
    // level 1. Honest: gates by the snapshot gem's own requirement; we never invent a path.
    // Supports report only attribute reqs (no Level row) → fall back to [1,100].
    const gems = (group.allGems || []).map(g => ({ name: g.name, level: g.level, id: gem[g.name], req: levelReq(g.itemData) })).filter(g => g.id);
    const active = gems.find(g => /\/SkillGem/i.test(g.id));
    if (!active) return; // a group with no resolvable active skill is dropped
    if (/PlayerDefault/i.test(active.id)) return; // innate/default attack, not a real build gem
    const supports = gems.filter(g => g !== active && /\/SupportGem/i.test(g.id));
    const skill = { id: active.id, level_interval: [active.req, 100] };
    if (supports.length) skill.support_skills = supports.map(s => ({ id: s.id, level_interval: [s.req, 100] }));
    // group.dps is an array of {name, dps, ...}; take the group's peak dps
    const dps = Array.isArray(group.dps) ? Math.max(0, ...group.dps.map(d => Number(d && d.dps) || 0)) : (Number(group.dps) || 0);
    // dedupe repeated active gems, keeping the HIGHER-DPS configuration — PoE2 can run the
    // same skill twice with different supports, so don't let an inferior first-seen copy win.
    const prev = byActive[active.id];
    if (prev !== undefined) { if (dps > dpsOf[prev]) { skills[prev] = skill; dpsOf[prev] = dps; } }
    else { byActive[active.id] = skills.length; skills.push(skill); dpsOf.push(dps); }
    if (dps > bestDps) { bestDps = dps; mainSkillName = active.name; }
  });

  // inventory: equipment in the main weapon set (skip runes / 2nd-set offhands). First item
  // per destination slot wins (dedupe, mirroring the gem/passive dedupe). Rare/magic gear
  // gates by its own required level so endgame gear isn't shown from level 1 in the guide.
  const inv = [], seenSlot = {};
  (char.items || []).forEach(it => {
    const d = it.itemData || it;
    const dest = SLOT_MAP[d.inventoryId];
    if (!dest || seenSlot[dest]) return;
    seenSlot[dest] = true;
    if (d.frameType === 3 && d.name) inv.push({ inventory_id: dest, unique_name: d.name, slot_x: 0, slot_y: 0 });
    else inv.push({ inventory_id: dest, additional_text: itemText(d), level_interval: [levelReq(d), 100], slot_x: 0, slot_y: 0 });
  });

  const buildName = `${ascName}${mainSkillName ? ' — ' + mainSkillName : ''} (public ladder)`;
  // Exactly these seven top-level keys are served (name/author/description/ascendancy/
  // passives/skills/inventory_slots). The game tolerates `description`; do NOT add other
  // top-level keys (provenance lives in author/description + the meta-detail sidecar).
  return {
    name: buildName,
    author: `Tincture — reconstructed from public ladder character "${name}" (${account})`,
    description:
      `A representative ${ascName} build from the public ${league} ladder (character "${name}", account "${account}", level ${char.level || '?'}), ` +
      `reconstructed by Tincture from poe.ninja: https://poe.ninja/poe2/builds/${league}/character/${encodeURIComponent(account)}/${encodeURIComponent(name)} . ` +
      `Path of Exile and its assets are owned by Grinding Gear Games; this tool isn't affiliated with or endorsed by GGG.`,
    ascendancy: code,
    passives,
    skills,
    inventory_slots: inv,
  };
}

// ---- QA: catch conversion errors + cheap cohesion checks ----
function qa(build, char, { slug, tree, baseItems, md, weaponClass }) {
  const issues = [];
  const warn = m => issues.push({ sev: 'warn', m });
  const fail = m => issues.push({ sev: 'fail', m });

  if (!build.name) fail('missing name');
  if (!build.ascendancy || !Object.values(ASCENDANCY_CODES).includes(build.ascendancy)) fail(`ascendancy code ${build.ascendancy} not confirmed`);

  // passive coverage: every selected id must have mapped (no silent drops)
  const allIds = [...new Set([].concat(char.passiveSelection||[], char.passiveSelectionSet1||[], char.passiveSelectionSet2||[]))];
  const dropped = allIds.filter(id => slug[id] == null);
  if (dropped.length) fail(`${dropped.length} passive ids did not map to slugs (would lose tree)`);

  // counts — PoE2 budgets: shared normal nodes ~123 (level+quest), each weapon set up to 24
  // weapon-set points, and up to 8 ASCENDANCY points (the "Start" anchor is free, not a point).
  const isAsc = s => /^Ascendancy/i.test(s);
  const isStart = s => /Start$/i.test(s);
  const shared = build.passives.filter(p => !isAsc(p.id) && p.weapon_set == null);
  const ws1 = build.passives.filter(p => p.weapon_set === 1);
  const ws2 = build.passives.filter(p => p.weapon_set === 2);
  const ascAll = build.passives.filter(p => isAsc(p.id));
  const ascPts = ascAll.filter(p => !isStart(p.id));
  // These builds are REAL level-100 ladder characters — inherently valid in-game — so the
  // approximate game-rule caps are WARNINGS (flag anomalies); only absurd values, which
  // would mean a conversion bug, hard-fail. The empty-tree guard stays a hard fail.
  const sharedUnique = new Set(shared.map(p => p.id)).size;
  if (sharedUnique < 20) fail(`only ${sharedUnique} passive nodes — conversion produced an empty/broken tree`);
  else if (sharedUnique > 160) fail(`shared normal nodes ${sharedUnique} absurdly high — likely a conversion bug`);
  else if (sharedUnique > 123) warn(`shared normal nodes ${sharedUnique} above the ~123 estimate`);
  if (ws1.length > 30 || ws2.length > 30) fail(`weapon-set nodes ${ws1.length}/${ws2.length} absurdly high`);
  const ascUnique = new Set(ascPts.map(p => p.id)).size;
  if (ascUnique > 12) fail(`ascendancy points ${ascUnique} absurdly high`);
  else if (ascUnique > 8) warn(`ascendancy points ${ascUnique} above the 8 estimate`);

  // ascendancy-name binding (warn only): node prefixes mostly match the code, but some
  // pairs differ in the tree data (e.g. Abyssal Lich code Witch3b vs nodes AscendancyWitch3*).
  const base = build.ascendancy.replace(/[a-z]+$/, ''); // Witch3b -> Witch3
  const stray = [...new Set(ascAll.map(p => p.id))].filter(s => !s.includes(build.ascendancy) && !s.includes('Ascendancy' + base));
  if (stray.length) warn(`ascendancy nodes not bound to ${build.ascendancy}/${base}: ${stray.slice(0,3).join(', ')}`);

  // tree connectivity: allocated NORMAL nodes connect to the class start through each other
  try {
    const conn = connectivity(build, char, tree);
    if (conn.orphans > 0) warn(`${conn.orphans} normal nodes not connected to class start (orphans)`);
    if (!conn.startFound) warn('could not locate class-start node for connectivity check');
  } catch (e) { warn('connectivity check skipped: ' + e.message); }

  // skills
  if (!build.skills.length) fail('no skills');
  const mainish = build.skills.some(s => /\/SkillGem/i.test(s.id));
  if (!mainish) fail('no active skill gem present');
  build.skills.forEach((s, i) => {
    const sup = s.support_skills || [];
    if (sup.length > 5) fail(`skill ${i} has ${sup.length} supports > 5`);
    const ids = sup.map(x => x.id.replace(/(One|Two|Three|Four|Five)$/, ''));
    if (new Set(ids).size !== ids.length) warn(`skill ${i} has duplicate supports`);
    sup.forEach(x => { if (!/\/SupportGem/i.test(x.id)) fail(`skill ${i} support is not a SupportGem: ${x.id}`); });
    // every gem id must be a VERBATIM BaseItemTypes key, or the in-game planner can't
    // resolve it and falls back to the full gem catalog. An unresolved ACTIVE skill gem
    // breaks support scoping for the whole group → hard fail; a stray support → warn.
    if (baseItems) {
      if (!baseItems.has(s.id)) fail(`skill ${i} id not a live BaseItemTypes key (would not load): ${s.id}`);
      sup.forEach(x => { if (!baseItems.has(x.id)) warn(`skill ${i} support id not a live BaseItemTypes key: ${x.id}`); });
    }
  });

  // items
  const slots = build.inventory_slots.map(s => s.inventory_id);
  const single = ['Weapon1','Helm1','BodyArmour1','Gloves1','Boots1','Belt1','Amulet1'];
  single.forEach(sl => { if (slots.filter(s => s === sl).length > 1) fail(`slot ${sl} occupied more than once`); });
  if (slots.filter(s => s === 'Ring1' || s === 'Ring2').length > 2) fail('more than 2 rings');
  build.inventory_slots.forEach(s => { if (!Object.values(SLOT_MAP).includes(s.inventory_id)) fail(`unknown inventory slot ${s.inventory_id}`); });

  // stats<->build overlap invariant: the served build MUST run the ascendancy's DOMINANT meta
  // weapon (#1 weaponmode), so a .build never contradicts the stats panel (e.g. a spear Monk
  // served for a 63%-quarterstaff ascendancy). Compared by weapon FAMILY (see weaponFamily).
  // Hard-fails an off-weapon pick → honest template served instead of a misleading build.
  // Skipped when meta context is absent or the meta weapon is unclassifiable ("Unknown").
  if (md && weaponClass && md.weapons && md.weapons[0]) {
    const metaFam = metaWeaponFamily(md.weapons[0].name);
    const haveFam = charWeaponFamily(char, weaponClass);
    if (metaFam && haveFam !== metaFam) fail(`build weapon ${haveFam || '?'} != dominant meta weapon ${md.weapons[0].name} [${md.weapons[0].pct}%] — stats/build mismatch`);
  }

  return { ok: !issues.some(i => i.sev === 'fail'), issues, stats: { sharedUnique, ws1: ws1.length, ws2: ws2.length, ascUnique, skills: build.skills.length, items: build.inventory_slots.length } };
}

// connectivity over the real tree graph (nodes + out/in adjacency + per-class start)
function connectivity(build, char, tree) {
  const slugToSkill = {}; // slug -> numeric node id
  for (const [k, n] of Object.entries(tree.nodes)) if (k !== 'root' && n && n.id != null && n.skill != null) slugToSkill[String(n.id)] = Number(n.skill);
  const adj = {}; // numeric -> Set(numeric)
  for (const [k, n] of Object.entries(tree.nodes)) {
    if (k === 'root' || !n || n.skill == null) continue;
    const id = Number(n.skill); adj[id] = adj[id] || new Set();
    (n.out || []).concat(n.in || []).forEach(o => { const t = Number(tree.nodes[o] && tree.nodes[o].skill); if (!Number.isNaN(t)) { adj[id].add(t); (adj[t] = adj[t] || new Set()).add(id); } });
  }
  // class-start node: the tree's "root.out" links to the 6 class start nodes; pick the one matching baseClass
  const startSkills = (tree.nodes.root && tree.nodes.root.out || []).map(o => Number(tree.nodes[o] && tree.nodes[o].skill)).filter(n => !Number.isNaN(n));
  const allocated = new Set(build.passives.filter(p => !/^Ascendancy/i.test(p.id) && p.weapon_set == null).map(p => slugToSkill[p.id]).filter(n => n != null));
  // find a start node that is adjacent to / among the allocated set
  let start = startSkills.find(s => allocated.has(s));
  if (start == null) start = startSkills.find(s => [...(adj[s] || [])].some(a => allocated.has(a)));
  if (start == null) return { startFound: false, orphans: 0 };
  // BFS from start through allocated-only
  const seen = new Set([start]); const q = [start];
  while (q.length) { const cur = q.pop(); for (const nb of (adj[cur] || [])) if (allocated.has(nb) && !seen.has(nb)) { seen.add(nb); q.push(nb); } }
  const orphans = [...allocated].filter(a => !seen.has(a)).length;
  return { startFound: true, orphans };
}

// front-end slug (must match index.html slugOf with a blank skill)
const slugify = asc => `${asc}-`.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const charUrl = (sv, account, name) =>
  `https://poe.ninja/poe2/api/builds/${sv.version}/character?overview=${sv.snapshotName}&account=${encodeURIComponent(account)}&name=${encodeURIComponent(name)}`;

async function getSnapshot(league) {
  const idx = JSON.parse(await get('https://poe.ninja/poe2/api/data/index-state'));
  return (idx.snapshotVersions || []).find(s => s.url === league) || idx.snapshotVersions[0];
}
// --cache-only: recover the snapshot id from the cached global-search filename
// (s-<version>-_global.bin) so we never touch the network. snapshotName (the league overview)
// is only used to build URLs, which cache-only never fetches, so the league value is fine.
function snapshotFromCache(cacheDir, league) {
  const f = fs.readdirSync(cacheDir).find(n => /^s-.*-_global\.bin$/.test(n));
  const m = f && f.match(/^s-(.+)-_global\.bin$/);
  if (!m) throw new Error('cache-only: no cached global search (run a live --enumerate first)');
  return { version: m[1], snapshotName: league, url: league };
}

// minimal protobuf reader — enough to pull the named string value_lists from /search
function pbFields(b) {
  const out = []; let i = 0;
  const vint = (p) => { let r = 0, s = 0; while (p < b.length) { const x = b[p++]; r += (x & 0x7f) * 2 ** s; if (!(x & 0x80)) return [r, p]; s += 7; } return [0, -1]; };
  while (i < b.length) {
    const [t, ni] = vint(i); if (ni < 0) break; i = ni; const f = t >>> 3, wt = t & 7;
    if (wt === 0) { const [v, n] = vint(i); if (n < 0) break; i = n; out.push({ f, wt, v }); }
    else if (wt === 2) { const [len, n] = vint(i); if (n < 0 || n + len > b.length) break; out.push({ f, wt, data: b.slice(n, n + len) }); i = n + len; }
    else if (wt === 5) { i += 4; } else if (wt === 1) { i += 8; } else break;
  }
  return out;
}
const strf = (ff, f) => { const d = (ff.find(x => x.f === f && x.wt === 2) || {}).data; return d ? d.toString('utf8') : null; };
const numf = (ff, f) => (ff.find(x => x.f === f && x.wt === 0) || {}).v || 0;
const searchBase = sv => `https://poe.ninja/poe2/api/builds/${sv.version}/search?overview=${sv.snapshotName}`;

// full /search protobuf parse → { total, dims{id:[{key,count}]}, dicts{id:hash}, vls{id:[str]} }
function parseSearch(buf) {
  const result = (pbFields(buf).find(x => x.f === 1 && x.wt === 2) || {}).data;
  if (!result) return null;
  const rf = pbFields(result), dims = {}, dicts = {}, vls = {};
  rf.filter(x => x.f === 2 && x.wt === 2).forEach(d => { const ff = pbFields(d.data); const id = strf(ff, 1); if (id) dims[id] = ff.filter(x => x.f === 3 && x.wt === 2).map(c => { const cf = pbFields(c.data); return { key: numf(cf, 1), count: numf(cf, 2) }; }); });
  rf.filter(x => x.f === 6 && x.wt === 2).forEach(d => { const ff = pbFields(d.data); const id = strf(ff, 1); if (id) dicts[id] = strf(ff, 2); });
  rf.filter(x => x.f === 5 && x.wt === 2).forEach(d => { const ff = pbFields(d.data); const id = strf(ff, 1); if (id) vls[id] = ff.filter(x => x.f === 2 && x.wt === 2).map(v => strf(pbFields(v.data), 1)); });
  return { total: numf(rf, 1), dims, dicts, vls };
}

const _dictCache = {};
// dictionaries are content-addressed by hash → disk-cache them (dict-<hash>.bin) so a throttled
// run resumes nearly free; without this, extractMeta re-fetched every dictionary on each run.
async function dictNames(hash) { if (!hash) return []; if (_dictCache[hash]) return _dictCache[hash]; const b = await diskCached(`dict-${hash}.bin`, () => get(`https://poe.ninja/poe2/api/builds/dictionary/${hash}`, true), true); _dictCache[hash] = pbFields(b).filter(x => x.f === 2 && x.wt === 2).map(x => x.data.toString('utf8')); return _dictCache[hash]; }

const _num = s => { if (!s) return null; const m = String(s).match(/([\d.]+)\s*([km])?/i); return m ? Math.round(parseFloat(m[1]) * (m[2] ? (m[2].toLowerCase() === 'm' ? 1e6 : 1e3) : 1)) : null; };
const _median = a => { const n = (a || []).map(_num).filter(x => x != null).sort((x, y) => x - y); return n.length ? n[Math.floor(n.length / 2)] : null; };

// strip poe.ninja's [tag|Display] / [Tag] markup; normalise an affix to its TYPE (numbers -> #)
const cleanMod = m => String(m).replace(/\[[^\]|]+\|([^\]]+)\]/g, '$1').replace(/\[([^\]]+)\]/g, '$1');
const normMod = m => cleanMod(m).replace(/\d+(\.\d+)?/g, '#').replace(/\s+/g, ' ').trim();

// aggregate a sample of /character objects -> "values to chase" (top gear affixes) + top runes.
// Affixes are taken from RARE/MAGIC items only (uniques have fixed mods you don't roll, and
// would otherwise dominate a small sample at ~100%); runes are real Rune/Soul Core socketables
// (not socketed skills). frameType: 1=magic, 2=rare, 3=unique, 5=rune.
function aggregateGear(chars) {
  // Affixes are counted PER GEAR PIECE (% of the sample's rare/magic items carrying each) —
  // counting per-character saturates at 100% (everyone has resistances/life somewhere).
  // Runes are counted per character (% of sampled builds socketing each weapon rune).
  const modItems = {}, modVals = {}, runeChars = {};
  let rareItems = 0;
  for (const ch of chars) {
    const runes = new Set();
    for (const it of (ch.items || [])) {
      const d = it.itemData || it;
      if (d.frameType === 1 || d.frameType === 2) {
        rareItems++;
        const seen = new Set();
        (d.explicitMods || []).forEach(m => {
          const k = normMod(m);
          if (k.length > 6 && k.length < 56 && !seen.has(k)) {
            seen.add(k); modItems[k] = (modItems[k] || 0) + 1;
            // capture the rolled value only for single-number affixes (so we can show a range)
            const nums = (cleanMod(m).match(/\d+(\.\d+)?/g) || []).map(Number);
            if (nums.length === 1) (modVals[k] = modVals[k] || []).push(nums[0]);
          }
        });
      }
      if (/^Weapon/.test(d.inventoryId || '')) (d.socketedItems || []).forEach(soc => { const nm = soc.typeLine || soc.baseType; if (nm && /\bRune\b|Soul Core/i.test(nm)) runes.add(nm); });
    }
    runes.forEach(r => runeChars[r] = (runeChars[r] || 0) + 1);
  }
  const ri = rareItems || 1, n = chars.length || 1;
  const topMods = Object.entries(modItems).sort((a, b) => b[1] - a[1]).slice(0, 8).map(([name, c]) => {
    const e = { name, pct: Math.round(c / ri * 1000) / 10 };
    const vals = (modVals[name] || []).slice().sort((x, y) => x - y);
    if (vals.length >= 3) { e.lo = vals[Math.floor(vals.length * 0.25)]; e.hi = vals[Math.floor(vals.length * 0.75)]; }  // interquartile range of rolled values
    return e;
  });
  const topRunes = Object.entries(runeChars).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([name, c]) => ({ name, pct: Math.round(c / n * 1000) / 10 }));
  return { gear: topMods, runes: topRunes, sampled: chars.length };
}

// readable skill setups for ONE character: [{skill, supports[]}] in display names, dps-sorted
function readableSkills(char) {
  return (char.skills || [])
    .map(g => {
      const gems = (g.allGems || []).map(x => x.name).filter(Boolean);
      const dps = Array.isArray(g.dps) ? Math.max(0, ...g.dps.map(d => Number(d && d.dps) || 0)) : 0;
      return gems.length ? { skill: gems[0], supports: gems.slice(1), dps } : null;
    })
    .filter(Boolean).sort((a, b) => b.dps - a.dps).slice(0, 6)
    .map(({ skill, supports }) => ({ skill, supports }));
}
// the character's equipped items (readable) in the .build's slots, WITH per-item detail
// (base / item level / rarity / affixes / socketed augments) for the hover tooltip.
function buildItems(char) {
  const rar = ft => ft === 3 ? 'Unique' : ft === 1 ? 'Magic' : ft === 0 ? 'Normal' : 'Rare';
  const clean = a => (a || []).map(cleanMod).filter(Boolean);
  const out = [];
  for (const it of (char.items || [])) {
    const d = it.itemData || it;
    if (!SLOT_MAP[d.inventoryId]) continue;
    const o = { slot: SLOT_MAP[d.inventoryId], name: d.name || d.typeLine || d.baseType || 'Item', unique: d.frameType === 3, rarity: rar(d.frameType) };
    if (d.baseType && d.baseType !== o.name) o.base = d.baseType;
    if (d.ilvl) o.ilvl = d.ilvl;
    if (d.corrupted) o.corrupted = true;
    const enc = clean(d.enchantMods), imp = clean(d.implicitMods), exp = clean(d.explicitMods).concat(clean(d.fracturedMods));
    if (enc.length) o.enchants = enc;
    if (imp.length) o.implicits = imp;
    if (exp.length) o.explicits = exp;
    const sockets = (d.socketedItems || []).map(s => s.name || s.typeLine || s.baseType).filter(Boolean);
    if (sockets.length) o.sockets = sockets;
    out.push(o);
  }
  return out;
}

// parsed search → meta-detail shape: top skills / supports / notables / uniques / anointments / weapon + stats
async function extractMeta(s, gem) {
  const gemD = await dictNames(s.dicts.gem), kpD = await dictNames(s.dicts.keypassive), itD = await dictNames(s.dicts.item);
  const anD = await dictNames(s.dicts.anointed), wmD = await dictNames(s.dicts.weaponmode);
  const pct = c => Math.round(c / s.total * 1000) / 10;
  const topN = (dim, names, n, filt) => (s.dims[dim] || []).map(c => ({ name: names[c.key], pct: pct(c.count) })).filter(x => x.name && x.name !== 'Unknown' && (!filt || filt(x.name))).sort((a, b) => b.pct - a.pct).slice(0, n);
  const isSupport = nm => /\/SupportGem/i.test(gem[nm] || '');
  return {
    sample: s.total,
    skills: topN('skills', gemD, 6),
    supports: topN('allskills', gemD, 6, isSupport),
    notables: topN('keypassives', kpD, 6),
    uniques: topN('items', itD, 6, nm => !/^(Rare|Magic) /.test(nm)),
    anointments: topN('anointed', anD, 5),
    weapons: topN('weaponmode', wmD, 5),
    stats: { ehp: _median(s.vls.ehp), dps: _median(s.vls.dps) },
    top: { account: (s.vls.account || [])[0], name: (s.vls.name || [])[0] },
  };
}

function writeBuild(slug, build) {
  const outDir = path.join(REPO, 'builds');
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, slug + '.build'), JSON.stringify(build, null, 2) + '\n');
}
// the poe.ninja-supplied Path of Building import code, served on demand (kept out of
// meta-detail.json — it's ~12KB each — and fetched only when the user clicks "copy PoB").
function writePob(slug, code) {
  if (code) fs.writeFileSync(path.join(REPO, 'builds', slug + '.pob'), code);
}
function refreshManifest() {
  const outDir = path.join(REPO, 'builds');
  const slugs = fs.readdirSync(outDir).filter(f => f.endsWith('.build')).map(f => f.slice(0, -'.build'.length)).sort();
  fs.writeFileSync(path.join(outDir, 'index.json'), JSON.stringify(slugs, null, 2) + '\n');
  return slugs;
}

function buildOne(char, { gem, account, name, league, tree, slugMap, baseItems, md, weaponClass, quiet }) {
  const build = convert(char, { slug: slugMap, gem, account, name, league });
  const report = qa(build, char, { slug: slugMap, tree, baseItems, md, weaponClass });
  if (!quiet) { console.log('=== QA', JSON.stringify(report.stats)); report.issues.forEach(i => console.log(`  [${i.sev}] ${i.m}`)); }
  return { build, report };
}

// ---- CLI ----
async function main() {
  const args = require('process').argv.slice(2);
  const opt = {};
  for (let i = 0; i < args.length; i++) if (args[i].startsWith('--')) opt[args[i].slice(2)] = args[i + 1] && !args[i + 1].startsWith('--') ? args[++i] : true;
  const league = opt.league || 'runesofaldur';

  // data maps (prefer local cache in tools/.cache for dev; else fetch — never committed)
  const cacheDir = CACHE_DIR;
  // --cache-only: replay the last run's cached searches + character pulls with ZERO network
  // (rejects every cache miss). Lets a throttled run be finished deterministically offline.
  const cacheOnly = !!opt['cache-only'];
  const cached = (f, url, bin) => { if (cacheOnly && !fs.existsSync(path.join(cacheDir, f))) return Promise.reject(new Error('cache-only miss: ' + f)); return diskCached(f, () => get(url, bin), bin); };
  const tree = JSON.parse(await cached('tree.json', TREE_URL));
  const slugMap = slugMapFromTree(tree);
  const gem = gemMapFromLua(await cached('Gems.lua', GEMS_URL));
  // Authoritative live-game gem-id keys; QA rejects any emitted gem id missing here
  // (it would not resolve in-game → full-catalog fallback). Fail-soft if unavailable.
  let baseItems = null, weaponClass = null;
  try {
    const bi = JSON.parse(await cached('base_items.json', BASEITEMS_URL));
    baseItems = new Set(Object.keys(bi));
    weaponClass = {}; for (const v of Object.values(bi)) if (v && v.name && v.item_class) weaponClass[v.name] = v.item_class;
  } catch (e) { console.log('base_items.json unavailable — skipping gem-id validation & meta-weapon pick:', e.message); }
  // In --enumerate the result is committed for serving, so a missing base_items.json must NOT
  // silently disable the gem-id + meta-weapon QA (that could publish an off-meta build). Fatal.
  if (opt.enumerate && (!baseItems || !weaponClass)) throw new Error('base_items.json required for --enumerate (gem-id + meta-weapon QA) — refusing to write unvalidated builds');

  // ENUMERATE: class-driven — per ascendancy, one class-filtered search gives the meta
  // breakdown (top skills/supports/notables/uniques/stats) AND the top character, which we
  // reconstruct into a loadable build. Produces builds/*.build + meta-detail.json. Covers
  // niche ascendancies too (each is found via its own class filter).
  if (opt.enumerate) {
    // In --cache-only we can't ask poe.ninja for the live snapshot or the meta dictionaries, so
    // recover the snapshot id from the cache and source per-asc meta from the existing
    // meta-detail.json (extractMeta would hit the dictionary endpoint). Builds are still rebuilt
    // from cached character pulls, so the fix takes effect; only the meta breakdown is reused.
    const priorDetail = cacheOnly ? JSON.parse(fs.readFileSync(path.join(REPO, 'meta-detail.json'), 'utf8')) : null;
    const sv = cacheOnly ? snapshotFromCache(cacheDir, league) : await getSnapshot(league);
    console.log(`snapshot ${sv.version} (${sv.snapshotName})${cacheOnly ? ' [cache-only]' : ''}`);
    // poe.ninja throttles a fast burst (~60 live requests then a wall). Two defenses:
    //  (1) DISK CACHE searches + character pulls (keyed by snapshot) so a throttled run can be
    //      re-run and resume nearly free — no re-hammering. Failed fetches are NOT cached, so
    //      they retry next run. Cache lives in tools/.cache (gitignored; the Action runs fresh).
    //  (2) a periodic COOLDOWN every N live requests to let the rate-limit window refill.
    const san = s => String(s).replace(/[^a-z0-9]+/gi, '_').slice(0, 48);
    const hit = f => fs.existsSync(path.join(cacheDir, f));   // was this already on disk? (check BEFORE cached() writes it)
    let netReqs = 0;
    const onMiss = async (ms) => { if (cacheOnly) return; netReqs++; await sleep(ms); if (netReqs % 45 === 0) { console.log(`  … ${netReqs} live requests — cooling down 120s to respect poe.ninja's window`); await sleep(120000); } };
    // `updated` describes the META BREAKDOWN's age. In --cache-only the breakdown is reused from
    // the prior meta-detail.json (only builds are rebuilt), so carry its timestamp forward rather
    // than overstating freshness; `buildsUpdated` always records when builds were last rebuilt.
    const nowIso = new Date().toISOString();
    const meta = { updated: cacheOnly ? (priorDetail.updated || nowIso) : nowIso, buildsUpdated: nowIso, league, version: sv.version, total: 0, global: null, byAsc: {} };
    const gf = `s-${sv.version}-_global.bin`, gHit = hit(gf);
    if (cacheOnly) { meta.total = priorDetail.total; meta.global = priorDetail.global; console.log(`global: ${meta.total} chars [meta reused from meta-detail.json]`); }
    else {
      try { const g = parseSearch(await cached(gf, searchBase(sv), true)); meta.total = g.total; meta.global = await extractMeta(g, gem); console.log(`global: ${g.total} chars · top skill ${meta.global.skills[0] && meta.global.skills[0].name} ${meta.global.skills[0] && meta.global.skills[0].pct}%`); }
      catch (e) { console.log('global meta failed:', e.message); }
      if (!gHit) await onMiss(700);
    }
    const SAMPLE = opt['no-builds'] ? 0 : (Number(opt.sample) || 5);   // chars pulled per ascendancy (gear/rune sample; build is the #1)
    let builds = 0;
    const globalChars = [];
    for (const asc of Object.keys(ASCENDANCY_CODES)) {
      const slug = slugify(asc);
      let s;
      const sf = `s-${sv.version}-${slug}.bin`, sHit = hit(sf);
      try { s = parseSearch(await cached(sf, searchBase(sv) + '&class=' + encodeURIComponent(asc), true)); }
      catch (e) { console.log(`  - ${asc}: search ${e.message}`); if (!sHit) await onMiss(600); continue; }
      if (!s || s.total < 8) { console.log(`  · ${asc}: ${s ? s.total : 0} chars — too few, skipping`); if (!sHit) await onMiss(500); continue; }
      const md = cacheOnly ? priorDetail.byAsc[slug] : await extractMeta(s, gem);
      if (!md) { console.log(`  · ${asc}: no prior meta-detail entry — skipping (cache-only)`); continue; }
      // <30 chars: the aggregate percentages (gear/notables/uniques) are statistical noise, but a
      // single real QA'd character is still a valid build — keep building it, flagged low-sample
      // (the UI already shows the sample count). Above 30 the breakdown is published normally.
      if (s.total < 30) md.lowSample = true;
      meta.byAsc[slug] = { asc, ...md };
      if (!sHit) await onMiss(600);
      if (SAMPLE > 0) {
        // Pull top characters for gear aggregation, then keep pulling DEEPER down poe.ninja's
        // ranked list until we have an L85+ character running the ascendancy's DOMINANT meta
        // weapon. The top of the list is often off-meta high-DPS outliers (a spear Monk ahead of
        // the quarterstaff majority), so a fixed top-N can miss the meta entirely. Capped by MAXSAMPLE.
        const metaWep = md.weapons && md.weapons[0] && md.weapons[0].name;
        const metaFam = weaponClass && metaWeaponFamily(metaWep);
        const onMetaWeapon = char => !!metaFam && charWeaponFamily(char, weaponClass) === metaFam;
        // default 25 (was 15): a sparse #1 meta weapon (e.g. Ritualist's ~19% Wand/Focus) often
        // isn't on an L85+ char within 15 pulls, leaving the ascendancy with no build. The disk
        // cache makes deeper scans nearly free on re-run; the cooldown bounds the live cost.
        const MAXSAMPLE = Math.max(SAMPLE, Number(opt['max-sample']) || 25);
        const ranked = (s.vls.name || []).map((nm, i) => ({ account: (s.vls.account || [])[i], name: nm, ehp: _num((s.vls.ehp || [])[i]), dps: _num((s.vls.dps || [])[i]) })).filter(p => p.account && p.name);
        const pulled = [];
        let metaFound = false;
        for (const p of ranked) {
          if (pulled.length >= MAXSAMPLE) break;
          if (pulled.length >= SAMPLE && (!metaFam || metaFound)) break;
          const cf = `c-${sv.version}-${san(p.account)}-${san(p.name)}.json`, cHit = hit(cf);
          try { const char = JSON.parse(await cached(cf, charUrl(sv, p.account, p.name))); pulled.push({ ...p, char }); if (metaFam && (char.level || 0) >= 85 && onMetaWeapon(char)) metaFound = true; }
          catch (e) { if (!cacheOnly) console.log(`    · ${asc}: skip ${p.account}/${p.name} — ${e.message}`); }  // surface throttle/404 instead of silent coverage loss
          if (!cHit) await onMiss(650);
        }
        if (pulled.length) {
          const ga = aggregateGear(pulled.map(p => p.char));
          meta.byAsc[slug].gear = ga.gear; meta.byAsc[slug].runes = ga.runes;
          pulled.forEach(p => globalChars.push(p.char));
          let cands = pulled.filter(p => (p.char.level || 0) >= 85);
          if (!cands.length) cands = pulled;
          // Narrow to candidates running the dominant meta weapon (computed above). The adaptive
          // pull tries to ensure at least one exists; if none do, the off-weapon pick is kept but
          // QA's stats<->build overlap check rejects it (honest template served instead).
          if (metaFam) {
            const onMeta = cands.filter(p => onMetaWeapon(p.char));
            if (onMeta.length) cands = onMeta;
            else console.log(`  ! ${asc}: no L85+ char running meta weapon ${metaWep} within ${pulled.length} pulls — QA will reject the off-weapon build`);
          }
          const maxE = Math.max(1, ...cands.map(p => p.ehp || 0)), maxD = Math.max(1, ...cands.map(p => p.dps || 0));
          cands.sort((a, b) => Math.min((b.ehp || 0) / maxE, (b.dps || 0) / maxD) - Math.min((a.ehp || 0) / maxE, (a.dps || 0) / maxD));
          const { account, name, char } = cands[0];
          try {
            const { build, report } = buildOne(char, { gem, account, name, league, tree, slugMap, baseItems, md, weaponClass, quiet: true });
            if (report.ok) {
              writeBuild(slug, build); writePob(slug, char.pathOfBuildingExport); builds++;
              meta.byAsc[slug].source = { account, name, level: char.level || null };
              meta.byAsc[slug].build = { passives: build.passives.length, skills: report.stats.skills, items: report.stats.items };
              meta.byAsc[slug].skillSetups = readableSkills(char);
              meta.byAsc[slug].buildItems = buildItems(char);
              meta.byAsc[slug].pob = !!char.pathOfBuildingExport;
              if (char.level) meta.byAsc[slug].stats.level = char.level;
              console.log(`  + ${asc.padEnd(20)} ${String(s.total).padStart(6)} chars · ${pulled.length} sampled · build <- ${name} (L${char.level || '?'}, EHP ${cands[0].ehp || '?'}, DPS ${cands[0].dps || '?'})`);
            } else console.log(`  x ${asc.padEnd(20)} build QA FAIL (${report.issues.filter(i => i.sev === 'fail').map(i => i.m).join('; ')})`);
          } catch (e) { console.log(`  x ${asc}: build ${e.message}`); }
        } else console.log(`  · ${asc}: no characters pulled`);
      }
      if (!cacheOnly) await sleep(500); // be polite to poe.ninja
    }
    if (globalChars.length && meta.global) { const gg = aggregateGear(globalChars); meta.global.gear = gg.gear; meta.global.runes = gg.runes; }
    const slugs = refreshManifest();
    fs.writeFileSync(path.join(REPO, 'meta-detail.json'), JSON.stringify(meta, null, 2) + '\n');
    console.log(`\n${builds} builds · meta-detail.json for ${Object.keys(meta.byAsc).length} ascendancies · manifest (${slugs.length})`);
    return;
  }

  // SINGLE: one character by --account/--name, or --from-cache <char.json>
  if (!opt.slug) throw new Error('--slug <out-slug> required (or use --enumerate)');
  let char, account = opt.account, name = opt.name;
  if (opt['from-cache']) { char = JSON.parse(fs.readFileSync(opt['from-cache'], 'utf8')); account = account || char.account; name = name || char.name; }
  else {
    if (!opt.account || !opt.name) throw new Error('--account and --name required (or --from-cache / --enumerate)');
    char = JSON.parse(await get(charUrl(await getSnapshot(league), account, name)));
  }
  // run the meta-weapon QA in the single path too (when meta-detail.json has an entry for this
  // slug) so a hand-generated build committed for serving can't quietly contradict the stats panel.
  let md = null;
  try { md = (JSON.parse(fs.readFileSync(path.join(REPO, 'meta-detail.json'), 'utf8')).byAsc || {})[opt.slug] || null; } catch (_) {}
  const { build, report } = buildOne(char, { gem, account, name, league, tree, slugMap, baseItems, md, weaponClass });
  console.log('QA verdict:', report.ok ? 'PASS' : 'FAIL');
  if (!report.ok) { console.log('Refusing to write an incohesive build.'); process.exit(1); }
  writeBuild(opt.slug, build);
  console.log('wrote builds/' + opt.slug + '.build', `(${build.passives.length} passives, ${build.skills.length} skills, ${build.inventory_slots.length} items)`);
  refreshManifest();
}
if (require.main === module) main().catch(e => { console.error('ERROR:', e.message); process.exit(1); });
// exported for unit tests (importing the module must not run the CLI — hence the guard above)
module.exports = { weaponFamily, metaWeaponFamily, charWeaponFamily, convert, qa, gemMapFromLua, slugMapFromTree };

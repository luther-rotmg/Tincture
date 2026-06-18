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
const REPO = path.resolve(__dirname, '..');

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
    https.get({ hostname:u.hostname, path:u.pathname+u.search, headers:{ 'User-Agent':UA, 'Accept':'*/*', 'Referer':'https://poe.ninja/poe2/builds' } }, r => {
      if (r.statusCode >= 300 && r.statusCode < 400 && r.headers.location) return get(new URL(r.headers.location, url).href, binary, attempt).then(res, rej);
      const ch = []; r.on('data', c => ch.push(c)); r.on('end', () => {
        const b = Buffer.concat(ch);
        if (r.statusCode === 429 && attempt < 5) { // respect the throttle: back off and retry
          const wait = (Number(r.headers['retry-after']) || 3 * (attempt + 1)) * 1000;
          return setTimeout(() => get(url, binary, attempt + 1).then(res, rej), wait);
        }
        if (r.statusCode !== 200) return rej(new Error('HTTP ' + r.statusCode));
        res(binary ? b : b.toString('utf8'));
      });
    }).on('error', rej);
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
    const gameId = (body.match(/gameId\s*=\s*"([^"]*)"/) || [])[1] || x[1];
    if (name) m[name] = gameId;
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

  // skills: each group = one active SkillGem + its SupportGems. Track the highest-DPS
  // group's gem as the headline "main skill" for naming (ascendancy buffs like Hollow
  // Focus report ~0 dps, so they won't be mistaken for the main skill).
  const skills = [];
  let mainSkillName = '', bestDps = -1;
  (char.skills || []).forEach(group => {
    const gems = (group.allGems || []).map(g => ({ name: g.name, level: g.level, id: gem[g.name] })).filter(g => g.id);
    const active = gems.find(g => /\/SkillGem/i.test(g.id));
    if (!active) return; // a group with no resolvable active skill is dropped
    const supports = gems.filter(g => g !== active && /\/SupportGem/i.test(g.id));
    const skill = { id: active.id };
    if (active.level) skill.level_interval = [1, 100];
    if (supports.length) skill.support_skills = supports.map(s => ({ id: s.id, level_interval: [1, 100] }));
    skills.push(skill);
    // group.dps is an array of {name, dps, ...}; take the group's peak dps
    const dps = Array.isArray(group.dps) ? Math.max(0, ...group.dps.map(d => Number(d && d.dps) || 0)) : (Number(group.dps) || 0);
    if (dps > bestDps) { bestDps = dps; mainSkillName = active.name; }
  });

  // inventory: equipment in the main weapon set (skip runes / 2nd-set offhands)
  const inv = [];
  (char.items || []).forEach(it => {
    const d = it.itemData || it;
    const dest = SLOT_MAP[d.inventoryId];
    if (!dest) return;
    if (d.frameType === 3 && d.name) inv.push({ inventory_id: dest, unique_name: d.name, slot_x: 0, slot_y: 0 });
    else inv.push({ inventory_id: dest, additional_text: itemText(d), level_interval: [1, 100], slot_x: 0, slot_y: 0 });
  });

  const buildName = `${ascName}${mainSkillName ? ' — ' + mainSkillName : ''} (public ladder)`;
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
    _tincture: { source: 'poe.ninja public ladder', account, character: name, league, level: char.level || null, slug },
  };
}

// ---- QA: catch conversion errors + cheap cohesion checks ----
function qa(build, char, { slug, tree }) {
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
  });

  // items
  const slots = build.inventory_slots.map(s => s.inventory_id);
  const single = ['Weapon1','Helm1','BodyArmour1','Gloves1','Boots1','Belt1','Amulet1'];
  single.forEach(sl => { if (slots.filter(s => s === sl).length > 1) fail(`slot ${sl} occupied more than once`); });
  if (slots.filter(s => s === 'Ring1' || s === 'Ring2').length > 2) fail('more than 2 rings');
  build.inventory_slots.forEach(s => { if (!Object.values(SLOT_MAP).includes(s.inventory_id)) fail(`unknown inventory slot ${s.inventory_id}`); });

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
// returns ranked [[account, name], ...] for a search snapshot (top ~100 ladder characters)
async function searchPairs(sv) {
  const buf = await get(`https://poe.ninja/poe2/api/builds/${sv.version}/search?overview=${sv.snapshotName}`, true);
  const result = (pbFields(buf).find(x => x.f === 1 && x.wt === 2) || {}).data;
  if (!result) return [];
  const lists = pbFields(result).filter(x => x.f === 5 && x.wt === 2).map(vl => {
    const ff = pbFields(vl.data);
    const id = (ff.find(x => x.f === 1 && x.wt === 2) || {}).data;
    const strings = ff.filter(x => x.f === 2 && x.wt === 2).map(v => {
      const s = (pbFields(v.data).find(x => x.f === 1 && x.wt === 2) || {}).data; return s ? s.toString('utf8') : null;
    });
    return { id: id ? id.toString('utf8') : '?', strings };
  });
  const names = (lists.find(l => l.id === 'name') || {}).strings || [];
  const accts = (lists.find(l => l.id === 'account') || {}).strings || [];
  return names.map((nm, k) => [accts[k], nm]).filter(p => p[0] && p[1]);
}

function writeBuild(slug, build) {
  const outDir = path.join(REPO, 'builds');
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, slug + '.build'), JSON.stringify(build, null, 2) + '\n');
}
function refreshManifest() {
  const outDir = path.join(REPO, 'builds');
  const slugs = fs.readdirSync(outDir).filter(f => f.endsWith('.build')).map(f => f.slice(0, -'.build'.length)).sort();
  fs.writeFileSync(path.join(outDir, 'index.json'), JSON.stringify(slugs, null, 2) + '\n');
  return slugs;
}

function buildOne(char, { gem, account, name, league, tree, slugMap, quiet }) {
  const build = convert(char, { slug: slugMap, gem, account, name, league });
  delete build._tincture;
  const report = qa(build, char, { slug: slugMap, tree });
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
  const cacheDir = path.join(__dirname, '.cache');
  const cached = (f, url, bin) => { const p = path.join(cacheDir, f); if (fs.existsSync(p)) return Promise.resolve(bin ? fs.readFileSync(p) : fs.readFileSync(p, 'utf8')); return get(url, bin).then(d => { fs.mkdirSync(cacheDir, { recursive: true }); fs.writeFileSync(p, d); return d; }); };
  const tree = JSON.parse(await cached('tree.json', TREE_URL));
  const slugMap = slugMapFromTree(tree);
  const gem = gemMapFromLua(await cached('Gems.lua', GEMS_URL));

  // ENUMERATE: pull top ladder characters, one cohesive build per meta ascendancy
  if (opt.enumerate) {
    const sv = await getSnapshot(league);
    const pairs = await searchPairs(sv);
    console.log(`search snapshot ${sv.version} (${sv.snapshotName}) — ${pairs.length} top characters`);
    const targets = new Set(Object.keys(ASCENDANCY_CODES));
    const done = new Set(), results = [];
    const cap = Number(opt.max) || 45;
    for (let k = 0; k < pairs.length && k < cap && done.size < targets.size; k++) {
      const [account, name] = pairs[k];
      let char;
      try { char = JSON.parse(await get(charUrl(sv, account, name))); } catch (e) { console.log(`  - ${name}: fetch ${e.message}`); await sleep(300); continue; }
      const asc = char.class;
      if (!targets.has(asc) || done.has(asc)) { await sleep(300); continue; }
      const slug = slugify(asc);
      try {
        const { build, report } = buildOne(char, { gem, account, name, league, tree, slugMap, quiet: true });
        if (!report.ok) { console.log(`  x ${asc} <- ${name}: QA FAIL (${report.issues.filter(i => i.sev === 'fail').map(i => i.m).join('; ')})`); await sleep(300); continue; }
        writeBuild(slug, build);
        done.add(asc); results.push({ asc, slug, name, account, ...report.stats });
        console.log(`  + ${asc.padEnd(20)} <- ${name} (${account})  [${report.stats.sharedUnique}p ${report.stats.ws1 + report.stats.ws2}ws ${report.stats.skills}s ${report.stats.items}i]`);
      } catch (e) { console.log(`  x ${asc} <- ${name}: ${e.message}`); }
      await sleep(700); // be polite to poe.ninja (it throttles bursts)
    }
    const slugs = refreshManifest();
    console.log(`\nGenerated ${results.length} loadable builds. Manifest (${slugs.length}): ${slugs.join(', ')}`);
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
  const { build, report } = buildOne(char, { gem, account, name, league, tree, slugMap });
  console.log('QA verdict:', report.ok ? 'PASS' : 'FAIL');
  if (!report.ok) { console.log('Refusing to write an incohesive build.'); process.exit(1); }
  writeBuild(opt.slug, build);
  console.log('wrote builds/' + opt.slug + '.build', `(${build.passives.length} passives, ${build.skills.length} skills, ${build.inventory_slots.length} items)`);
  refreshManifest();
}
main().catch(e => { console.error('ERROR:', e.message); process.exit(1); });

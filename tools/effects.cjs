'use strict';
// Pure extractors that turn data the enumerate pass already pulls (poe.ninja character
// items, the GGG tree export, PoB2 Gems.lua) into display-ready effect text for the
// in-site tooltips. No network, no fs — callers pass parsed inputs. Unit-tested in
// tools/test-effects.cjs; imported by tools/build-from-ninja.cjs.

function cleanMarkup(s) {
  return String(s == null ? '' : s)
    .replace(/\[[^\]|]+\|([^\]]+)\]/g, '$1') // [Tag|Display] -> Display
    .replace(/\[([^\]]+)\]/g, '$1')          // [Tag] -> Tag
    .replace(/\s+/g, ' ')
    .trim();
}

function normKey(s) {
  return cleanMarkup(s).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

// Names the meta actually references (notables + anointments, across all ascendancies +
// global), normalized. Used to pull in popular "other"-flagged tree nodes without bloat.
function wantedFromMeta(meta) {
  const out = new Set();
  if (!meta) return out;
  const add = md => { if (!md) return; for (const col of ['notables', 'anointments']) for (const x of (md[col] || [])) if (x && x.name) out.add(normKey(x.name)); };
  add(meta.global);
  for (const md of Object.values(meta.byAsc || {})) add(md);
  return out;
}

// Keep notables AND keystones, plus any named-with-stats node the meta references
// (popular "other"-flagged passives + anointments) — never the ~3,300 small named nodes.
function notablesFromTree(tree, wanted) {
  const want = wanted instanceof Set ? wanted : new Set();
  const out = {};
  const nodes = (tree && tree.nodes) || {};
  for (const [k, n] of Object.entries(nodes)) {
    if (k === 'root' || !n || !n.name) continue;
    if (!Array.isArray(n.stats) || !n.stats.length) continue;
    if (!(n.isNotable || n.isKeystone || want.has(normKey(n.name)))) continue;
    const key = normKey(n.name);
    if (out[key]) continue;
    out[key] = { name: cleanMarkup(n.name), stats: n.stats.map(cleanMarkup).filter(Boolean) };
  }
  return out;
}

// tags that describe the gem's category for chips; drop attribute/plumbing tags
const TAG_SKIP = new Set(['strength', 'dexterity', 'intelligence', 'grants_active_skill', 'grants_active_skill_or_minion', 'support']);

function gemInfoFromLua(lua) {
  const out = {};
  const re = /\[\s*"([^"]+)"\s*\]\s*=\s*\{([\s\S]*?)\n\t\},/g; // tab-indented entry close (mirrors gemMapFromLua)
  let x;
  while ((x = re.exec(lua))) {
    const gameId = x[1], body = x[2];
    const name = (body.match(/name\s*=\s*"([^"]*)"/) || [])[1];
    if (!name) continue;
    const kind = /\/SupportGem/i.test(gameId) ? 'support' : /\/SkillGem/i.test(gameId) ? 'skill' : null;
    const tagsBlock = (body.match(/tags\s*=\s*\{([\s\S]*?)\}/) || [])[1] || '';
    const tags = [...tagsBlock.matchAll(/(\w+)\s*=\s*true/g)].map(m => m[1]).filter(t => !TAG_SKIP.has(t));
    out[normKey(name)] = { kind, tags };
  }
  return out;
}

function collectFromChar(char, acc) {
  // uniques live in items, but unique JEWELS are in char.jewels and unique FLASKS/charms
  // in char.flasks — same item shape. Harvest all three. (Jewels/flasks carry no socketed
  // runes, so the rune loop below is a harmless no-op for them.)
  for (const it of [].concat(char.items || [], char.jewels || [], char.flasks || [])) {
    const d = it.itemData || it;
    // runes / soul cores socketed into gear — mod text is slot-prefixed and self-describing
    for (const s of (d.socketedItems || [])) {
      const nm = s.typeLine || s.baseType || s.name || '';
      if (!nm || !/\bRune\b|Soul Core/i.test(nm)) continue;
      const key = normKey(nm);
      const e = acc.runes[key] || (acc.runes[key] = { name: cleanMarkup(nm), lines: [] });
      for (const m of (s.explicitMods || [])) {
        const line = cleanMarkup(m);
        if (line && !e.lines.includes(line)) e.lines.push(line);
      }
    }
    // uniques — first seen wins (a representative real item)
    if (d.frameType === 3 && d.name && !/^(Normal|Magic|Rare) /.test(d.name)) {
      const key = normKey(d.name);
      if (!acc.uniques[key]) {
        acc.uniques[key] = {
          name: cleanMarkup(d.name),
          base: cleanMarkup(d.baseType || d.typeLine || ''),
          mods: [].concat(d.implicitMods || [], d.explicitMods || []).map(cleanMarkup).filter(Boolean),
          flavour: cleanMarkup((d.flavourText || []).join(' ')),
        };
      }
    }
  }
  // skill + support gems — description from the in-game gem text
  for (const g of (char.skills || [])) {
    for (const gm of (g.allGems || [])) {
      const d = gm.itemData || {};
      const nm = gm.name || d.typeLine || d.baseType;
      if (!nm) continue;
      const key = normKey(nm);
      if (acc.gems[key]) continue;
      const desc = cleanMarkup(d.secDescrText || d.descrText || '');
      if (!desc) continue; // no description -> omit (front end falls back to link)
      acc.gems[key] = { name: cleanMarkup(nm), desc };
    }
  }
}

function buildEffectsJson(acc, opts) {
  const gemInfo = (opts && opts.gemInfo) || {};
  const gems = {};
  for (const [key, g] of Object.entries(acc.gems || {})) {
    const info = gemInfo[key] || {};
    gems[key] = { name: g.name, kind: g.kind || info.kind || 'skill', desc: g.desc, tags: info.tags || [] };
  }
  const runes = {};
  for (const [key, r] of Object.entries(acc.runes || {})) {
    if (r.lines && r.lines.length) runes[key] = { name: r.name, lines: r.lines };
  }
  return {
    meta: { generated: opts.generated, sources: opts.sources || [] },
    runes,
    uniques: acc.uniques || {},
    gems,
    notables: notablesFromTree(opts.tree || {}, opts.wanted),
  };
}

module.exports = { normKey, cleanMarkup, notablesFromTree, wantedFromMeta, gemInfoFromLua, collectFromChar, buildEffectsJson };

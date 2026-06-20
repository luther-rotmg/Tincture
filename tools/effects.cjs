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

function notablesFromTree(tree) {
  const out = {};
  const nodes = (tree && tree.nodes) || {};
  for (const [k, n] of Object.entries(nodes)) {
    if (k === 'root' || !n || !n.isNotable || !n.name) continue;
    if (!Array.isArray(n.stats) || !n.stats.length) continue;
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

module.exports = { normKey, cleanMarkup, notablesFromTree, gemInfoFromLua };

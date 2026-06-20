'use strict';
// Audit which entities rendered by metaCol() resolve to an effects.json card vs fall back
// to the lookup link. Replicates the front-end normKey + effectFor + KIND_TO_TYPE.
// Run: node tools/coverage-audit.cjs
const fs = require('fs');
const path = require('path');
const REPO = path.resolve(__dirname, '..');
const EFF = JSON.parse(fs.readFileSync(path.join(REPO, 'effects.json'), 'utf8'));
const MD = JSON.parse(fs.readFileSync(path.join(REPO, 'meta-detail.json'), 'utf8'));
const cleanMarkup = s => String(s == null ? '' : s).replace(/\[[^\]|]+\|([^\]]+)\]/g, '$1').replace(/\[([^\]]+)\]/g, '$1').replace(/\s+/g, ' ').trim();
const normKey = s => cleanMarkup(s).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
const KIND_TO_TYPE = { 'Skill gem': 'gems', 'Support gem': 'gems', 'Passive notable': 'notables', 'Anointment': 'notables', 'Unique item': 'uniques', 'Rune / soul core': 'runes' };
function effectFor(kind, name) {
  const type = KIND_TO_TYPE[kind]; const map = type && EFF[type]; if (!map) return false;
  const k = normKey(name); if (map[k]) return true;
  if (type === 'runes') { const k2 = k.replace(/^(lesser|greater|grand|perfect|superior|exceptional)\s+/, ''); if (k2 !== k && map[k2]) return true; }
  return false;
}
const COLS = [['skills', 'Skill gem'], ['supports', 'Support gem'], ['notables', 'Passive notable'], ['uniques', 'Unique item'], ['runes', 'Rune / soul core'], ['anointments', 'Anointment'], ['weapons', 'Weapon base']];
const cats = {}; for (const [, kind] of COLS) cats[kind] = new Map();
for (const md of [MD.global, ...Object.values(MD.byAsc || {})].filter(Boolean)) {
  for (const [col, kind] of COLS) for (const x of (md[col] || [])) {
    if (!x || !x.name) continue;
    const k = normKey(x.name), hit = effectFor(kind, x.name), prev = cats[kind].get(k);
    if (!prev) cats[kind].set(k, { name: x.name, hit, maxpct: x.pct || 0 });
    else { prev.maxpct = Math.max(prev.maxpct, x.pct || 0); prev.hit = prev.hit || hit; }
  }
}
let totEnt = 0, totHit = 0;
console.log('=== TOOLTIP COVERAGE AUDIT (deduped across all ascendancies + global) ===\n');
for (const [col, kind] of COLS) {
  const arr = [...cats[kind].values()], hits = arr.filter(e => e.hit).length;
  totEnt += arr.length; totHit += hits;
  console.log(`${kind.padEnd(16)} (md.${col.padEnd(11)}): ${String(hits).padStart(4)}/${String(arr.length).padStart(4)}  (${arr.length ? Math.round(hits / arr.length * 100) : 0}%)`);
  const misses = arr.filter(e => !e.hit).sort((a, b) => b.maxpct - a.maxpct).slice(0, 10).map(m => `${m.name} [${m.maxpct}%]`);
  if (misses.length) console.log('   top misses: ' + misses.join(' · '));
}
console.log(`\nOVERALL: ${totHit}/${totEnt} resolve (${Math.round(totHit / totEnt * 100)}%)`);

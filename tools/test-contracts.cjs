'use strict';
/*
 * Cross-implementation contract tests — lock the agreement between the front end (index.html)
 * and the Node pipeline, so a silent drift can never ship.
 *   node --test tools/test-contracts.cjs
 *
 * #20  index.html `normKeyFE` MUST produce identical output to effects.cjs `normKey`. If they
 *      drift, every affected entity tooltip silently falls back to a Google link with no failing
 *      test (the FE key wouldn't match the effects.json key).
 * #21  index.html `slugOf({asc, skill:''})` MUST equal build-from-ninja.cjs `slugify(asc)` for
 *      every ascendancy. If they drift, `builds/<slug>.build` 404s on Decant.
 *
 * The FE functions live only in index.html (no module system there), so we extract their source
 * and make them callable in Node — the test reads the very code that ships.
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const effects = require('./effects.cjs');
const recon = require('./build-from-ninja.cjs');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
function extract(re, label) {
  const m = html.match(re);
  if (!m) throw new Error(`contract test could not find ${label} in index.html — did it get renamed?`);
  return m[1];
}
// `function normKeyFE(s){ <body has no nested braces> }`
const normKeyFE = new Function('s', extract(/function normKeyFE\s*\(s\)\s*\{([\s\S]*?)\}/, 'normKeyFE'));
// `const slugOf = b => <single-expression arrow>;`
const slugOf = eval('(' + extract(/const slugOf\s*=\s*(b =>.*);\r?$/m, 'slugOf') + ')');

test('#20 normKeyFE (index.html) === effects.normKey over a shared fixture set', () => {
  const fixtures = [
    "Farrul's Rune of the Chase", "[Resistances|Fire Resistance]", "  Soul Core  of  Quipolatl ",
    "Gain [Tailwind] on Skill use", "[HitDamage|Hit]", "Perfect Iron Rune", "Well of Power",
    "Chaos Inoculation", "20% increased Critical Damage if you've consumed a Power Charge",
    "Acolyte of Chayula", "Saqawal's Rune of the Sky", "Café—Münchën", "tabs\tand\nnewlines",
    "", "123", "ALL CAPS", "—leading dash", "trailing—", null, undefined,
  ];
  for (const f of fixtures)
    assert.equal(normKeyFE(f), effects.normKey(f), `normKey mismatch for ${JSON.stringify(f)}`);
});

test('#21 slugOf({asc}) (index.html) === slugify(asc) (build-from-ninja) for every ascendancy', () => {
  const ascs = Object.keys(recon.ASCENDANCY_CODES);
  assert.ok(ascs.length >= 20, `expected the full ascendancy table, got ${ascs.length}`);
  for (const asc of ascs)
    assert.equal(slugOf({ asc, skill: "" }), recon.slugify(asc), `slug mismatch for "${asc}"`);
});

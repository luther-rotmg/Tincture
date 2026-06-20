'use strict';
const test = require('node:test');
const assert = require('node:assert');
const E = require('./effects.cjs');

test('normKey lowercases, strips markup and punctuation', () => {
  assert.strictEqual(E.normKey("Farrul's Rune of the Chase"), 'farrul s rune of the chase');
  assert.strictEqual(E.normKey('[Resistances|Fire Resistance]'), 'fire resistance');
  assert.strictEqual(E.normKey('  Soul Core  of  Quipolatl '), 'soul core of quipolatl');
  assert.strictEqual(E.normKey(null), '');
});

test('cleanMarkup unwraps tags and collapses whitespace, preserving case', () => {
  assert.strictEqual(E.cleanMarkup('Gain [Tailwind] on Skill use'), 'Gain Tailwind on Skill use');
  assert.strictEqual(E.cleanMarkup('[HitDamage|Hit]'), 'Hit');
  assert.strictEqual(E.cleanMarkup('Body Armours:   15% of   Damage'), 'Body Armours: 15% of Damage');
});

test('notablesFromTree keeps isNotable nodes with stats, cleaned', () => {
  const tree = { nodes: {
    root: { out: [] },
    a: { isNotable: true, name: 'Gathering Winds', stats: ['Gain [Tailwind] on Skill use', 'Lose all [Tailwind] when [HitDamage|Hit]'] },
    b: { isNotable: false, name: 'Small Node', stats: ['+10 to Dexterity'] },
    c: { isNotable: true, name: 'No Stats', stats: [] },
  }};
  const out = E.notablesFromTree(tree);
  assert.deepStrictEqual(Object.keys(out), ['gathering winds']);
  assert.strictEqual(out['gathering winds'].name, 'Gathering Winds');
  assert.deepStrictEqual(out['gathering winds'].stats, ['Gain Tailwind on Skill use', 'Lose all Tailwind when Hit']);
});

test('gemInfoFromLua parses kind from gameId and display tags', () => {
  const lua = [
    '\t["Metadata/Items/Gems/SkillGemIceNova"] = {',
    '\t\tname = "Ice Nova",',
    '\t\tgameId = "Metadata/Items/Gems/SkillGemIceNova",',
    '\t\ttags = {',
    '\t\t\tintelligence = true,',
    '\t\t\tgrants_active_skill = true,',
    '\t\t\tspell = true,',
    '\t\t\tcold = true,',
    '\t\t},',
    '\t},',
    '\t["Metadata/Items/Gems/SupportGemInspiration"] = {',
    '\t\tname = "Inspiration",',
    '\t\tgameId = "Metadata/Items/Gems/SupportGemInspiration",',
    '\t\ttags = {',
    '\t\t\tsupport = true,',
    '\t\t},',
    '\t},',
  ].join('\n');
  const out = E.gemInfoFromLua(lua);
  assert.strictEqual(out['ice nova'].kind, 'skill');
  assert.deepStrictEqual(out['ice nova'].tags, ['spell', 'cold']);
  assert.strictEqual(out['inspiration'].kind, 'support');
});

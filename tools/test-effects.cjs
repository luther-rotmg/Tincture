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

test('collectFromChar gathers runes (union of slot lines), uniques, gems', () => {
  const acc = { runes: {}, uniques: {}, gems: {} };
  const charA = {
    items: [
      { itemData: { inventoryId: 'Boots', frameType: 2, socketedItems: [
        { typeLine: "Farrul's Rune of the Chase", explicitMods: ['Boots: 5% increased Movement Speed'] } ] } },
      { itemData: { inventoryId: 'Ring', frameType: 3, name: "Kalandra's Touch", baseType: 'Ring',
        implicitMods: [], explicitMods: ['Reflects opposite Ring'], flavourText: ['Power is a matter of perspective.'] } },
    ],
    skills: [ { allGems: [
      { name: 'Ice Nova', itemData: { typeLine: 'Ice Nova', secDescrText: 'Creates a ring of [Cold] damage.' } } ] } ],
  };
  const charB = {
    items: [
      { itemData: { inventoryId: 'BodyArmour', frameType: 2, socketedItems: [
        { typeLine: "Farrul's Rune of the Chase", explicitMods: ['Body Armours: +10 to Spirit'] } ] } },
    ], skills: [],
  };
  E.collectFromChar(charA, acc);
  E.collectFromChar(charB, acc);

  assert.deepStrictEqual(acc.runes['farrul s rune of the chase'].lines,
    ['Boots: 5% increased Movement Speed', 'Body Armours: +10 to Spirit']);
  assert.strictEqual(acc.uniques['kalandra s touch'].base, 'Ring');
  assert.deepStrictEqual(acc.uniques['kalandra s touch'].mods, ['Reflects opposite Ring']);
  assert.strictEqual(acc.uniques['kalandra s touch'].flavour, 'Power is a matter of perspective.');
  assert.strictEqual(acc.gems['ice nova'].desc, 'Creates a ring of Cold damage.');
});

test('collectFromChar skips gems with no description text', () => {
  const acc = { runes: {}, uniques: {}, gems: {} };
  E.collectFromChar({ items: [], skills: [ { allGems: [ { name: 'Mystery', itemData: {} } ] } ] }, acc);
  assert.strictEqual(acc.gems['mystery'], undefined);
});

test('buildEffectsJson assembles all maps and merges gem kind+tags', () => {
  const acc = {
    runes: { 'a rune': { name: 'A Rune', lines: ['Boots: +1'] }, 'empty': { name: 'Empty', lines: [] } },
    uniques: { 'x': { name: 'X', base: 'Ring', mods: ['m'], flavour: '' } },
    gems: { 'ice nova': { name: 'Ice Nova', desc: 'cold ring' } },
  };
  const tree = { nodes: { n: { isNotable: true, name: 'Notable One', stats: ['+5 life'] } } };
  const gemInfo = { 'ice nova': { kind: 'skill', tags: ['cold', 'spell'] } };
  const out = E.buildEffectsJson(acc, { tree, gemInfo, generated: '2026-06-19T00:00:00Z', sources: [{ name: 'poe.ninja' }] });

  assert.strictEqual(out.meta.generated, '2026-06-19T00:00:00Z');
  assert.strictEqual(out.meta.sources[0].name, 'poe.ninja');
  assert.deepStrictEqual(Object.keys(out.runes), ['a rune']); // empty-lines rune dropped
  assert.strictEqual(out.gems['ice nova'].kind, 'skill');
  assert.deepStrictEqual(out.gems['ice nova'].tags, ['cold', 'spell']);
  assert.strictEqual(out.notables['notable one'].stats[0], '+5 life');
});

test('collectFromChar harvests unique jewels and flasks, not just items', () => {
  const acc = { runes: {}, uniques: {}, gems: {} };
  const char = {
    items: [{ itemData: { inventoryId: 'Ring', frameType: 3, name: "Kalandra's Touch", baseType: 'Ring', explicitMods: ['Reflects opposite Ring'] } }],
    jewels: [{ itemData: { frameType: 3, name: 'From Nothing', baseType: 'Sapphire', explicitMods: ['Allocates a Jewel socket'], flavourText: ['x'] } }],
    flasks: [{ itemData: { frameType: 3, name: 'The Fall of the Axe', baseType: 'Silver Charm', implicitMods: ['Used when you are Slowed'], explicitMods: ['Grants Onslaught during effect'] } }],
    skills: [],
  };
  E.collectFromChar(char, acc);
  assert.ok(acc.uniques['kalandra s touch'], 'item unique still harvested');
  assert.ok(acc.uniques['from nothing'], 'jewel unique harvested');
  assert.strictEqual(acc.uniques['the fall of the axe'].base, 'Silver Charm', 'flask unique harvested');
  assert.deepStrictEqual(acc.uniques['the fall of the axe'].mods, ['Used when you are Slowed', 'Grants Onslaught during effect']);
});

test('collectFromChar skips frameType-3 items named Normal/Magic/Rare (meta noise)', () => {
  const acc = { runes: {}, uniques: {}, gems: {} };
  E.collectFromChar({ items: [{ itemData: { frameType: 3, name: 'Rare Amulet of Doom' } }], skills: [] }, acc);
  assert.strictEqual(acc.uniques['rare amulet of doom'], undefined);
});

test('notablesFromTree includes keystones + meta-referenced other nodes, excludes unreferenced others', () => {
  const tree = { nodes: {
    root: { out: [] },
    a: { isNotable: true, name: 'Gathering Winds', stats: ['Gain Tailwind on Skill use'] },
    k: { isKeystone: true, name: 'Chaos Inoculation', stats: ['Maximum Life becomes 1'] },
    o1: { name: 'Point Blank', stats: ['More damage at close range'] },
    o2: { name: 'Tiny Passive', stats: ['+10 to Strength'] },
  }};
  const out = E.notablesFromTree(tree, new Set([E.normKey('Point Blank')]));
  assert.ok(out['gathering winds'], 'notable kept');
  assert.ok(out['chaos inoculation'], 'keystone kept');
  assert.ok(out['point blank'], 'referenced other node kept');
  assert.strictEqual(out['tiny passive'], undefined, 'unreferenced other node dropped');
});

test('notablesFromTree without wanted still keeps notables and keystones', () => {
  const tree = { nodes: { k: { isKeystone: true, name: 'Blood Magic', stats: ['Removes all Mana'] }, o: { name: 'Nope', stats: ['x'] } } };
  const out = E.notablesFromTree(tree);
  assert.ok(out['blood magic']);
  assert.strictEqual(out['nope'], undefined);
});

test('wantedFromMeta collects normalized notable + anointment names from global and byAsc', () => {
  const meta = {
    global: { notables: [{ name: 'Point Blank' }], anointments: [{ name: 'Well of Power' }] },
    byAsc: { x: { notables: [{ name: 'Choice of Power' }], anointments: [] } },
  };
  const w = E.wantedFromMeta(meta);
  assert.ok(w.has('point blank') && w.has('well of power') && w.has('choice of power'));
});

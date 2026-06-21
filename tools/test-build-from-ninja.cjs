'use strict';
/*
 * Offline unit tests for the build reconstructor — no network, no deps.
 *   node --test tools/test-build-from-ninja.cjs
 *
 * These lock the honesty-critical invariants of tools/build-from-ninja.cjs: the weapon-family
 * matching (a served .build must run the ascendancy's dominant meta weapon — the regression that
 * shipped a mace ascendancy with no build), verbatim gem ids, gear/gem leveling gates, and the
 * skill/item dedupe. The module guards its CLI behind require.main, so importing is side-effect free.
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const zlib = require('node:zlib');
const T = require('./build-from-ninja.cjs');

test('weaponFamily normalises base_items item_class to a poe.ninja family', () => {
  assert.equal(T.weaponFamily('One Hand Mace'), 'Mace');
  assert.equal(T.weaponFamily('Two Hand Mace'), 'Mace');
  assert.equal(T.weaponFamily('Two Hand Sword'), 'Sword');
  assert.equal(T.weaponFamily('One Hand Axe'), 'Axe');
  assert.equal(T.weaponFamily('Warstaff'), 'Quarterstaff');   // the quirky rename
  assert.equal(T.weaponFamily('Bow'), 'Bow');
  assert.equal(T.weaponFamily('Sceptre'), 'Sceptre');
  assert.equal(T.weaponFamily('Talisman'), 'Talisman');       // a real caster main-hand
  assert.equal(T.weaponFamily(null), null);
  assert.equal(T.weaponFamily(''), null);
});

test('metaWeaponFamily takes the main-hand token and skips the unclassifiable', () => {
  assert.equal(T.metaWeaponFamily('Mace / Shield'), 'Mace');       // the bug: must NOT reject maces
  assert.equal(T.metaWeaponFamily('Quarterstaff'), 'Quarterstaff');
  assert.equal(T.metaWeaponFamily('Wand / Sceptre'), 'Wand');      // main-hand, not the offhand
  assert.equal(T.metaWeaponFamily('Sceptre / Focus'), 'Sceptre');
  assert.equal(T.metaWeaponFamily('Bow / Quiver'), 'Bow');
  assert.equal(T.metaWeaponFamily('Unknown / Sceptre'), null);     // poe.ninja couldn't classify -> don't enforce
  assert.equal(T.metaWeaponFamily(''), null);
  assert.equal(T.metaWeaponFamily(null), null);
});

test('charWeaponFamily reads the main-hand (not a swap or an offhand)', () => {
  const wc = { 'Giant Maul': 'Two Hand Mace', 'Execratus Hammer': 'One Hand Mace',
    'Changeling Talisman': 'Talisman', 'Twig Focus': 'Focus', 'Stoic Sceptre': 'Sceptre', 'Warmonger Bow': 'Bow', 'Visceral Quiver': 'Quiver' };
  const mk = items => ({ items: items.map(([inventoryId, baseType]) => ({ itemData: { inventoryId, baseType } })) });

  // main-set main hand wins
  assert.equal(T.charWeaponFamily(mk([['Weapon', 'Giant Maul'], ['Offhand', 'Stoic Sceptre']]), wc), 'Mace');
  // swap weapon (Weapon2) listed FIRST must not be picked over the main-set Weapon
  assert.equal(T.charWeaponFamily(mk([['Weapon2', 'Execratus Hammer'], ['Weapon', 'Changeling Talisman']]), wc), 'Talisman');
  // an offhand in the weapon slot is not a "main weapon"
  assert.equal(T.charWeaponFamily(mk([['Weapon', 'Twig Focus']]), wc), null);
  assert.equal(T.charWeaponFamily(mk([['Weapon', 'Warmonger Bow'], ['Offhand', 'Visceral Quiver']]), wc), 'Bow');
  // falls back to the swap set when there is no main-set weapon
  assert.equal(T.charWeaponFamily(mk([['Weapon2', 'Giant Maul']]), wc), 'Mace');
  assert.equal(T.charWeaponFamily({ items: [] }, wc), null);
  assert.equal(T.charWeaponFamily(mk([['Weapon', 'Giant Maul']]), null), null);
});

test('gemMapFromLua copies gameId verbatim, takes only real gem paths, never falls back to the Lua key', () => {
  const lua = [
    'local gems = {',
    '\t["Fireball"] = {',
    '\t\tname = "Fireball",',
    '\t\tgameId = "Metadata/Items/Gems/SkillGemFireball",',
    '\t},',
    '\t["Consecrate"] = {',           // genuine lowercase-`items` game data, not a typo — must survive
    '\t\tname = "Staff Consecrate",',
    '\t\tgameId = "Metadata/items/Gems/SkillGemStaffConsecrate",',
    '\t},',
    '\t["Singular"] = {',             // singular Items/Gem (no s) is real and per-gem
    '\t\tname = "Singular Gem",',
    '\t\tgameId = "Metadata/Items/Gem/SupportGemSingular",',
    '\t},',
    '\t["Bogus"] = {',                // not a gem metadata path -> excluded
    '\t\tname = "Bogus",',
    '\t\tgameId = "Metadata/Items/Armours/Foo",',
    '\t},',
    '\t["NoId"] = {',                 // no gameId -> excluded (no Lua-key fallback)',
    '\t\tname = "No Id",',
    '\t},',
    '}',
  ].join('\n');
  const m = T.gemMapFromLua(lua);
  assert.equal(m['Fireball'], 'Metadata/Items/Gems/SkillGemFireball');
  assert.equal(m['Staff Consecrate'], 'Metadata/items/Gems/SkillGemStaffConsecrate');  // lowercase preserved
  assert.equal(m['Singular Gem'], 'Metadata/Items/Gem/SupportGemSingular');            // singular preserved
  assert.equal(m['Bogus'], undefined);
  assert.equal(m['No Id'], undefined);
});

// shared fixtures for convert()/qa()
const GEM = {
  'Fireball': 'Metadata/Items/Gems/SkillGemFireball',
  'Added Fire': 'Metadata/Items/Gems/SupportGemAddedFire',
  'Controlled Destruction': 'Metadata/Items/Gems/SupportGemControlledDestruction',
};
const SLUG = { 200: 'fire_dmg', 201: 'cast_speed' };
const levelReq = n => ({ requirements: [{ name: 'Level', type: 62, values: [[String(n), 0]] }] });
const gem = (name, lvl, req) => ({ name, level: lvl, itemData: req ? levelReq(req) : { requirements: [] } });

function fixtureChar() {
  return {
    class: 'Lich',                     // -> Witch3
    level: 96,
    passiveSelection: [200, 201],
    skills: [
      { allGems: [gem('Fireball', 20, 28), gem('Added Fire', 18)], dps: [{ dps: 1000 }] },
      // a SECOND Fireball group with different supports + higher dps — dedupe must keep this one
      { allGems: [gem('Fireball', 21, 28), gem('Controlled Destruction', 20)], dps: [{ dps: 9000 }] },
    ],
    items: [
      { itemData: { inventoryId: 'BodyArmour', baseType: 'Sage Robe', frameType: 2, explicitMods: ['+80 to maximum Life'], ...levelReq(65) } },
      { itemData: { inventoryId: 'Weapon', baseType: 'Dueling Wand', frameType: 2, explicitMods: ['Adds 1 to 20 Lightning Damage'], ...levelReq(60) } },
    ],
  };
}

test('convert produces the 7-key shape, gates by level, and dedupes', () => {
  const build = T.convert(fixtureChar(), { slug: SLUG, gem: GEM, account: 'acct', name: 'char', league: 'runesofaldur' });
  assert.deepEqual(Object.keys(build).sort(),
    ['ascendancy', 'author', 'description', 'inventory_slots', 'name', 'passives', 'skills'].sort());
  assert.equal(build.ascendancy, 'Witch3');
  assert.equal(build.passives.length, 2);

  // skill dedupe keeps the higher-DPS Fireball group (the Spark-support one), not the first-seen
  const fb = build.skills.filter(s => /SkillGemFireball$/.test(s.id));
  assert.equal(fb.length, 1, 'duplicate active gem must be deduped');
  assert.deepEqual((fb[0].support_skills || []).map(s => s.id), ['Metadata/Items/Gems/SupportGemControlledDestruction']);
  assert.deepEqual(fb[0].level_interval, [28, 100]);   // gem gated by its real Level requirement

  // gear gated by the item's own required level, not [1,100]
  const body = build.inventory_slots.find(s => s.inventory_id === 'BodyArmour1');
  assert.deepEqual(body.level_interval, [65, 100]);
  const wand = build.inventory_slots.find(s => s.inventory_id === 'Weapon1');
  assert.deepEqual(wand.level_interval, [60, 100]);
});

test('qa hard-fails an off-meta-weapon build and passes an on-meta one', () => {
  const build = T.convert(fixtureChar(), { slug: SLUG, gem: GEM, account: 'a', name: 'c', league: 'runesofaldur' });
  const char = fixtureChar();   // main-hand is a Dueling Wand -> family Wand
  const weaponClass = { 'Dueling Wand': 'Wand', 'Sage Robe': null };
  const ctx = { slug: SLUG, tree: { nodes: {} }, weaponClass };

  const onMeta = T.qa(build, char, { ...ctx, md: { weapons: [{ name: 'Wand / Sceptre', pct: 40 }] } });
  assert.equal(onMeta.issues.some(i => /dominant meta weapon/.test(i.m)), false, 'wand build must satisfy a clear wand meta');

  const offMeta = T.qa(build, char, { ...ctx, md: { weapons: [{ name: 'Mace / Shield', pct: 35 }] } });
  const wepFail = offMeta.issues.find(i => /dominant meta weapon/.test(i.m));
  assert.ok(wepFail, 'wand build must be flagged against a clear mace meta');
  assert.equal(wepFail.sev, 'fail');

  // skipped when the meta weapon is unclassifiable ("Unknown")...
  const unknown = T.qa(build, char, { ...ctx, md: { weapons: [{ name: 'Unknown / Sceptre', pct: 35 }] } });
  assert.equal(unknown.issues.some(i => /dominant meta weapon/.test(i.m)), false);

  // ...and skipped for a FRAGMENTED meta (top weapon < 30%): a Spear-vs-Wand mismatch is fine
  // because no single weapon defines the ascendancy (this is the Ritualist case).
  const fragmented = T.qa(build, char, { ...ctx, md: { weapons: [{ name: 'Mace / Shield', pct: 19 }] } });
  assert.equal(fragmented.issues.some(i => /dominant meta weapon/.test(i.m)), false, 'fragmented meta must not enforce a weapon');
});

test('parsePobDefence decodes a PoB export into a defence layer (and fails safe)', () => {
  const xml = '<?xml version="1.0"?><PathOfBuilding><Build>'
    + '<PlayerStat stat="TotalEHP" value="31670.56"/>'
    + '<PlayerStat stat="Life" value="1443"/>'
    + '<PlayerStat stat="EnergyShield" value="5985"/>'
    + '<PlayerStat stat="FireResist" value="75"/>'
    + '<PlayerStat stat="ColdResist" value="75"/>'
    + '<PlayerStat stat="LightningResist" value="60"/>'
    + '<PlayerStat stat="ChaosResist" value="-12"/>'
    + '<PlayerStat stat="MeleeEvadeChance" value="47"/>'
    + '<PlayerStat stat="CritChance" value="94.0032"/>'
    + '</Build></PathOfBuilding>';
  const code = zlib.deflateSync(Buffer.from(xml, 'utf8')).toString('base64').replace(/\+/g, '-').replace(/\//g, '_');
  const d = T.parsePobDefence(code);
  assert.equal(d.ehp, 31671);                 // rounded
  assert.equal(d.life, 1443);
  assert.equal(d.es, 5985);
  assert.deepEqual(d.resists, { fire: 75, cold: 75, lightning: 60, chaos: -12 });
  assert.equal(d.evade, 47);
  assert.equal(d.crit, 94);
  assert.equal(T.parsePobDefence('not-valid-base64-$$$'), null);   // fail-safe on garbage
  assert.equal(T.parsePobDefence(''), null);
  assert.equal(T.parsePobDefence(null), null);
});

test('variantIsDistinct keeps only meaningfully-different variants (vs ALL accepted)', () => {
  const primary = { name: 'Monk — Tempest Flurry', ehp: 30000 };
  assert.equal(T.variantIsDistinct({ name: 'Monk — Falling Thunder', ehp: 30500 }, [primary]), true);   // different skill
  assert.equal(T.variantIsDistinct({ name: 'Monk — Tempest Flurry', ehp: 33000 }, [primary]), false);   // same skill, within 30% EHP
  assert.equal(T.variantIsDistinct({ name: 'Monk — Tempest Flurry', ehp: 45000 }, [primary]), true);    // same skill, >30% tankier
  const accepted = [primary, { name: 'Monk — Tempest Flurry', ehp: 45000 }];
  assert.equal(T.variantIsDistinct({ name: 'Monk — Tempest Flurry', ehp: 46000 }, accepted), false);    // near an ACCEPTED variant, not just the primary
  assert.equal(T.variantIsDistinct({ name: 'Monk — Tempest Flurry', ehp: 60000 }, accepted), true);     // far from both
  assert.equal(T.variantIsDistinct({ name: 'Monk — Tempest Flurry', ehp: 0 }, [primary]), false);       // same skill, EHP unknown → treat as dup
});

test('coverageOk refuses a throttled run below 70% of prior coverage; allows force / first run', () => {
  assert.equal(T.coverageOk(5, 20, false), false);   // 25% -> refuse (would lose most ascendancies)
  assert.equal(T.coverageOk(15, 20, false), true);   // 75% -> ok
  assert.equal(T.coverageOk(14, 20, false), true);   // ceil(20*0.7)=14 -> exactly at threshold, ok
  assert.equal(T.coverageOk(13, 20, false), false);  // 65% -> refuse
  assert.equal(T.coverageOk(5, 20, true), true);     // --force overrides
  assert.equal(T.coverageOk(5, 0, false), true);     // first run / no prior meta-detail
});

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

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

module.exports = { normKey, cleanMarkup };

'use strict';
/*
 * Front-end pure-helper locks. index.html has no module system, so — as in test-contracts.cjs —
 * we extract the helper source straight from index.html and exercise it in Node. This keeps the
 * single-file front end intact (no js/*.js split, no extra request) while still putting the
 * honesty- and safety-critical pure functions under test.
 *   node --test tools/test-frontend.cjs
 *
 * Locked here:
 *   esc      — HTML escaping. A regression re-opens XSS in every interpolated field.
 *   fmt      — number display. A regression silently garbles every count/stat on the page.
 *   relTime  — relative time. MUST floor (never round up) so "refreshed hourly" is never
 *              overstated — 31 min is "31 min ago", 90 min is "1 hour ago", never the next bucket.
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
function extract(re, label) {
  const m = html.match(re);
  if (!m) throw new Error(`front-end test could not find ${label} in index.html — did it get renamed?`);
  return m[1];
}
// single-line arrow helpers: `const NAME = ARG => <expr>;`
const esc = eval('(' + extract(/const esc\s*=\s*(s =>.*);\r?$/m, 'esc') + ')');
const fmt = eval('(' + extract(/const fmt\s*=\s*(n =>.*);\r?$/m, 'fmt') + ')');
// multi-line function with no nested braces in its body:
const relTime = new Function('iso', extract(/function relTime\s*\(iso\)\s*\{([\s\S]*?)\n\}/, 'relTime'));

test('esc (index.html) escapes every HTML-significant character', () => {
  assert.equal(esc('<b>&"\'</b>'), '&lt;b&gt;&amp;&quot;&#39;&lt;/b&gt;');
  assert.equal(esc('a & b'), 'a &amp; b');
  assert.equal(esc(null), '');
  assert.equal(esc(undefined), '');
  assert.equal(esc('plain text 123'), 'plain text 123');
  // ampersand must be escaped first, or the others double-escape:
  assert.equal(esc('&amp;'), '&amp;amp;');
});

test('fmt (index.html) formats numbers and renders null as an em dash', () => {
  assert.equal(fmt(null), '—');
  assert.equal(fmt(undefined), '—');
  assert.equal(fmt(0), '0');
  assert.equal(fmt(1000), '1,000');
  assert.equal(fmt(1234567), '1,234,567');
});

test('relTime (index.html) FLOORS every bucket — freshness is never overstated', () => {
  const ago = ms => new Date(Date.now() - ms).toISOString();
  const MIN = 60000, HR = 3600000, pad = 5000; // pad keeps each case clear of its bucket edge
  assert.equal(relTime(ago(500)), 'just now');
  assert.equal(relTime(ago(2 * MIN + pad)), '2 min ago');
  assert.equal(relTime(ago(31 * MIN + pad)), '31 min ago');   // NOT rounded to "1 hour ago"
  assert.equal(relTime(ago(59 * MIN + pad)), '59 min ago');
  assert.equal(relTime(ago(90 * MIN + pad)), '1 hour ago');   // NOT "2 hours ago"
  assert.equal(relTime(ago(5 * HR + pad)), '5 hours ago');
  assert.equal(relTime(new Date(Date.now() + 60000).toISOString()), 'just now'); // future clamps to 0
});

// --- The Counterpoise: hash helpers (Task 1) ---
const parseCompareHash = new Function('hash','known',
  extract(/function parseCompareHash\s*\([^)]*\)\s*\{([\s\S]*?)\n\}/, 'parseCompareHash'));
const compareHashOf = new Function('slugs',
  extract(/function compareHashOf\s*\([^)]*\)\s*\{([\s\S]*?)\n\}/, 'compareHashOf'));

test('parseCompareHash filters to known slugs, dedupes, caps at 3', () => {
  const known = ['titan','deadeye','oracle','lich'];
  assert.deepEqual(parseCompareHash('#compare=titan,deadeye', known), ['titan','deadeye']);
  assert.deepEqual(parseCompareHash('compare=titan,deadeye', known), ['titan','deadeye']); // tolerate missing #
  assert.deepEqual(parseCompareHash('#compare=TITAN, Deadeye ', known), ['titan','deadeye']); // case/space
  assert.deepEqual(parseCompareHash('#compare=titan,titan,deadeye', known), ['titan','deadeye']); // dedupe
  assert.deepEqual(parseCompareHash('#compare=titan,bogus,oracle', known), ['titan','oracle']); // unknown dropped
  assert.deepEqual(parseCompareHash('#compare=titan,deadeye,oracle,lich', known), ['titan','deadeye','oracle']); // cap 3
  assert.deepEqual(parseCompareHash('', known), []);
  assert.deepEqual(parseCompareHash('#compare=', known), []);
});

test('compareHashOf round-trips with parseCompareHash', () => {
  const known = ['titan','deadeye','oracle'];
  assert.equal(compareHashOf([]), '');
  assert.equal(compareHashOf(['titan','deadeye']), '#compare=titan,deadeye');
  assert.deepEqual(parseCompareHash(compareHashOf(['titan','deadeye','oracle']), known), ['titan','deadeye','oracle']);
});

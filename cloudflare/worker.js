/**
 * Tincture OAuth Worker — the server-side half a static site can't do: GGG's
 * authorization_code + PKCE flow for the account:characters scope, so a logged-in user can
 * export THEIR OWN PoE2 character as a loadable .build ("Decant my character").
 *
 * Why a Worker: GitHub Pages has no server to hold the client_secret or run the token
 * exchange. A Cloudflare Worker (free tier) gives Tincture a tiny serverless backend at
 * e.g. https://tincturepoe2.com/api/* while keeping the site itself static.
 *
 * ⚠️ UNTESTED — written to the GGG developer docs but never run against live GGG servers
 * (no approved client yet). Treat every endpoint/param as VERIFY-LIVE. See cloudflare/README.md.
 *
 * Flow:
 *   GET /api/oauth/login      -> redirect the user to GGG's consent screen (PKCE challenge)
 *   GET /api/oauth/callback   -> exchange the code for a per-user token, stash it in a
 *                                short-lived httpOnly cookie, bounce back to the site
 *   GET /api/characters       -> list the consenting user's PoE2 characters (summaries)
 *   GET /api/character?name=  -> that user's character WITH passives+items (for .build)
 *   GET /api/logout           -> clear the session
 *
 * Secrets (wrangler secret put ...): GGG_CLIENT_ID, GGG_CLIENT_SECRET, COOKIE_SECRET.
 * Vars (wrangler.toml): SITE_ORIGIN (e.g. https://tincturepoe2.com), REDIRECT_URI.
 */

const GGG_AUTHORIZE = 'https://www.pathofexile.com/oauth/authorize';
const GGG_TOKEN = 'https://www.pathofexile.com/oauth/token';
const GGG_API = 'https://api.pathofexile.com';
const SCOPE = 'account:characters';
const REALM = 'poe2';
const VERSION = '0.5.0';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const ua = `OAuth ${env.GGG_CLIENT_ID}/${VERSION} (contact: ryan.duke360@gmail.com)`;
    // CORS preflight: a credentialed cross-origin GET (e.g. from the *.workers.dev fallback
    // origin) sends OPTIONS first, which must answer with the allowed methods/headers.
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders(env, {
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Max-Age': '86400',
      }) });
    }
    try {
      switch (url.pathname) {
        case '/api/oauth/login':    return login(url, env);
        case '/api/oauth/callback': return callback(request, url, env, ua);
        case '/api/characters':     return proxy(request, env, ua, `/character/${REALM}`);
        case '/api/character':      return proxy(request, env, ua, `/character/${REALM}/${encodeURIComponent(url.searchParams.get('name') || '')}`);
        case '/api/logout':         return new Response(null, { status: 302, headers: { Location: env.SITE_ORIGIN, 'Set-Cookie': clearCookie() } });
        default:                    return json({ error: 'not found' }, 404, env);
      }
    } catch (e) {
      // never forward internal/upstream error detail to the client
      console.error('worker error:', (e && e.stack) || e);
      return json({ error: 'internal error' }, 500, env);
    }
  },
};

// 1) kick off consent with a fresh PKCE verifier + CSRF state, both stashed in a signed cookie
async function login(url, env) {
  const verifier = b64url(crypto.getRandomValues(new Uint8Array(32)));
  const state = b64url(crypto.getRandomValues(new Uint8Array(16)));
  const challenge = b64url(new Uint8Array(await crypto.subtle.digest('SHA-256', enc(verifier))));
  // short TTL for the consent leg — an abandoned login shouldn't leave the verifier/state
  // lingering for an hour; it's replaced by the session cookie on a successful callback.
  const cookie = await signCookie({ verifier, state }, env.COOKIE_SECRET, 600);
  const authUrl = `${GGG_AUTHORIZE}?` + new URLSearchParams({
    client_id: env.GGG_CLIENT_ID, response_type: 'code', scope: SCOPE,
    state, redirect_uri: env.REDIRECT_URI, code_challenge: challenge, code_challenge_method: 'S256',
  });
  return new Response(null, { status: 302, headers: { Location: authUrl, 'Set-Cookie': cookie } });
}

// 2) exchange the code (+ verifier) for the user's access token; keep it httpOnly cookie-side
async function callback(request, url, env, ua) {
  const code = url.searchParams.get('code'), state = url.searchParams.get('state');
  const sess = await readCookie(request.headers.get('Cookie'), env.COOKIE_SECRET).catch(() => null);
  if (!code || !sess || sess.state !== state) return json({ error: 'bad oauth state' }, 400, env);
  const body = new URLSearchParams({
    client_id: env.GGG_CLIENT_ID, client_secret: env.GGG_CLIENT_SECRET, grant_type: 'authorization_code',
    code, redirect_uri: env.REDIRECT_URI, code_verifier: sess.verifier, scope: SCOPE,
  });
  const r = await fetch(GGG_TOKEN, { method: 'POST', headers: { 'User-Agent': ua, 'Content-Type': 'application/x-www-form-urlencoded' }, body });
  if (!r.ok) return json({ error: 'token exchange failed', status: r.status }, 502, env);
  const tok = await r.json();
  // tie the cookie's Max-Age to the real token lifetime (clamped) so it doesn't outlive the token
  const ttl = Math.max(60, Math.min(Number(tok.expires_in) || 3600, 86400));
  const session = await signCookie({ access_token: tok.access_token, exp: Date.now() + ttl * 1000 }, env.COOKIE_SECRET, ttl);
  return new Response(null, { status: 302, headers: { Location: `${env.SITE_ORIGIN}/#decant-mine`, 'Set-Cookie': session } });
}

// 3) proxy a GGG character endpoint with the user's token (self-only, by GGG design)
async function proxy(request, env, ua, apiPath) {
  const sess = await readCookie(request.headers.get('Cookie'), env.COOKIE_SECRET).catch(() => null);
  if (!sess || !sess.access_token || (sess.exp && sess.exp < Date.now())) return json({ error: 'not authenticated' }, 401, env);
  const r = await fetch(GGG_API + apiPath, { headers: { 'User-Agent': ua, Authorization: `Bearer ${sess.access_token}`, Accept: 'application/json' } });
  // forward the (needed) character JSON on success, but never the raw upstream error body/headers
  if (!r.ok) return json({ error: 'upstream error', status: r.status }, r.status === 401 ? 401 : 502, env);
  return new Response(await r.text(), { status: 200, headers: corsHeaders(env, { 'Content-Type': 'application/json' }) });
}

// ---- helpers ----
const enc = s => new TextEncoder().encode(s);
const b64url = buf => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
function corsHeaders(env, extra) { return { 'Access-Control-Allow-Origin': env.SITE_ORIGIN, 'Access-Control-Allow-Credentials': 'true', 'Vary': 'Origin', ...(extra || {}) }; }
function json(obj, status, env) { return new Response(JSON.stringify(obj), { status: status || 200, headers: corsHeaders(env, { 'Content-Type': 'application/json' }) }); }

// signed (HMAC) cookie so the verifier/token can't be tampered with; httpOnly + Secure
async function hmac(secret, data) { const key = await crypto.subtle.importKey('raw', enc(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']); return b64url(await crypto.subtle.sign('HMAC', key, enc(data))); }
async function signCookie(obj, secret, maxAge = 3600) { const p = b64url(enc(JSON.stringify(obj))); const sig = await hmac(secret, p); return `tinct=${p}.${sig}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=${maxAge}`; }
async function readCookie(cookieHeader, secret) {
  const m = (cookieHeader || '').match(/tinct=([^;]+)/); if (!m) throw new Error('no cookie');
  const [p, sig] = m[1].split('.'); if ((await hmac(secret, p)) !== sig) throw new Error('bad sig');
  return JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(p.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0))));
}
const clearCookie = () => 'tinct=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0';

# Tincture OAuth Worker — "Decant my character"

A tiny Cloudflare Worker that does the one thing a static GitHub Pages site can't: GGG's
**authorization_code + PKCE** OAuth flow, so a logged-in player can export **their own** PoE2
character as a loadable `.build`. (The public-ladder meta builds don't need this — they're
reconstructed from poe.ninja. This is only for "export *my* character", which GGG's
`account:characters` scope restricts to the consenting user.)

> ⚠️ **Untested.** `worker.js` is written to the GGG developer docs but has never run against
> live GGG servers (no approved client yet). Treat endpoints/params as **verify-live**, and
> test with your real client before relying on it.

## Prerequisites
1. An **approved GGG OAuth client** (`oauth@grindinggear.com` — see `../docs/owner-actions.md`),
   **confidential**, grant `authorization_code` + PKCE, scope `account:characters`, redirect URI
   `https://tincturepoe2.com/api/oauth/callback` (must match `REDIRECT_URI` in `wrangler.toml`).
2. A free **Cloudflare account**, and ideally the `tincturepoe2.com` zone on Cloudflare so the
   Worker can serve from `/api/*` (owner-actions.md #3). Without the zone it still runs at
   `https://tincture-oauth.<subdomain>.workers.dev/api/*` — set that as `SITE_ORIGIN`/redirect
   instead, and register that redirect with GGG.

## Deploy
```bash
cd cloudflare
npm i -g wrangler            # or: npx wrangler ...
wrangler secret put GGG_CLIENT_ID
wrangler secret put GGG_CLIENT_SECRET
wrangler secret put COOKIE_SECRET     # any long random string (signs the session cookie)
wrangler deploy
```

## Endpoints
| Route | Purpose |
|---|---|
| `GET /api/oauth/login` | Redirect the user to GGG's consent screen (PKCE). |
| `GET /api/oauth/callback` | Exchange the code for a per-user token; store it in an httpOnly cookie; bounce back to the site. |
| `GET /api/characters` | List the consenting user's PoE2 characters (summaries). |
| `GET /api/character?name=<name>` | That user's character **with** passives + items. |
| `GET /api/logout` | Clear the session. |

## Wiring into Tincture
Add an "Export **my** character" button that links to `/api/oauth/login`. After consent the
user lands back on the site (`/#decant-mine`); call `/api/characters`, let them pick one, fetch
`/api/character?name=…`, then convert the returned GGG JSON to a `.build` with the **same
logic** as `tools/build-from-ninja.cjs` (`convert()` + the cohesion QA — the passive→slug and
gem→metadata maps already exist there). Two reasonable shapes:
- **Worker-side convert** (recommended): port `convert()`/`qa()` into the Worker and have it
  fetch the GGG tree export + PoB2 `Gems.lua` once (cache in a KV namespace), so `/api/character`
  returns a ready `.build`. Keeps the heavy maps off the client.
- **Client-side convert**: return raw GGG JSON and convert in the browser (needs the slug/gem
  maps loaded client-side — larger download).

## Security notes
- The `client_secret` lives only as a Worker secret, never in the static site or this repo.
- The session cookie is `HttpOnly; Secure; SameSite=Lax`, HMAC-signed with `COOKIE_SECRET`,
  and holds only a short-lived access token (no refresh token persisted here).
- `account:characters` is **self-only** by GGG design — this can never read another player's
  characters, which is the privacy guarantee to surface in the UI.

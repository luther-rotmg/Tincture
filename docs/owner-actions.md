# Owner actions — things only you (Ryan) can do

Everything in here needs an account, an email, a paid service, or your own game data — so
it can't be automated. Each item says what it unlocks and how hard it is. Most code-side
groundwork is already done (see notes).

---

## 1. Register a GGG PoE2 API OAuth client  — *moderate; free; ~1–4 week manual approval*

Email **oauth@grindinggear.com**. There is no self-serve portal.

> ⚠️ GGG's docs state they **immediately reject low-effort or LLM-generated requests.**
> Do **not** paste AI-written text. Write the email yourself, in your own voice — the
> skeleton below is only a checklist of what to cover.

Your application must include:

1. **PoE account name with discriminator** — e.g. `luther#1234`.
2. **Application name** — `Tincture`.
3. **Client type** — **confidential** (you need a `client_secret` for the ladder's
   service scope; public clients can't get service scopes).
4. **Grant type(s)** — `client_credentials` (for the ladder) and, if you want
   "Decant my character", `authorization_code` + PKCE (for `account:characters`).
5. **Scopes, each justified**:
   - `service:leagues:ladder` — "read the Runes of Aldur ladder to cross-check the
     ascendancy-share meta my site already shows from poe.ninja, so it's not single-sourced."
   - `account:characters` *(optional)* — "let a logged-in user export **their own**
     character as a loadable build file. Self-only; I never read other players' characters."
6. **Redirect URI(s)** — for the confidential/ladder use you don't strictly need one;
   for `account:characters` you need an HTTPS redirect on a domain you control
   (e.g. `https://tincturepoe2.com/oauth/callback`) **or** a local `http://localhost:PORT/...`
   for a CLI tool.

What it unlocks: the **official ladder cross-check** (item 4 below) and a future
**"Decant my character"** feature. It does **not** unlock decanting arbitrary ladder
players (see "the honest boundary" below).

**Heads-up on secrets:** a static GitHub Pages site has no server to hold a `client_secret`.
Realistic options: (a) run the ladder cross-check from the **GitHub Action** (store the
secret as a repo secret — it already runs the hourly job), or (b) a tiny serverless
function (Cloudflare Workers free tier) for the per-user token exchange. Code-side, the
client is already wired: `scripts/ggg.py` (correct endpoints/scopes) just needs
`GGG_CLIENT_ID` / `GGG_CLIENT_SECRET` (and `GGG_USER_TOKEN` for the self-character path).

---

## 2. Say hello to poe.ninja  — *easy; free*

poe.ninja (run solo by "Rasmus") publishes **no terms of service and no rate-limit
headers**, and your site republishes its data. The hourly job is well within any plausible
limit (the endpoint is server-cached for 30 min), but the courteous move before leaning on
it harder is a quick message in the **poe.ninja Discord** (https://discord.gg/7qSRyKdyre)
introducing Tincture and asking if automated/derived use is OK.

Code-side: **done** — `distill.py` now sends a descriptive, contactable User-Agent so
Rasmus can reach you instead of just blocking the IP. (Swap the contact email if you'd
rather not expose a personal one.)

---

## 3. Custom domain + Cloudflare + privacy-first analytics  — *easy; domain you already own*

You already have **tincturepoe2.com**. Fronting GitHub Pages with **Cloudflare** (free CDN,
HTTPS, DDoS protection) and adding **Cloudflare Web Analytics** (cookieless, no banner,
no PII) would finally tell you whether anyone uses the site **without** breaking the
"no tracking / no browser storage" principle. Needs a free Cloudflare account + a DNS change.

---

## 4. Loadable Decant — the data path (mostly solved!)

The two mappings previously called the blockers are now resolved **from public data**:

- ✅ **Passive node-id → `.build` slug**: GGG's public skill-tree export
  (`github.com/grindinggear/poe2-skilltree-export`) carries the slug on every node
  (`node.id` = `"attack_speed25"`). `scripts/treedata.py` derives the numeric↔slug map
  on demand — no GGPK extraction needed.
- ✅ **Ascendancy code table**: filled in `scripts/buildfile.py` from the same export and
  cross-confirmed (`Martial Artist → Monk1`). `python scripts/treedata.py --check`
  re-verifies it against the live export each patch.

**What's left, and the honest boundary:**

- The **gem → metadata path** mapping (`extract_skills` in `ggg.py`) still needs one real
  PoE2 `--character` response to confirm where gems live and their exact
  `Metadata/Items/Gem(s)/…` strings. *(Your own export covers this — see item 5.)*
- ⛔ **You cannot decant an arbitrary ladder player's build.** GGG's `account:characters`
  is **self-only**, and the ladder API returns **summary only** (no passives/equipment).
  So loadable Decant is realistically a **"export *my* character"** feature for a
  logged-in user — not "decant any meta build." The aggregate site meta stays an honest
  ascendancy template. (This is now reflected in `ggg.py`.)

> ⚠️ Licensing: the tree export has **no license** (all rights reserved). Deriving from it
> for tooling is customary (PoB etc.), but **don't commit GGG's `data.json` or a wholesale
> derived copy** into the repo — `treedata.py` downloads + derives at runtime, which keeps
> us clean. Keep the GGG non-affiliation disclaimer (already in the footer).

## 5. Export a few of your own `.build` files  — *moderate; free; needs PoE2*

Export 2–3 real builds you control from the in-game Build Planner. Diffing them against the
Character API gives ground-truth for the **gem metadata paths** and confirms the **slug
underscore variants** (`attack_speed2_` vs `attack_speed2`) — the last bits needed to make
"export my character" produce a genuinely loadable file. Strictly your own data, so it
sidesteps the "don't republish other people's builds" rule.

---

## 6. Optional: sustainability  — *easy; free to set up*

A project GitHub org (cleaner than a personal handle for a public tool) and a
Ko-fi / Buy-Me-a-Coffee link to offset the domain cost. GitHub Sponsors works too but needs
identity/tax/Stripe onboarding to actually receive money.

---

## 7. Turn on "Export my character"  — *moderate; needs items 1 + 5 first*

The whole **front-end** for this is already built and verified, but it ships **dormant**:
`index.html` has `const SELF_EXPORT_ENABLED = false`, so the "export my own character" link
stays hidden and the `#decant-mine` return route no-ops. Nothing about it touches the live
site until you flip that flag. The flow it drives: sign in with your PoE account → pick one
of **your own** characters (a small dialog) → the worker fetches it → the page saves a
loadable `.build` **only if the worker returns a real one** (it never fabricates a `.build`).

To enable it, in order:

1. **Register the GGG OAuth client** (item 1) with `authorization_code` + PKCE and the
   `account:characters` scope, and set the redirect URI to
   `https://tincturepoe2.com/api/oauth/callback`.
2. **Deploy the Cloudflare Worker** (`cloudflare/worker.js`, see `cloudflare/README.md`):
   - Route it at `tincturepoe2.com/api/*` (so the site and the API share an origin — the
     front-end calls relative `/api/...` paths).
   - `wrangler secret put GGG_CLIENT_ID GGG_CLIENT_SECRET COOKIE_SECRET`.
   - Set `SITE_ORIGIN` and `REDIRECT_URI` vars in `wrangler.toml`.
3. **Finish the conversion** (item 5): the worker's `/api/character` currently proxies the
   **raw** GGG character JSON. Use one real `--character` response to confirm the
   `gem → Metadata/Items/Gem(s)/…` paths (and the slug underscore variants), then have the
   worker return a serialized `.build` (reuse `buildfile.py`'s serializer logic) instead of
   raw JSON. Until this step, the front-end shows an honest "not enabled yet" message rather
   than saving anything — so flipping the flag early degrades gracefully, it doesn't lie.
4. **Verify**, then flip the flag: with the worker live, `GET /api/characters` should return
   `401 {"error":"not authenticated"}` (a JSON 401, not an HTML 404). Walk the flow once on
   the live site. When `/api/character` returns a genuine `.build`, set
   `SELF_EXPORT_ENABLED = true` in `index.html` and commit.

> The page distinguishes a real `.build` from JSON purely by `Content-Type` (anything that
> isn't `application/json`/`text/html` and is non-empty is treated as a build), matching how
> `decant()` already guards the public reconstructions. Keep the worker's success response
> `Content-Type` accordingly.

---

### Already done for you (code side)
- `buildfile.py` — full, cross-confirmed ascendancy-code table.
- `treedata.py` — derives the passive slug map + ascendancy codes from the GGG export (`--slugs` / `--codes` / `--check`).
- `ggg.py` — corrected endpoints/scopes/auth model, honest self-only/ladder-summary framing, wired to `treedata`.
- `cloudflare/worker.js` — PKCE OAuth flow + self-only character proxy, hardened (constant-time cookie HMAC, token-lifetime cookies, generic errors). Untested against live GGG (no client yet) — see `cloudflare/README.md`.
- `index.html` — the **dormant** "export my character" front-end: login link, character picker, and save-only-a-real-`.build` flow, all behind `SELF_EXPORT_ENABLED` (item 7). Verified locally with a mocked worker.
- `distill.py` — contactable User-Agent for poe.ninja.
- Social card (`docs/og.png`), `docs/demo.svg`, `robots.txt`, `sitemap.xml`, OG/Twitter/JSON-LD meta.

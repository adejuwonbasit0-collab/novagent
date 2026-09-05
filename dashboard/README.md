# Nova Dashboard

Web control panel for the Nova assistant platform (spec section 26): account
auth, device management, reminders, and a chat interface to the assistant
itself. Next.js 14 (App Router), TypeScript, Tailwind.

## Design

Utility control surface, not a marketing site — near-black background,
indigo/teal/amber/coral accent system, Space Grotesk (headings) + Inter
(body) + JetBrains Mono (device IDs, timestamps, tokens). The header's state
ring (`components/StateRing.tsx`) deliberately mirrors the desktop agent's
floating bubble state indicator — same idle/listening/thinking/executing
visual language on both surfaces, so the dashboard reads as *the same
assistant* viewed from a browser, not a disconnected admin panel.

## Layout

```
lib/
  api.ts      typed fetch client for every backend endpoint used here,
              with automatic access-token refresh on a 401
  auth.tsx    React context for current-user state; useRequireAuth()
              redirects to /login when there's no session
components/
  StateRing.tsx   the shared idle/listening/thinking/executing indicator
app/
  login/, register/     auth pages
  dashboard/
    layout.tsx           sidebar nav + auth guard
    page.tsx              overview (device/reminder counts)
    devices/page.tsx       list, revoke, remove devices
    permissions/page.tsx   toggle each PermissionScope, grouped with a
                            plain-language description and risk-level tag
    reminders/page.tsx     create/complete/delete reminders
    assistant/page.tsx     chat UI — implements the same confirmation flow
                            as the desktop agent (REQUIRES_CONFIRMATION ->
                            modal -> POST /confirm/{pending_id})
    admin/page.tsx          users/devices/audit-logs, admin-only (nav link
                            hidden client-side for non-admins; the real
                            enforcement is server-side via get_current_admin)
    voice/page.tsx          upload voice samples, train a voice profile,
                            pick a delivery tone, preview synthesized audio
```

## Security: httpOnly cookies, not localStorage

Tokens never reach the browser's JS. `/api/auth/login` calls the backend,
gets the access/refresh tokens, and sets them as `httpOnly` cookies on its
own response — the client only ever sees `{ok: true}`. Every other
authenticated call goes through `/api/proxy/[...path]`, which reads the
cookie server-side, attaches the bearer token, and forwards the request;
on a 401 it does exactly one silent refresh (using the httpOnly refresh
cookie) before giving up, rewriting the cookie with the new token pair.

This closes the tradeoff the previous version of this README flagged
(`localStorage` tokens are readable by any injected script). One
consequence: `NEXT_PUBLIC_BACKEND_URL` became plain `BACKEND_URL` — the
backend's address no longer needs to ship in the client bundle at all,
since the browser only ever talks to this app's own `/api/*` routes now.

**Verified, not assumed**, against a live backend and a real
`next start` production server (not just `next dev`):
- Login sets both cookies with `HttpOnly; SameSite=Lax` (and `Secure` in
  production mode) — confirmed via raw `Set-Cookie` headers, not just
  reading the code
- A request with the cookie succeeds; the identical request with **no**
  cookie gets a clean `401`
- POST with a JSON body (creating a reminder) correctly forwards through
  the proxy
- Logout clears both cookies (`Max-Age=0`), and a subsequent request with
  the (now-cleared) jar fails as expected
- **The actual refresh-on-401 path** — not just the happy path: forged an
  already-expired access token, kept a real refresh token, called the
  proxy, and confirmed it silently refreshed and returned real user data
  with a fresh (non-forged) access token written back to the cookie

One caveat worth knowing rather than discovering later: curl's cookie jar
doesn't enforce the `Secure` attribute the way real browsers do, so a
curl-based test can appear to pass in a configuration (production mode
over plain HTTP) where an actual browser might refuse to send the cookie.
`secure: true` whenever `NODE_ENV=production` is the correct default for
a real deployment (which should be HTTPS anyway) — just don't take a
curl-only pass as proof it'll work in a browser under those exact
conditions. Test with `npm run dev` locally, or put the production build
behind real TLS.

## Setup

```bash
npm install
cp .env.local.example .env.local   # point BACKEND_URL at your backend
npm run dev
```

The backend no longer needs `CORS_ORIGINS` to include the dashboard's
origin — the browser only ever calls this app's own same-origin `/api/*`
routes now; the server-to-server call from those routes to the backend
isn't subject to browser CORS at all. (`CORS_ORIGINS` is still needed for
the browser extension, which does call the backend directly.)

## Verified

- `npx tsc --noEmit` — zero type errors
- `npm run build` — full production build succeeds; all 17 routes
  correctly built (verified with a temporary system-font layout, since
  this sandbox's network egress doesn't reach fonts.googleapis.com; the
  shipped `app/layout.tsx` uses `next/font/google` as intended — any real
  dev machine or CI runner has that access)
- The full httpOnly cookie flow — see the security section above for
  specifics — was run against a real `next start` server and a live
  backend instance, including the refresh-on-401 path with a genuinely
  forged expired token, not just the happy path
- The proxy route's multipart-upload and binary-response handling
  (needed for voice sample uploads and synthesized audio): uploaded a
  real WAV file through `/api/proxy/voice/samples` with cookie auth, and
  fetched synthesized audio back through `/api/proxy/voice/synthesize` —
  confirmed the returned bytes were still a genuine, parseable WAV file
  after passing through the proxy's JSON-vs-binary passthrough logic

## Known tradeoffs, stated plainly

- **`next@14.2.35`, not the latest major.** `npm audit` flags several
  advisories that only fully resolve on Next 16, which changes enough of
  the data-fetching/caching model that I didn't want to force it without
  verifying every page against it first. 14.2.35 has the patches available
  in the 14.x line; upgrading to 16 is a reasonable next step, done
  deliberately rather than silently.

## Not built yet

- Device installer download flow — actual signed installers/EAS builds
  (spec section 32); the Downloads page currently points to source +
  local setup instructions instead
- Onboarding/assistant-personality configuration (spec section 15)
- Billing/subscription UI

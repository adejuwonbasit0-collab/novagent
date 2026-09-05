# Nova — Personal AI Operating Assistant Platform

One account, four ways to reach the same assistant: a web dashboard (the
"site"), a desktop agent, a browser extension, and a backend API tying them
together. This is a single project — start the backend first, then run
whichever client(s) you want.

```
nova-platform/
├── backend/            FastAPI + PostgreSQL — auth, devices, permissions,
│                        reminders, tool registry, AI orchestration (Claude
│                        tool-use), WebSocket device-command channel with
│                        Redis-backed multi-instance dispatch
├── dashboard/           Next.js web app — the "site." Account management,
│                        device/permission control, reminders, assistant
│                        chat, and a Downloads page for the other clients.
│                        Tokens live in httpOnly cookies via a small
│                        backend-for-frontend layer, never in browser JS.
├── desktop-agent/       PySide6 floating assistant bubble — the only client
│                        that can actually control the local OS (open apps,
│                        lock/shut down the machine, etc.), via a live
│                        WebSocket connection to the backend
├── browser-extension/   Manifest V3 Chrome extension — lightweight chat
│                        and reminders from the toolbar, no OS access, with
│                        on-demand (not background) page-content reading
└── mobile/              Expo (React Native) app — iOS/Android, chat and
                          reminders, tokens in native Keychain/Keystore via
                          expo-secure-store
```

## Why one backend, several clients

Every client authenticates against the same `backend/` API and the same
account. The dashboard and extension use short-lived user tokens; the
desktop agent registers itself as a **device** with its own token (so it
can be revoked independently of the account — see `backend/app/api/v1/devices.py`).
Whatever you do in one client — set a reminder, grant a permission — is
immediately visible in the others, because there's exactly one source of
truth: the backend's database.

## Quickstart

**1. Backend (required by everything else)**

```bash
cd backend
cp .env.example .env   # set JWT_SECRET_KEY; ANTHROPIC_API_KEY if you want /assistant/chat to work
docker compose up -d   # postgres + redis
pip install -r requirements.txt
alembic revision --autogenerate -m "init schema" && alembic upgrade head
uvicorn app.main:app --reload
```

**2. Pick your client(s):**

```bash
# Web dashboard
cd dashboard && npm install && npm run dev        # http://localhost:3000

# Desktop agent
cd desktop-agent && pip install -r requirements.txt && python main.py

# Browser extension
# Chrome/Chromium → chrome://extensions → Developer mode → Load unpacked
# → select the browser-extension/ folder

# Mobile app
cd mobile && npm install && npx expo start   # scan the QR code with Expo Go
```

The dashboard's **Get Nova** page (`/dashboard/downloads`) is where a
signed-in user is pointed at the desktop agent and extension — described
honestly as "included in this project" with real setup instructions,
rather than fake download buttons that don't link anywhere (there's no
hosted release yet; these are source-distributed, run-locally clients).

## What's real vs. what's a stub

Every piece listed as "implemented" below has been run and tested against
a live instance of the backend during development — not just written and
assumed to work. Specifics are in each sub-project's own README:
`backend/README.md`, `dashboard/README.md`, `desktop-agent/README.md`.

**Implemented and verified:**
- Full auth (register/login/refresh), device registration & revocation
- Permission system (16 scopes, grant/revoke via API and dashboard toggle)
- Reminders (full CRUD, both REST and as an AI-callable tool)
- Tool registry with permission/risk/confirmation gating — a high-risk tool
  (`shutdown_computer`) cannot self-approve via the LLM; it always requires
  a separate, explicit user confirmation against a persisted pending-action
  row
- AI orchestration: natural language → Claude tool-use → gated tool
  execution → response, in `/api/v1/assistant/chat`
- WebSocket device-command channel: the backend can push a real command
  (lock, shutdown, open an app) to a specific connected desktop agent and
  get a real result back — proven with an actual socket connection and
  round-trip test, not mocked
- **Multi-instance WebSocket dispatch via Redis pub/sub** — a command
  reaches the right device even when the REST request lands on a
  *different* backend process than the one the device is connected to.
  Proven with two genuinely separate `uvicorn` processes sharing one
  Redis instance: device connects to instance A, the tool-execute call
  hits instance B, and the command still round-trips correctly. Redis
  being unreachable fails fast (bounded connect/ping timeouts) and falls
  back to single-instance mode automatically rather than hanging app
  startup — also verified directly.
- Desktop agent: floating bubble, chat panel, OS control (Windows/macOS/
  Linux), device auth with an encrypted local-fallback token store
- Browser extension: login, chat, confirmation flow, and real on-demand
  page summarization — `chrome.scripting.executeScript` reads the active
  tab's text only when the user clicks "Summarize this page" (never a
  background content script watching every page), strips nav/script/
  style/footer noise, and sends up to 6,000 characters to the assistant.
  Its extraction logic was tested against real HTML via jsdom (confirmed
  boilerplate is stripped and real content survives), and its `api.js` was
  run against a live backend the same way the dashboard's client was.
  `host_permissions` is scoped to the backend's own origin only — no
  `<all_urls>` wildcard, no always-on content script.
- Dashboard: 8 pages (overview, downloads, devices, permissions,
  reminders, assistant, login, register), full TypeScript, verified
  production build. Auth tokens live in httpOnly cookies via a small
  backend-for-frontend layer (`app/api/auth/*`, `app/api/proxy/*`) —
  never in `localStorage`, never reachable by browser JS. The full flow,
  including the refresh-on-401 path with a deliberately forged expired
  token, was run against a real `next start` server and a live backend.
- Mobile app (Expo/React Native): login, reminders, assistant chat with
  the same confirmation-modal flow as every other client. Verified in
  layers this sandbox actually allowed: `tsc --noEmit` clean; a real
  Metro bundler export (`expo export --platform web`) compiled all 170
  modules with zero errors; and — the part that actually matters — the
  client's token/refresh logic was run standalone against a live backend
  with an in-memory mock standing in for the native Keychain/Keystore
  module, including a forged-expired-token refresh test identical in
  spirit to the dashboard's. One honest finding along the way:
  `expo-secure-store`'s *web-platform* shim doesn't fully work outside a
  real browser — specific to a bundler-testing convenience, not the
  actual iOS/Android distribution target, which uses a different,
  well-established native code path. See `mobile/README.md` for the full
  breakdown.
- Admin dashboard (`/api/v1/admin/*` + `/dashboard/admin`): user
  list/suspend/reactivate/role-change, platform-wide device oversight
  with revoke, audit log inspection, aggregate stats. Every route
  requires admin/super-admin role (403 otherwise, verified directly); an
  admin can't suspend or change their own role (verified); a suspension
  invalidates an already-issued token immediately (verified); and the
  full flow was confirmed working through the dashboard's httpOnly
  cookie proxy, not just via direct bearer-token calls to the backend.
- **Voice training** (`/api/v1/voice/*` + `/dashboard/voice`): upload
  samples of your own voice, train a voice profile, pick a delivery tone
  (warm/professional/energetic/calm, or custom stability/similarity/style
  sliders), and synthesize speech in that voice. Built behind a pluggable
  provider interface specifically so the whole pipeline is genuinely
  testable without external network access: the default mock provider
  validates real uploaded audio files and returns real, well-formed WAV
  output (silent, but verified as valid audio by reading it back with
  Python's own `wave` module — both calling the backend directly and
  through the dashboard's httpOnly-cookie proxy, which required teaching
  the proxy to correctly pass through multipart uploads and binary audio
  responses rather than always forcing JSON). Consent is required and
  enforced server-side before training runs. A real ElevenLabs adapter is
  included, implemented against their actual API, but **explicitly not
  verified** — see below.

**Not built yet** (each sub-README has specifics):
- **Real voice cloning output** specifically: the entire pipeline above
  is built and tested against a mock provider; the actual call to
  ElevenLabs' cloning API isn't verified, because `api.elevenlabs.io`
  isn't reachable from this environment's network allowlist. Activating
  it is a one-line settings change (`VOICE_PROVIDER=elevenlabs` + your own
  `ELEVENLABS_API_KEY`) — but test it for real before trusting it, since
  it's the one piece in this repo that wasn't run against a live service
  before being called done.
- Speech-to-text (mic-to-text voice *input* — separate from voice
  training, which is the assistant speaking back in your voice) and
  speaker verification (voice biometrics for authentication) — both
  blocked the same way: real STT/biometric providers aren't reachable
  from this sandbox's network allowlist
- Knowledge/RAG system, agent builder, automation builder
- Billing/subscriptions, CMS

## Deploying beyond localhost

`browser-extension/manifest.json`'s `host_permissions` is scoped to
`http://localhost:8000/*` only — narrow on purpose, but it means pointing
the extension at a real deployed backend requires adding that origin to
`host_permissions` (and to the backend's `CORS_ORIGINS`) before it'll work
anywhere but local development.

## A note on scope

The original spec (36 sections) describes a platform on the scale of a
small company's roadmap — voice biometrics, a marketplace, an admin CMS,
billing, a full agent builder. What's here is the architectural spine of
that system, built in vertical slices that actually work end-to-end,
rather than a wide layer of stubs. Each "not built yet" item is a genuine
next phase, not a placeholder pretending to be finished.
#   n o v a g e n t  
 
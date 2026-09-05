# Nova Backend — Personal AI Operating Assistant Platform

Cloud API layer for the assistant platform: auth, users/devices, permissions,
reminders, and the tool execution engine that the desktop agent / browser
extension / AI orchestration layer will call into.

## Stack

FastAPI (async) · PostgreSQL (SQLAlchemy 2.0 async) · Alembic · Redis (reserved
for sessions/rate-limiting/Celery) · JWT auth (access + refresh + device
tokens) · Pydantic v2.

## Project layout

```
app/
  core/       config, DB session, JWT/password security, auth dependencies
  models/     SQLAlchemy models (User, Device, UserPermission, Reminder, AuditLog)
  schemas/    Pydantic request/response models
  api/v1/     route modules (auth, reminders, tools)
  tools/      Tool Registry — base.py (BaseTool/ToolRegistry/permission+audit
              plumbing) + reminder_tools.py (first concrete tools)
  services/   reserved for cross-cutting business logic as it grows
alembic/      migrations (async-aware env.py)
```

## Why it's structured this way

- **Tool Registry (`app/tools/base.py`)** is the architectural core from the
  spec's section 6/7 — every capability the assistant can perform (reminders
  today; files, browser, OS control, agents later) is a `BaseTool` subclass
  that declares its permission scope, risk level, and whether it needs
  interactive confirmation. `BaseTool.execute()` centralizes permission
  checks, timeouts, error handling, and audit logging so individual tools
  stay thin. The AI orchestration layer (not built yet) will call
  `ToolRegistry.get(name).execute(...)` after planning — it never talks to
  the DB or models directly.
- **Permissions (`app/models/permission.py`)** are a flat enum with a static
  risk-level table, matching spec section 34. Adding a new permission scope
  is a one-line enum addition, not a migration.
- **Device tokens** are stored hashed (`Device.token_hash`), never raw —
  mirrors password handling, needed before the desktop agent/browser
  extension can authenticate.
- **Audit log** is separate from reminders/business tables and is written by
  the tool layer itself, so every tool call is logged automatically without
  each tool remembering to do it.

## Local setup

```bash
cp .env.example .env          # edit JWT_SECRET_KEY at minimum
docker compose up -d          # postgres + redis
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

alembic revision --autogenerate -m "init schema"
alembic upgrade head

uvicorn app.main:app --reload
```

API docs: `http://localhost:8000/docs`

## What's implemented now

- Register/login/refresh (`/api/v1/auth/*`), JWT access+refresh tokens
- Current-user dependency with account-status enforcement
- Device registration/list/rename/revoke (`/api/v1/devices/*`) — issues a
  device token (JWT) whose hash is stored, never the raw token; revoking a
  device is enforced on its very next request via `get_current_device`,
  independent of the token's expiry
- Reminders CRUD + snooze (`/api/v1/reminders/*`) — full vertical slice
- `POST /api/v1/tools/{tool_name}/execute` — single entry point for running
  any registered tool, from either a user or a device token
- **AI orchestration (`/api/v1/assistant/*`)** — `POST /chat` sends a
  natural-language message to Claude with every registered tool exposed as
  an Anthropic tool-use schema (`app/services/orchestrator.py`). The model
  may propose tool calls, but **every one still passes through
  `BaseTool.execute()`'s own permission and risk checks** — the model
  cannot self-approve a high-risk action. High-risk proposals come back as
  `REQUIRES_CONFIRMATION` with a `pending_id`; only `POST
  /confirm/{pending_id}`, a separate authenticated call the user must make,
  actually executes them (`PendingToolCall` model, 5-minute TTL by default).
- **Device WebSocket channel (`/api/v1/ws/device`)** — the mechanism spec
  section 3 requires ("a website cannot directly control a user's
  operating system"). A connected desktop agent gets a live socket;
  `DeviceConnectionManager.send_command()` (`app/services/connection_manager.py`)
  lets any tool push a command to that exact device and await a real
  result, correlated by request_id. `shutdown_computer`, `lock_computer`,
  and `open_application` all dispatch this way now — none of them are
  stubs. **Verified live**: a simulated device connected over a real
  WebSocket, a REST call to `/tools/lock_computer/execute` genuinely
  traveled through the connection manager to that device and back
  (3.9ms round-trip), and calling the same tool with no device connected
  correctly failed with `"device isn't currently connected"` rather than
  hanging or silently no-op'ing.
- Tool Registry with `create_reminder`, `get_schedule`, `shutdown_computer`,
  `lock_computer`, `open_application`
- `GET /api/v1/tools` — capability discovery endpoint for clients
- `GET/PUT /api/v1/permissions` — list every `PermissionScope` with its
  grant status (defaults to ungranted for scopes with no row yet) and
  toggle individual scopes. Without this, permissions could only be set by
  writing directly to the database — verified end-to-end: default
  ungranted → tool call `DENIED` → grant via the same `PUT` call the
  dashboard's toggle makes → tool call `SUCCESS`.
- **Multi-instance WebSocket dispatch** — `DeviceConnectionManager` now
  backs itself with Redis pub/sub (`app/services/connection_manager.py`).
  A device connected to instance A can still be reached by a tool call
  handled by instance B: on connect, the owning instance publishes
  `{device_id -> instance_id}` to Redis (TTL-refreshed via a heartbeat
  task); `send_command()` checks its own local connections first (fast
  path, no Redis involved) and only falls through to a Redis-forwarded
  dispatch when the device isn't connected locally. Verified with two
  genuinely separate `uvicorn` processes on different ports sharing one
  Redis instance — a REST call to instance B correctly reached a device
  connected only to instance A. Redis being unreachable at startup fails
  fast (bounded `socket_connect_timeout`/ping timeout) and falls back to
  single-instance-only mode rather than hanging — also verified directly,
  since the first version of this code had exactly that hang and it was
  caught by Redis genuinely going down mid-testing.
- **Admin API (`/api/v1/admin/*`)** — user list/suspend/reactivate/role
  change, platform-wide device list + revoke, audit log inspection,
  aggregate stats. Every route requires `get_current_admin` (403 for
  anyone not `ADMIN`/`SUPER_ADMIN`). An admin can't suspend or change
  their own role — verified directly, along with the 403 gate, a
  suspension actually invalidating an already-issued token immediately,
  and the same routes working correctly through the dashboard's httpOnly
  cookie proxy (not just direct bearer-token calls).
- **Voice training (`/api/v1/voice/*`)** — upload voice samples, train a
  voice profile from them, choose a delivery tone (warm/professional/
  energetic/calm/custom sliders), synthesize speech. Built behind a
  pluggable `BaseVoiceProvider` interface
  (`app/services/voice_providers/`) specifically so the entire pipeline
  is genuinely testable without any external service: the default `mock`
  provider validates real uploaded files and returns real, valid WAV
  audio (silent, but genuinely well-formed — verified by reading it back
  with Python's own `wave` module, both directly and through the
  dashboard's proxy). Consent is required and checked server-side before
  training runs. A real `ElevenLabsVoiceProvider` adapter is included,
  implemented against ElevenLabs' actual API shape, but **explicitly
  marked as unverified** — `api.elevenlabs.io` isn't reachable from this
  dev environment's network allowlist, so unlike everything else in this
  repo, it was not run against the real service. Set
  `VOICE_PROVIDER=elevenlabs` + `ELEVENLABS_API_KEY` to activate it; test
  it for real before trusting it.

Requires `ANTHROPIC_API_KEY` in `.env` for `/assistant/chat` to work — get
one at console.anthropic.com. Everything else works without it.

## What's deliberately not built yet (next phases per the spec)

- Computer-use/accessibility-API interaction beyond the handful of
  OSController actions implemented so far (open app/url/folder, lock,
  shutdown, restart, notify)
- **Real voice cloning output** — the training pipeline (upload, train,
  tone, synthesize, playback) is fully built and tested against a mock
  provider; the actual ElevenLabs API call itself isn't verified, since
  that service isn't reachable from this dev environment's network. Wire
  in `ELEVENLABS_API_KEY`, set `VOICE_PROVIDER=elevenlabs`, and test
  `app/services/voice_providers/elevenlabs.py` for real before relying on
  it.
- Speech-to-text / real-time voice *input* (typed text still goes into
  `/assistant/chat`; there's no mic-to-text path yet)
- Speaker *verification* (voice biometrics for authenticating who's
  speaking, spec section 12) — distinct from voice *training* (having the
  assistant speak back in your voice, which is what's built here) and a
  substantially larger undertaking (embedding models, false-accept/
  false-reject thresholds, liveness detection) not attempted this round
- Knowledge/RAG system, agent builder, automation builder
- Billing/subscriptions, CMS (user/device/audit admin tooling is now
  implemented — see above)
- Conversation history / multi-turn context in `/assistant/chat` (currently
  single-turn — each call is a fresh message to the model)

Each of these plugs into what's here rather than requiring a rebuild: new
tools register with `ToolRegistry`, new permission scopes are enum additions,
new resource types follow the same model → schema → router → (optional) tool
pattern reminders use.

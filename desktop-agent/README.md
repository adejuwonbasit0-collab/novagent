# Nova Desktop Agent

Floating assistant bubble (spec section 4) that talks to the Nova backend.
First run: sign in with your Nova account, which registers this machine as
a device; every run after that authenticates as the device, not the user
session.

## Layout

```
main.py            entrypoint — wires bubble + chat panel + onboarding
config.py           local settings (backend URL, theme, bubble size)
core/
  api_client.py      HTTP client — user-token mode (first run) / device-token
                      mode (normal operation), matches backend's get_current_actor
  device_store.py    persists device identity; token goes in the OS keyring,
                      with a graceful encrypted-file fallback if no keyring
                      backend exists on the machine (headless Linux, etc.)
  ws_client.py        persistent WebSocket connection to the backend — receives
                      dispatched tool commands (shutdown_computer, lock_computer,
                      open_application, ...), runs them via OSController, and
                      replies with the result. Reconnects with exponential
                      backoff; runs in its own thread with its own asyncio
                      loop since it doesn't share Qt's event loop.
ui/
  bubble.py           draggable always-on-top bubble, draws its own state ring
                      (idle/listening/thinking/executing) — no image assets needed
  chat_panel.py       text chat window; runs API calls off the Qt thread via
                      QThread workers (PySide6 doesn't mix with asyncio directly)
  onboarding.py       first-run login + device registration dialog
os_control/
  base.py             OSController interface (spec section 5) — open app/url/
                      folder, lock, shutdown, restart, notify
  windows.py / macos.py / linux.py   platform implementations
```

## Why it's structured this way

- **Confirmation flow lives in the UI, not baked into any tool.**
  `ChatPanel._handle_confirmation_needed` shows a real modal when the
  backend returns `REQUIRES_CONFIRMATION`, and only calls
  `/assistant/confirm/{pending_id}` if the user clicks Yes — mirrors the
  backend's own refusal to let the LLM self-approve high-risk actions.
- **Device token, not user token, for daily operation.** After onboarding,
  the agent never re-sends the user's password or even the login JWT; it
  authenticates purely as itself, so revoking the device (from the web
  dashboard) kills its access immediately without touching the account.
- **OSController is now wired to the backend** via `ws_client.py` — the
  backend pushes a command over WebSocket, the agent runs it locally and
  replies with the real result. `shutdown_computer` is no longer a stub.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Point it at a non-default backend with `BACKEND_URL` in a local `.env` file
(defaults to `http://localhost:8000`).

## Verified

Ran the agent's real `NovaAPIClient` (not a mock) against a live instance of
the backend: login → device registration → local credential persistence →
simulated app restart with a fresh client instance still authenticating
correctly via the saved device token → reminders fetch → health check →
credential cleanup. All passed. UI widgets (bubble, chat panel, onboarding
dialog) were verified to construct correctly under Qt's offscreen platform,
though full interactive rendering hasn't been checked against a real display.

Also verified the WebSocket dispatch path end-to-end against the live
backend: a simulated device connected to `/api/v1/ws/device`, and a REST
call to `/api/v1/tools/lock_computer/execute` genuinely traveled through
the backend's connection manager, over that WebSocket, to the "device,"
and its reply came back as the tool's actual result (3.9ms round-trip) —
not a stub. Also confirmed the correct failure path when no device is
connected.

## Not built yet

- System tray icon / start-with-OS registration
- Voice input (mic capture + STT) feeding into `/assistant/chat`
- Notification-on-reminder-due (needs local scheduling, spec section 17)
- `ws_client.py` hasn't been run against a real OS yet (this sandbox has no
  desktop session) — the dispatch table and message protocol are tested,
  but actual `subprocess`/`os.startfile` calls in `os_control/*.py` should
  be sanity-checked on each target OS before shipping

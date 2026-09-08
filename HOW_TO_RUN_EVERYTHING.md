# Running all four pieces together (local dev, Windows)

Four separate things, four separate terminal windows, all open at once.
Order matters — later ones depend on earlier ones being up first.

## 1. Backend (start this first, always)

```powershell
cd nova-platform\backend
docker compose up -d              # starts Postgres + Redis (needs Docker Desktop open)
python -m venv .venv               # first time only
.venv\Scripts\activate
pip install -r requirements.txt    # first time only
alembic upgrade head               # first time only, and after any migration is added
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Leave this running. Confirm it's actually up before touching anything else:
**http://127.0.0.1:8000/health** in a browser should return JSON, not an
error page. Nothing downstream works until this does.

If you'd rather use the one-shot script instead of the manual steps above
(after the first-time setup), `start-nova.ps1` in the repo root starts
backend + dashboard + desktop-agent together — but only after you've done
steps 2-6 above at least once each, and only after applying the credential
fix from earlier in this conversation.

## 2. Dashboard (the website — registration, devices, voice, admin, etc.)

```powershell
cd nova-platform\dashboard
npm install        # first time only
npm run dev
```

Opens at **http://localhost:3000**. This is what spec section 3's "user
visits Nova website" flow refers to — register/login, connect a device,
train voice, manage permissions, admin panel at `/admin`.

## 3. Desktop agent (the actual assistant — wake word, bubble, local commands)

```powershell
cd nova-platform\desktop-agent
python -m venv venv        # first time only
venv\Scripts\activate
pip install -r requirements.txt   # first time only
python main.py
```

First run opens the sign-in dialog (now fixed to actually come to the
front) — log in with the account you registered on the dashboard, or it'll
walk you through pairing a new device. After that, the floating bubble
appears and you talk to it directly; you shouldn't need to come back to
this terminal.

## 4. Browser extension (optional — page context, "summarize this page")

Not run from a terminal — loaded straight into Chrome:

1. Chrome → `chrome://extensions`
2. Toggle **Developer mode** on (top right)
3. **Load unpacked** → select the `browser-extension` folder
4. Click the Nova icon in the toolbar, log in with the same account

It talks to the backend at `http://localhost:8000` by default
(`browser-extension/config.js`) — matches the backend port above, no
extra setup needed for local dev.

## Everyday use, once all four have run at least once

You don't need the dashboard or extension open every day — spec's own
intent (section 3, "the user should not need to return to the website for
normal Nova use"). Realistically, for local dev:

- **Always**: backend (terminal 1) — nothing works without it.
- **Always**: desktop agent (terminal 3) — this is what you actually talk to.
- **As needed**: dashboard (terminal 2) — only when changing account/device/
  voice/permission settings.
- **As needed**: browser extension — only if you want page-context features.

## Quick "is it actually working" checklist

1. `http://127.0.0.1:8000/health` loads → backend is up.
2. `http://localhost:3000` loads and you can log in → dashboard is up.
3. Desktop agent terminal shows no repeating `WebSocket connection
   failed` lines → it's connected to the backend.
4. Say the wake word → bubble shows a listening/thinking state, not
   silence.

If any of these fails, that's the one to fix before testing anything
further downstream of it.

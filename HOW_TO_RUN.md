# Running Nova (as this zip actually is)

## 1. Backend
```
cd backend
cp .env.example .env
# fix the DB URL to match docker-compose (see "known bug" below) before continuing
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt      # macOS/Linux: .venv/bin/pip
docker compose up -d                                # starts postgres + redis
.venv\Scripts\alembic upgrade head                  # macOS/Linux: .venv/bin/alembic
.venv\Scripts\uvicorn app.main:app --reload          # macOS/Linux: .venv/bin/uvicorn
```
Set `ANTHROPIC_API_KEY` in `.env` if you want `/assistant/chat` to actually
call an LLM — without it, chat requests will fail (voice enrollment/backend
auth/devices all work fine without it).

API docs: http://localhost:8000/docs

## 2. Dashboard (website)
```
cd dashboard
npm install
npm run dev
```
http://localhost:3000

## 3. Desktop agent
```
cd desktop-agent
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```
On first run it opens a login/pairing dialog — log in with the account you
registered on the dashboard, and it registers this machine as a device.

## Known bug you'll hit immediately: Postgres credentials don't match

`docker-compose.yml` creates the database with user `nova` / password
`nova_password` (matches `.env.example`'s `DATABASE_URL`), but
`start-nova.ps1` hardcodes `postgres` / `postgres123` when it launches the
backend — that combination doesn't exist, so the backend will fail to
connect to Postgres if you use `start-nova.ps1` as-is.

**Fix, either:**
- Edit `start-nova.ps1`'s `DATABASE_URL` to
  `postgresql+asyncpg://nova:nova_password@localhost:5432/nova_db`, or
- Skip `start-nova.ps1` and just run each piece manually per the steps
  above, using whatever's actually in your `backend/.env`.

I've fixed this in the batch below along with the other unresolved issues.

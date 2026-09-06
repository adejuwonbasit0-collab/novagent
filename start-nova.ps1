# Convention: each Python subproject (backend/, desktop-agent/) owns its OWN
# .venv/ inside its own folder — never a shared venv/ at the repo root. Create
# them with, e.g.:
#   cd backend        && python -m venv .venv && .\.venv\Scripts\pip install -r requirements.txt
#   cd desktop-agent   && python -m venv .venv && .\.venv\Scripts\pip install -r requirements.txt
# Both are already covered by .gitignore — never commit a .venv/ or venv/ folder.
# DATABASE_URL below must match docker-compose.yml's POSTGRES_USER/PASSWORD
# (currently nova/nova_password) — they drifted out of sync once already.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$dashboard = Join-Path $root "dashboard"
$agent = Join-Path $root "desktop-agent"

$apiUp = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if (-not $apiUp) {
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$backend'; `$env:DATABASE_URL='postgresql+asyncpg://nova:nova_password@localhost:5432/nova_db'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
    )
} else {
    Write-Host "Backend already running on port 8000; reusing it."
}

$webUp = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
if (-not $webUp) {
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$dashboard'; `$env:BACKEND_URL='http://localhost:8000'; npm run dev"
    )
} else {
    Write-Host "Dashboard already running on port 3000; reusing it."
}

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$agent'; .\.venv\Scripts\python.exe main.py"
)

Write-Host "Nova started. Website: http://localhost:3000"
Write-Host "API docs: http://localhost:8000/docs"

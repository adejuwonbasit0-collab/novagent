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
        "Set-Location '$backend'; `$env:DATABASE_URL='postgresql+asyncpg://postgres:postgres123@localhost:5432/nova_db'; ..\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
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

param (
    [switch]$NoAgent,
    [switch]$NoDashboard,
    [string]$Port = "8000"
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$dashboard = Join-Path $root "dashboard"
$agent = Join-Path $root "desktop-agent"

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "    NOVA ASSISTANT PLATFORM INITIALIZATION      " -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan

# 1. Check Python Venv in backend
$backendPy = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $backendPy)) {
    Write-Host "[!] Backend virtual environment not found at $backendPy" -ForegroundColor Yellow
    Write-Host "[*] Creating backend .venv..." -ForegroundColor Gray
    python -m venv (Join-Path $backend ".venv")
    & (Join-Path $backend ".venv\Scripts\pip.exe") install --prefer-binary -r (Join-Path $backend "requirements.txt")
}

# 2. Set DATABASE_URL to SQLite (overrides any system env)
$env:DATABASE_URL = "sqlite+aiosqlite:///./nova.db"

# 3. Install aiosqlite if missing
Write-Host "[*] Ensuring aiosqlite is installed..." -ForegroundColor Gray
& (Join-Path $backend ".venv\Scripts\pip.exe") install aiosqlite pydantic-settings -q

# 4. Run Database Migrations (SQLite)
Write-Host "[*] Applying database migrations..." -ForegroundColor Gray
Push-Location $backend
try {
    & $backendPy -m alembic upgrade head
    Write-Host "[+] Database migrations up to date." -ForegroundColor Green
} catch {
    Write-Host "[!] Migration warning: $_" -ForegroundColor Yellow
} finally {
    Pop-Location
}

# 5. Start Backend Server
$apiUp = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $apiUp) {
    Write-Host "[*] Launching Nova Backend API on http://127.0.0.1:$Port..." -ForegroundColor Green
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$backend'; `$env:DATABASE_URL='sqlite+aiosqlite:///./nova.db'; & .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port $Port --reload"
    )
} else {
    Write-Host "[+] Backend API already running on port $Port." -ForegroundColor Green
}

# 6. Start Next.js Dashboard
if (-not $NoDashboard) {
    $webUp = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
    if (-not $webUp) {
        Write-Host "[*] Launching Nova Web Dashboard on http://localhost:3000..." -ForegroundColor Green
        Start-Process powershell -ArgumentList @(
            "-NoExit",
            "-Command",
            "Set-Location '$dashboard'; `$env:NODE_OPTIONS='--max-old-space-size=8192'; `$env:BACKEND_URL='http://localhost:8000'; npm run dev"
        )
    } else {
        Write-Host "[+] Dashboard already running on port 3000." -ForegroundColor Green
    }
}

# 7. Start Desktop Agent
if (-not $NoAgent) {
    $agentPy = Join-Path $agent ".venv\Scripts\python.exe"
    if (Test-Path $agentPy) {
        Write-Host "[*] Launching Nova Desktop Agent..." -ForegroundColor Green
        Start-Process powershell -ArgumentList @(
            "-NoExit",
            "-Command",
            "Set-Location '$agent'; & .\.venv\Scripts\python.exe main.py"
        )
    } else {
        Write-Host "[!] Desktop Agent .venv not ready yet; run desktop-agent manually once pip completes." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "  Nova Platform is Online:" -ForegroundColor Cyan
Write-Host "  - Web Dashboard:  http://localhost:3000" -ForegroundColor White
Write-Host "  - Backend API:    http://127.0.0.1:8000" -ForegroundColor White
Write-Host "  - API Swagger:    http://127.0.0.1:8000/docs" -ForegroundColor White
Write-Host "=================================================" -ForegroundColor Cyan
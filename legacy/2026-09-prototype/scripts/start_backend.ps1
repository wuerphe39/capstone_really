$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "가상환경이 없습니다. 먼저 scripts\setup_backend.ps1을 실행하세요."
}
if (-not $env:PETMIND_SIMULATE_ACTIONS) {
    $env:PETMIND_SIMULATE_ACTIONS = "true"
}

Push-Location (Join-Path $RepoRoot "petmind\backend")
try {
    & $Python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
} finally {
    Pop-Location
}

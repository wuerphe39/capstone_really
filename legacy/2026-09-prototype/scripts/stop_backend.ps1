$ErrorActionPreference = "Stop"
$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1

if (-not $listener) {
    Write-Host "포트 8000에서 실행 중인 백엔드가 없습니다."
    exit 0
}

$process = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction Stop
$commandLine = [string]$process.CommandLine

# Conda-backed virtual environments can report the base interpreter path rather
# than .venv\Scripts\python.exe, so validate the command instead of its path.
if ($commandLine -notmatch "uvicorn\s+main:app" -or $commandLine -notmatch "--port\s+8000") {
    throw "포트 8000은 PetMind가 아닌 다른 프로세스가 사용 중이므로 종료하지 않았습니다. PID=$($process.ProcessId)"
}

Stop-Process -Id $process.ProcessId
Write-Host "PetMind 백엔드를 종료했습니다. PID=$($process.ProcessId)"

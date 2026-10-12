$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPath = Join-Path $RepoRoot ".venv"
$StudyPython = Join-Path $env:USERPROFILE "miniconda3\envs\study\python.exe"
$CondaPython = Join-Path $env:USERPROFILE "miniconda3\python.exe"

if (Test-Path -LiteralPath $StudyPython) {
    & $StudyPython -m venv $VenvPath
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -m venv $VenvPath
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -m venv $VenvPath
} elseif (Test-Path -LiteralPath $CondaPython) {
    & $CondaPython -m venv $VenvPath
} else {
    throw "Python 3 또는 Miniconda를 찾을 수 없습니다. Python 설치 후 다시 실행하세요."
}

$Python = Join-Path $VenvPath "Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $RepoRoot "petmind\requirements-dev.txt")
Write-Host "백엔드 환경 준비 완료: $VenvPath"

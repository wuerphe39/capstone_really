$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 가상환경 생성 실패' }
}
& .\.venv\Scripts\python.exe -m pip install -r requirements-core.txt
if ($LASTEXITCODE -ne 0) { throw '의존성 설치 실패' }
& .\.venv\Scripts\python.exe -m pytest tests petmind\backend\tests -q -p no:cacheprovider
if ($LASTEXITCODE -ne 0) { throw '테스트 실패' }

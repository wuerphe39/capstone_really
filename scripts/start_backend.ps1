$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
& .\.venv\Scripts\python.exe -m uvicorn petmind.backend.main:app --host 127.0.0.1 --port 8010

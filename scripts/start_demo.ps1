<#
.SYNOPSIS
  Start the whole PetMind demo on one Windows laptop (YAMNet service, backend, Flutter web).

.DESCRIPTION
  1. Builds the Flutter web app from an ASCII-only path (the build fails when the project path has Korean characters).
  2. Starts the YAMNet service (8030), the backend (8010, YAMNet detector, rule-based explanations, no external calls)
     and a static web server (8021). Data goes to artifacts/demo (ignored by git).
  3. -Capture also starts the collector agent: an outing started in the web UI ("auto observation") then records the
     laptop webcam and microphone (devices are detected automatically; see scripts/make_capture_input.py).
  4. -Seed fills the demo pet with public ESC-50 recordings (about 40 seconds, real time).

  .\scripts\start_demo.ps1 -Capture     also collect from the webcam and microphone
  .\scripts\start_demo.ps1 -Seed        first run: build, start, fill demo data, open the browser
  .\scripts\start_demo.ps1              start again (keeps data)
  .\scripts\start_demo.ps1 -Rebuild     rebuild the web app after changing petmind_app/lib
  .\scripts\start_demo.ps1 -Stop        stop everything

  Requirements: .venv (requirements-core.txt + soundfile scipy opencv-python), Python 3.12 with TensorFlow
  (requirements-yamnet-experiment.txt) as "py -3.12", Flutter 3.32.x (PATH, $env:FLUTTER_HOME or ~/flutter).
#>
[CmdletBinding()]
param(
    [switch]$Seed,
    [switch]$Rebuild,
    [switch]$Stop,
    [switch]$NoBrowser,
    [switch]$Capture,
    [string]$PetId = 'demo-dog',
    [string]$BuildRoot = $(if ($env:PETMIND_BUILD_ROOT) { $env:PETMIND_BUILD_ROOT } else { 'C:\petmind_build' })
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Demo = Join-Path $Root 'artifacts\demo'
$Ports = @(8030, 8010, 8021, 18081)
$PidFile = Join-Path $Demo 'pids.json'

function Stop-Demo {
    # The collector agent, its capture worker and the capture FFmpeg open no port of their own: find them by command line.
    # Without this a restart leaves old agents running (they would claim the next outing with outdated code).
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and ($_.CommandLine -match 'scripts\.pi_outing_agent|scripts\.monitor_audio_events' -or
            ($_.Name -like 'ffmpeg*' -and $_.CommandLine -match 'petmind-capture-')) } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    foreach ($port in $Ports) {
        Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    }
    Remove-Item $PidFile -ErrorAction SilentlyContinue
}

function Wait-Url([string]$Url, [string]$Name, [int]$Seconds = 240) {
    $until = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $until) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -eq 200) { Write-Host "  ready: $Name"; return }
        } catch { Start-Sleep -Seconds 2 }
    }
    throw "$Name did not become ready ($Url). See logs in $Demo"
}

function Find-Flutter {
    $cmd = Get-Command flutter -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($dir in @($env:FLUTTER_HOME, (Join-Path $env:USERPROFILE 'flutter'))) {
        if ($dir) {
            $bat = Join-Path $dir 'bin\flutter.bat'
            if (Test-Path $bat) { return $bat }
        }
    }
    throw 'Flutter not found. Install Flutter 3.32.x or set FLUTTER_HOME.'
}

if ($Stop) { Stop-Demo; Write-Host 'Stopped.'; return }

$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw ".venv not found. Create it: py -3.12 -m venv .venv ; .\.venv\Scripts\python.exe -m pip install -r requirements-core.txt soundfile scipy opencv-python" }
New-Item -ItemType Directory -Force $Demo | Out-Null
Stop-Demo   # clean start: free the ports first

# ---- 1. Flutter web build from an ASCII path ----------------------------------------------------
$WebDir = Join-Path $BuildRoot 'web'
$AppCopy = Join-Path $BuildRoot 'petmind_app'
$needBuild = $Rebuild -or -not (Test-Path (Join-Path $WebDir 'index.html'))
if (-not $needBuild) {
    $newest = (Get-ChildItem (Join-Path $Root 'petmind_app\lib') -Recurse -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime
    $needBuild = $newest -gt (Get-Item (Join-Path $WebDir 'index.html')).LastWriteTime
}
if ($needBuild) {
    Write-Host "Building Flutter web in $BuildRoot (first build takes a few minutes)..."
    $flutter = Find-Flutter
    New-Item -ItemType Directory -Force $AppCopy | Out-Null
    robocopy (Join-Path $Root 'petmind_app') $AppCopy /MIR /XD build .dart_tool /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }
    Push-Location $AppCopy
    try {
        & $flutter pub get
        if ($LASTEXITCODE -ne 0) { throw 'flutter pub get failed' }
        # --pwa-strategy=none: no service-worker cache, so a rebuilt page is never mixed with an old cached one (gray boxes)
        & $flutter build web --release --no-web-resources-cdn --pwa-strategy=none --output=$WebDir --dart-define=PETMIND_API_BASE=http://localhost:8010
        if ($LASTEXITCODE -ne 0) { throw 'flutter build web failed' }
    } finally { Pop-Location }
} else {
    Write-Host "Web build is up to date ($WebDir)."
}

# ---- 2. Services ---------------------------------------------------------------------------------
function Start-Hidden([string]$Name, [string]$File, [string[]]$ArgList) {
    $p = Start-Process -FilePath $File -ArgumentList $ArgList -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $Demo "$Name.out.log") -RedirectStandardError (Join-Path $Demo "$Name.err.log")
    Write-Host "  started: $Name (pid $($p.Id))"
    return $p.Id
}

$env:TF_CPP_MIN_LOG_LEVEL = '3'
$env:PYTHONIOENCODING = 'utf-8'
$ids = @{}
Write-Host 'Starting services...'
$ids.yamnet = Start-Hidden 'yamnet' 'py' @('-3.12', '-m', 'petmind.yamnet_service.app', '--port', '8030')

$env:PETMIND_DATABASE_URL = 'sqlite:///artifacts/demo/petmind_demo.db'
$env:PETMIND_AUDIO_STORAGE_DIR = 'artifacts/demo/user_audio'
$env:PETMIND_AUDIO_DETECTOR = 'yamnet'
$env:PETMIND_YAMNET_URL = 'http://127.0.0.1:8030/analyze'
if ($Capture) {
    Write-Host 'Detecting webcam and microphone...'
    & $Python -m scripts.make_capture_input
    if ($LASTEXITCODE -ne 0) { throw 'make_capture_input failed (is a camera/microphone connected and allowed in Windows privacy settings?)' }
    $CaptureConfig = Get-Content (Join-Path $Demo 'capture-config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $env:PETMIND_CAMERA_SNAPSHOT_URL = 'http://127.0.0.1:18081/snapshot.jpg'
}
$env:PETMIND_LLM_PROVIDER = 'rule'
$env:PETMIND_SEMANTIC_SEARCH = 'off'
$ids.backend = Start-Hidden 'backend' $Python @('-m', 'uvicorn', 'petmind.backend.main:app', '--host', '127.0.0.1', '--port', '8010')
$ids.web = Start-Hidden 'web' 'py' @('-3.12', '-m', 'http.server', '8021', '--bind', '127.0.0.1', '--directory', $WebDir)
$ids | ConvertTo-Json | Set-Content $PidFile

Wait-Url 'http://127.0.0.1:8021/' 'web (8021)'
Wait-Url 'http://127.0.0.1:8010/health' 'backend (8010)'
Wait-Url 'http://127.0.0.1:8030/' 'YAMNet service (8030)'

if ($Capture) {
    # The agent claims capture jobs created from the web UI and runs the capture program (webcam + microphone).
    $ids.agent = Start-Hidden 'agent' $Python @('-m', 'scripts.pi_outing_agent', '--base', 'http://127.0.0.1:8010', '--pet-id', $PetId,
        '--input-args-file', $CaptureConfig.input_args_file, '--ffmpeg', ('"' + $CaptureConfig.ffmpeg + '"'),
        '--video-map', '0:v:0', '--audio-map', '1:a:0')
    $ids | ConvertTo-Json | Set-Content $PidFile
    Write-Host "  collector agent: pet '$PetId' (start an outing with 'auto observation' in the web UI)"
}

# ---- 3. Demo data ---------------------------------------------------------------------------------
if ($Seed) {
    if (-not (Test-Path (Join-Path $Root 'artifacts\datasets\esc50_demo\audio'))) {
        Write-Host 'Downloading four public ESC-50 clips...'
        & $Python -m scripts.prepare_demo_audio
        if ($LASTEXITCODE -ne 0) { throw 'prepare_demo_audio failed' }
    }
    Write-Host 'Filling demo records (real time, about 40 seconds)...'
    & $Python -m scripts.seed_demo_records
    if ($LASTEXITCODE -ne 0) { throw 'seed_demo_records failed' }
}

Write-Host ''
Write-Host 'PetMind demo is running:  http://localhost:8021/   (stop with: .\scripts\start_demo.ps1 -Stop)'
if (-not $NoBrowser) { Start-Process 'http://localhost:8021/' }

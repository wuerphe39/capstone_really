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
  .\scripts\start_demo.ps1 -Gemini      explanations by Gemini (key in .env); only derived facts are sent, never audio
  .\scripts\start_demo.ps1 -Lan         also open the app to phones and PCs on the same network (needs an access key)
  .\scripts\start_demo.ps1 -Stop        stop everything

  Requirements: .venv (requirements-runtime.txt), Python 3.12 with TensorFlow (requirements-yamnet-experiment.txt)
  as "py -3.12" or the interpreter in $env:PETMIND_YAMNET_PYTHON, Flutter 3.32.x (PATH, $env:FLUTTER_HOME or ~/flutter).
  They are checked first and every missing piece is reported at once.
  Windows blocks .ps1 files by default: run  powershell -ExecutionPolicy Bypass -File .\scripts\start_demo.ps1 ...
  or use scripts\start_demo.cmd, which does that.
#>
[CmdletBinding()]
param(
    [switch]$Seed,
    [switch]$Rebuild,
    [switch]$Stop,
    [switch]$NoBrowser,
    [switch]$Capture,
    [switch]$Gemini,
    [switch]$Lan,
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
        Where-Object { $_.CommandLine -and ($_.CommandLine -match 'scripts\.capture_agent|scripts\.monitor_audio_events' -or
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
# The YAMNet service needs TensorFlow, which is installed outside .venv. Default: "py -3.12". Another interpreter
# (for example a venv) can be chosen with the environment variable PETMIND_YAMNET_PYTHON.
$YamnetExe = if ($env:PETMIND_YAMNET_PYTHON) { $env:PETMIND_YAMNET_PYTHON } else { 'py' }
$YamnetPre = if ($env:PETMIND_YAMNET_PYTHON) { @() } else { @('-3.12') }

function Test-PythonModules([string]$Exe, [string[]]$Pre, [string[]]$Modules) {
    # Returns the missing module names, or $null when the interpreter itself cannot run.
    $list = ($Modules | ForEach-Object { "'$_'" }) -join ','
    $code = "import importlib.util as u; print(' '.join(m for m in ($list) if u.find_spec(m) is None))"
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try { $out = & $Exe @Pre -c $code 2>$null; $ok = ($LASTEXITCODE -eq 0) } catch { $ok = $false } finally { $ErrorActionPreference = $old }
    if (-not $ok) { return $null }
    return ("$out").Trim()
}

function Test-GeminiKey {
    $envFile = Join-Path $Root '.env'
    if ($env:GEMINI_API_KEY) { return $true }
    if (-not (Test-Path $envFile)) { return $false }
    return [bool](Select-String -Path $envFile -Pattern '^\s*GEMINI_API_KEY\s*=\s*\S+' -Quiet)
}

function Test-Prerequisites {
    # Check everything up front and report all problems at once, instead of failing minutes into the start-up.
    $problems = @()
    if (-not (Test-Path $Python)) {
        $problems += ".venv not found.`n    Fix: py -3.12 -m venv .venv ; .\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt"
    } else {
        $missing = Test-PythonModules $Python @() @('fastapi', 'uvicorn', 'sqlalchemy', 'requests', 'soundfile', 'scipy', 'cv2', 'imageio_ffmpeg', 'mcp')
        if ($null -eq $missing) { $problems += ".venv Python does not run.`n    Fix: delete .venv and create it again with Python 3.12 (see README)." }
        elseif ($missing) { $problems += "Missing packages in .venv: $missing`n    Fix: .\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt" }
    }
    $missing = Test-PythonModules $YamnetExe $YamnetPre @('tensorflow', 'tensorflow_hub', 'soundfile', 'scipy')
    if ($null -eq $missing) {
        $problems += "Python for the YAMNet service not found ($YamnetExe $($YamnetPre -join ' ')).`n    Fix: install Python 3.12 (winget install Python.Python.3.12), or set PETMIND_YAMNET_PYTHON to a Python that has TensorFlow."
    } elseif ($missing) {
        $problems += "Missing packages for the YAMNet service: $missing`n    Fix: $YamnetExe $($YamnetPre -join ' ') -m pip install -r requirements-yamnet-experiment.txt"
    }
    if ($Rebuild -or -not (Test-Path (Join-Path $BuildRoot 'web\index.html'))) {
        try { $null = Find-Flutter } catch { $problems += "Flutter is needed to build the web app: $($_.Exception.Message)`n    Fix: install Flutter 3.32.x and put it on PATH (or set FLUTTER_HOME)." }
    }
    if ($Gemini -and -not (Test-GeminiKey)) {
        $problems += "-Gemini needs an API key, but GEMINI_API_KEY is not set.`n    Fix: copy .env.example to .env and put your key after GEMINI_API_KEY= (never paste it into chat or commit it)."
    }
    if ($problems.Count -gt 0) {
        Write-Host ''
        Write-Host 'Cannot start the demo yet:' -ForegroundColor Red
        $i = 1; foreach ($p in $problems) { Write-Host "  $i. $p"; $i++ }
        Write-Host ''
        Write-Host "$($problems.Count) prerequisite(s) missing. Nothing was started or stopped." -ForegroundColor Red
        exit 1
    }
}

Test-Prerequisites
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
        & $flutter build web --release --no-web-resources-cdn --pwa-strategy=none --output=$WebDir --dart-define=PETMIND_API_BASE=auto
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
$ids.yamnet = Start-Hidden 'yamnet' $YamnetExe (@($YamnetPre) + @('-m', 'petmind.yamnet_service.app', '--port', '8030'))

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
# Explanations use the rule-based provider (no external calls) unless -Gemini is given; the key is read from .env only.
$env:PETMIND_LLM_PROVIDER = if ($Gemini) { 'gemini' } else { 'rule' }
$env:PETMIND_SEMANTIC_SEARCH = 'off'
# -Lan: listen on all interfaces. The backend still refuses everything except this PC and private-network clients that
# hold the access key (petmind/backend/access.py). The key is created once and kept in artifacts/demo (git-ignored).
$BindHost = '127.0.0.1'
if ($Lan) {
    $KeyFile = Join-Path $Demo 'lan-key.txt'
    if (-not (Test-Path $KeyFile)) {
        $bytes = New-Object byte[] 18
        [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        ([Convert]::ToBase64String($bytes)).Replace('+', '-').Replace('/', '_') | Set-Content -Encoding ascii $KeyFile
    }
    $LanKey = (Get-Content $KeyFile -Raw).Trim()
    $env:PETMIND_LAN_TOKEN = $LanKey
    $env:PETMIND_WEB_DIR = $WebDir
    $BindHost = '0.0.0.0'
} else {
    Remove-Item Env:PETMIND_LAN_TOKEN -ErrorAction SilentlyContinue
    Remove-Item Env:PETMIND_WEB_DIR -ErrorAction SilentlyContinue
}
$ids.backend = Start-Hidden 'backend' $Python @('-m', 'uvicorn', 'petmind.backend.main:app', '--host', $BindHost, '--port', '8010')
$ids.web = Start-Hidden 'web' $Python @('-m', 'http.server', '8021', '--bind', '127.0.0.1', '--directory', $WebDir)
$ids | ConvertTo-Json | Set-Content $PidFile

Wait-Url 'http://127.0.0.1:8021/' 'web (8021)'
Wait-Url 'http://127.0.0.1:8010/health' 'backend (8010)'
Wait-Url 'http://127.0.0.1:8030/' 'YAMNet service (8030)'

if ($Capture) {
    # The agent claims capture jobs created from the web UI and runs the capture program (webcam + microphone).
    $ids.agent = Start-Hidden 'agent' $Python @('-m', 'scripts.capture_agent', '--base', 'http://127.0.0.1:8010', '--pet-id', $PetId,
        '--input-args-file', $CaptureConfig.input_args_file, '--ffmpeg', ('"' + $CaptureConfig.ffmpeg + '"'),
        '--video-map', '0:v:0', '--audio-map', '1:a:0', '--redetect')
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
if ($Lan) {
    # Private IPv4 addresses of real adapters (not VMware/Hyper-V/VirtualBox virtual ones).
    $vpn = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -match '^100[.]' -and $_.InterfaceAlias -match 'Tailscale' } |
        Select-Object -ExpandProperty IPAddress)
    $local = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -match '^(10[.]|192[.]168[.]|172[.](1[6-9]|2[0-9]|3[01])[.])' -and
                       $_.InterfaceAlias -notmatch 'VMware|vEthernet|VirtualBox|Loopback|Bluetooth|WSL' } |
        Select-Object -ExpandProperty IPAddress)
    $addresses = @($vpn) + @($local)
    $rule = 'PetMind demo (private network, TCP 8010)'
    if (-not (Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue)) {
        try {
            New-NetFirewallRule -DisplayName $rule -Direction Inbound -Protocol TCP -LocalPort 8010 -Action Allow `
                -Profile Private -RemoteAddress LocalSubnet -ErrorAction Stop | Out-Null
            Write-Host '  firewall: allowed TCP 8010 from the local subnet on private networks'
        } catch {
            Write-Host '  firewall: no rule yet (needs an administrator). Allow the Windows prompt, or run once in an admin PowerShell:' -ForegroundColor Yellow
            Write-Host "    New-NetFirewallRule -DisplayName '$rule' -Direction Inbound -Protocol TCP -LocalPort 8010 -Action Allow -Profile Private -RemoteAddress LocalSubnet"
        }
    }
    if ($vpn) {
        $vpnRule = 'PetMind demo (Tailscale VPN, TCP 8010)'
        if (-not (Get-NetFirewallRule -DisplayName $vpnRule -ErrorAction SilentlyContinue)) {
            try {
                New-NetFirewallRule -DisplayName $vpnRule -Direction Inbound -Protocol TCP -LocalPort 8010 -Action Allow `
                    -InterfaceAlias 'Tailscale' -RemoteAddress 100.64.0.0/10 -Profile Any -ErrorAction Stop | Out-Null
                Write-Host '  firewall: allowed TCP 8010 from Tailscale addresses on the Tailscale interface only'
            } catch {
                Write-Host '  firewall: no Tailscale rule yet (needs an administrator). Run once in an admin PowerShell:' -ForegroundColor Yellow
                Write-Host "    New-NetFirewallRule -DisplayName '$vpnRule' -Direction Inbound -Protocol TCP -LocalPort 8010 -Action Allow -InterfaceAlias 'Tailscale' -RemoteAddress 100.64.0.0/10 -Profile Any"
            }
        }
    } else {
        Write-Host '  Tailscale is not running on this PC: addresses below only work on the same network. For access away from home install Tailscale (see README).' -ForegroundColor Yellow
    }
    Write-Host ''
    Write-Host 'Open on a phone or another PC (the key is remembered after the first visit). The Tailscale address works at home AND away:' -ForegroundColor Green
    if (-not $addresses) { Write-Host '  no private network address found - connect to Wi-Fi or a hotspot first' -ForegroundColor Yellow }
    foreach ($a in $addresses) {
        $kind = if ($vpn -contains $a) { 'Tailscale VPN - works anywhere' } else { 'same network only' }
        Write-Host "  http://${a}:8010/?key=$LanKey   ($kind)"
    }
    if ($addresses) {
        # A QR code for the first address (the VPN address when there is one): scanning it avoids typing the key.
        $first = @($addresses)[0]
        # A new file name every run: an image viewer that still has the previous QR open would block overwriting it,
        # and a stale QR (old address) must never be what gets shown.
        Get-ChildItem $Demo -Filter 'lan-qr*.png' -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
        $qr = Join-Path $Demo ('lan-qr-' + (Get-Date -Format 'HHmmss') + '.png')
        # The QR code is a convenience: whatever goes wrong here (viewer holding the file, console encoding) must not stop the demo.
        $qrOk = $false
        $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        try { & $Python -m scripts.make_lan_qr "http://${first}:8010/?key=$LanKey" $qr 2>$null | Out-Null; $qrOk = ($LASTEXITCODE -eq 0) } catch { $qrOk = $false } finally { $ErrorActionPreference = $old }
        if (-not $qrOk) { Write-Host '  (no QR code this time - type the address above into the phone)' -ForegroundColor Yellow }
        if ($qrOk) {
            Write-Host "  QR code for the phone camera: $qr"
            if (-not $NoBrowser) { Start-Process $qr }
        }
    }
    Write-Host '  Anyone with this address can see the recordings. Do not share it, and do not use it on a public network.'
}
if (-not $NoBrowser) { Start-Process 'http://localhost:8021/' }

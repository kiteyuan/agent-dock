# AgentDock bootstrap — default: launch desk pet only (pet owns Runtime).
# Agents / voices are prepared in Console; pet is a host feature (not a remote client).
#
#   .\scripts\start.ps1
#   .\scripts\start.ps1 -NoPet       # Runtime only (no desk pet; for API/dev)
#   .\scripts\start.ps1 -Admin       # open Console as a second desk-pet window
#   .\scripts\stop.ps1
#
# GPU: copy config.cuda.example.yaml → config.local.yaml
# Optional engines: docker compose --profile engines
# See docs/DEPLOY.md

param(
    [switch]$NoPet,
    [switch]$Admin,
    [int]$ReadyTimeoutSec = 300,
    [int]$PetPort = 8090
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

function Test-PortListen([int]$Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Wait-PortListen([int]$Port, [int]$TimeoutSec, [string]$Label) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortListen $Port) {
            Write-Host "  ready: $Label (:$Port)"
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    Write-Host "  timeout: $Label (:$Port) after ${TimeoutSec}s"
    return $false
}

function Start-Background([string]$Title, [string]$WorkDir, [string]$Command, [hashtable]$ExtraEnv = @{}, [string]$LogFile) {
    # No visible PowerShell window — logs go under data/logs (same idea as start.sh nohup).
    $logDir = Join-Path $Root "data\logs"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $logPath = Join-Path $logDir $LogFile
    $stamp = Get-Date -Format "o"
    try {
        Add-Content -LiteralPath $logPath -Value "`n==== $stamp $Title ====`n" -Encoding utf8
    } catch {
        # Log file locked by a previous host — keep going.
    }

    $envLines = @(
        "Set-Location -LiteralPath '$WorkDir'"
        "`$env:PYTHONUNBUFFERED = '1'"
    )
    foreach ($key in $ExtraEnv.Keys) {
        $val = [string]$ExtraEnv[$key]
        $envLines += "`$env:$key = '$val'"
    }
    # Tee so the child stays attached to this hidden host and writes a durable log.
    $envLines += "& { $Command } *>> '$logPath'"
    $ps = $envLines -join "; "
    Start-Process -FilePath "powershell.exe" -WorkingDirectory $WorkDir -WindowStyle Hidden -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $ps
    ) | Out-Null
    Write-Host "  started: $Title (background → data/logs/$LogFile)"
}

Write-Host "AgentDock bootstrap (repo: $Root)"

$PetUrl = "http://127.0.0.1:${PetPort}/"
$AdminApiUrl = "http://127.0.0.1:8766/api/"
$ConsoleUrl = "http://127.0.0.1:8767/"
$DesktopDir = Join-Path $Root "desktop"
$PetHint = "cd desktop && npm run dev"

function Start-TauriPet {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) { return $false }
    if (-not (Test-Path (Join-Path $DesktopDir "package.json"))) { return $false }
    if (-not (Test-Path (Join-Path $DesktopDir "src-tauri"))) { return $false }
    if (-not (Test-Path (Join-Path $DesktopDir "node_modules\@tauri-apps\cli"))) {
        Write-Host "  Tauri pet: run once → cd desktop; npm install"
        return $false
    }
    $extra = @{}
    if ($Admin) { $extra["AGENTDOCK_OPEN_ADMIN"] = "1" }
    # Pet spawns python -m runtime if :8765 is free (see desktop/src-tauri/src/runtime_child.rs).
    Start-Background "AgentDock Desktop Pet (Tauri)" $DesktopDir "npm run dev" -ExtraEnv $extra -LogFile "desktop-pet-tauri.log"
    return $true
}

if ($NoPet) {
    # Dev / headless: Runtime only (pet is not running, so it cannot own the child).
    if (Test-PortListen 8765) {
        Write-Host "  skip Runtime — :8765 already listening"
    } else {
        Start-Background "AgentDock Runtime :8765" $Root "python -m runtime" -LogFile "runtime.log"
    }
    [void](Wait-PortListen 8765 $ReadyTimeoutSec "Runtime WS")
    [void](Wait-PortListen 8766 60 "Admin HTTP")
    $PetHint = "(none — -NoPet)"
} else {
    if (Start-TauriPet) {
        $PetHint = "Tauri (desktop / npm run dev; owns Runtime)"
    } elseif (Test-PortListen $PetPort) {
        Write-Host "  skip browser pet — :$PetPort already listening"
        $PetHint = $PetUrl
        try { Start-Process $PetUrl } catch { Write-Host "  (open: $PetUrl)" }
        # Browser fallback cannot spawn Runtime — start it here if needed.
        if (-not (Test-PortListen 8765)) {
            Start-Background "AgentDock Runtime :8765" $Root "python -m runtime" -LogFile "runtime.log"
        }
    } else {
        Write-Host "  Tauri not ready — browser fallback :$PetPort"
        if (-not (Test-PortListen 8765)) {
            Start-Background "AgentDock Runtime :8765" $Root "python -m runtime" -LogFile "runtime.log"
        }
        Start-Background "AgentDock Desktop Pet (web) :$PetPort" $Root "python -m desktop --port $PetPort --no-open" -LogFile "desktop-pet-web.log"
        [void](Wait-PortListen $PetPort 30 "Desktop pet web")
        $PetHint = "$PetUrl (browser fallback)"
        try { Start-Process $PetUrl } catch { Write-Host "  (open: $PetUrl)" }
    }
    # Pet (or fallback) should bring Runtime up; wait for ports.
    [void](Wait-PortListen 8765 $ReadyTimeoutSec "Runtime WS")
    [void](Wait-PortListen 8766 60 "Admin HTTP")
}

if ($PetHint -like "Tauri*") {
    $AdminHint = "desk-pet External http://127.0.0.1:8767 + admin_api; API $AdminApiUrl"
} else {
    $AdminHint = "requires Tauri desk-pet (no browser Admin UI); API $AdminApiUrl"
}
if ($Admin) {
    if ($PetHint -like "Tauri*") {
        # AGENTDOCK_OPEN_ADMIN already set when launching Tauri
    } else {
        Write-Host "  Console: install/run Tauri pet — Runtime does not serve /admin HTML"
    }
}

Write-Host ""
Write-Host "Host product (Runtime + desk pet):"
Write-Host "  Runtime WS    ws://127.0.0.1:8765"
Write-Host "  Desk pet      $PetHint"
Write-Host "  Console       $AdminHint"
Write-Host "  Console Dist  $ConsoleUrl (loopback static; dies with pet)"
Write-Host "  Pets assets   http://127.0.0.1:8766/pets/"
Write-Host ""
Write-Host "One app: talk to the pet; open Console (Ctrl+Shift+A / tray) to set Pi API Key."
Write-Host "Logs: data\logs\  (Runtime/Tauri run headless — no debug consoles)"
Write-Host "Stop: .\scripts\stop.ps1"

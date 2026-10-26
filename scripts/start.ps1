# AgentDock bootstrap — host Runtime + host desktop pet.
# Agents / voices are prepared in Admin; pet is a host feature (not a remote client).
#
#   .\scripts\start.ps1
#   .\scripts\start.ps1 -NoPet       # Runtime only (no desktop pet window)
#   .\scripts\start.ps1 -Admin       # open Admin as a second desk-pet window (Tauri)
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

function Start-Console([string]$Title, [string]$WorkDir, [string]$Command, [hashtable]$ExtraEnv = @{}) {
    $envLines = @(
        "`$Host.UI.RawUI.WindowTitle = '$Title'"
        "Set-Location -LiteralPath '$WorkDir'"
        "`$env:PYTHONUNBUFFERED = '1'"
    )
    foreach ($key in $ExtraEnv.Keys) {
        $val = [string]$ExtraEnv[$key]
        $envLines += "`$env:$key = '$val'"
    }
    $envLines += $Command
    $ps = $envLines -join "; "
    Start-Process -FilePath "powershell.exe" -WorkingDirectory $WorkDir -ArgumentList @(
        "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $ps
    ) | Out-Null
    Write-Host "  started: $Title"
}

Write-Host "AgentDock bootstrap (repo: $Root)"

if (Test-PortListen 8765) {
    Write-Host "  skip Runtime — :8765 already listening"
} else {
    Start-Console "AgentDock Runtime :8765" $Root "python -m runtime"
}

[void](Wait-PortListen 8765 $ReadyTimeoutSec "Runtime WS")
[void](Wait-PortListen 8766 60 "Admin HTTP")

$PetUrl = "http://127.0.0.1:${PetPort}/"
$AdminUrl = "http://127.0.0.1:8766/admin/"
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
    # tauri.dev's beforeDevCommand serves web on :8090; avoid clashing with a leftover server
    Start-Console "AgentDock Desktop Pet (Tauri)" $DesktopDir "npm run dev" $extra
    return $true
}

if (-not $NoPet) {
    if (Start-TauriPet) {
        $PetHint = "Tauri (desktop / npm run dev)"
    } elseif (Test-PortListen $PetPort) {
        Write-Host "  skip browser pet — :$PetPort already listening"
        $PetHint = $PetUrl
        try { Start-Process $PetUrl } catch { Write-Host "  (open: $PetUrl)" }
    } else {
        Write-Host "  Tauri not ready — browser fallback :$PetPort"
        Start-Console "AgentDock Desktop Pet (web) :$PetPort" $Root "python -m desktop --port $PetPort --no-open"
        [void](Wait-PortListen $PetPort 30 "Desktop pet web")
        $PetHint = "$PetUrl (browser fallback)"
        try { Start-Process $PetUrl } catch { Write-Host "  (open: $PetUrl)" }
    }
}

$AdminHint = $AdminUrl
if ($Admin) {
    if ($PetHint -like "Tauri*") {
        $AdminHint = "desk-pet second window (Ctrl+Shift+A)"
    } else {
        try {
            Start-Process $AdminUrl
            $AdminHint = "$AdminUrl (browser fallback)"
        } catch {
            Write-Host "  (open Admin manually: $AdminUrl)"
        }
    }
}

Write-Host ""
Write-Host "Endpoints:"
Write-Host "  Runtime WS    ws://127.0.0.1:8765"
Write-Host "  Desktop pet   $PetHint"
Write-Host "  Admin         $AdminHint"
Write-Host "  Pets assets   http://127.0.0.1:8766/pets/"
Write-Host ""
Write-Host "Configure Pi API Key in the desk-pet Admin window (Ctrl+Shift+A), then talk to the pet."
Write-Host "Stop: .\scripts\stop.ps1"

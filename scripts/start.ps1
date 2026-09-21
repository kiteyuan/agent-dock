# AgentDock bootstrap — only starts Runtime (WS :8765 + Admin :8766).
# Provider 安装、许可证确认与 sidecar 启停均在 Admin 完成。
#
#   .\scripts\start.ps1
#   .\scripts\start.ps1 -NoBrowser   # don't open Admin
#   .\scripts\stop.ps1
#
# Optional env (SoVITS path when started from Admin):
#   AGENTDOCK_GPT_SOVITS_ROOT
#   AGENTDOCK_GPT_SOVITS_PYTHON

param(
    [switch]$NoBrowser,
    [int]$ReadyTimeoutSec = 300
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

function Start-Console([string]$Title, [string]$WorkDir, [string]$Command) {
    $ps = @(
        "`$Host.UI.RawUI.WindowTitle = '$Title'"
        "Set-Location -LiteralPath '$WorkDir'"
        "`$env:PYTHONUNBUFFERED = '1'"
        $Command
    ) -join "; "
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

$admin = "http://127.0.0.1:8766/admin/"
Write-Host ""
Write-Host "Endpoints:"
Write-Host "  Runtime WS   ws://127.0.0.1:8765"
Write-Host "  Admin        $admin"
Write-Host "  Pets         http://127.0.0.1:8766/pets/"
Write-Host ""
Write-Host "Providers: choose assistants and voices in Admin"
Write-Host "Stop: .\scripts\stop.ps1"

if (-not $NoBrowser) {
    try {
        Start-Process $admin
    } catch {
        Write-Host "  (open Admin manually: $admin)"
    }
}

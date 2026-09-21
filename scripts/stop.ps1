# Stop AgentDock: ask Runtime to stop sidecars, then free well-known ports.
#   .\scripts\stop.ps1
#   .\scripts\stop.ps1 -KeepTts   # leave GPT-SoVITS :9880
#   .\scripts\stop.ps1 -KeepWeb

param(
    [switch]$KeepTts,
    [switch]$KeepWeb
)

$ErrorActionPreference = "Continue"

# Prefer graceful sidecar stop via Admin API (if Runtime is up)
try {
    $snapshot = Invoke-RestMethod -Uri "http://127.0.0.1:8766/api/v1/snapshot" -TimeoutSec 2
    foreach ($s in $snapshot.services) {
        if (-not $s.managed) { continue }
        if ($KeepTts -and $s.id -eq "sovits") { continue }
        if ($KeepWeb -and $s.id -eq "web") { continue }
        if ($s.can_stop -or $s.owned) {
            try {
                Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8766/api/v1/modules/service/$($s.id)/stop" -ContentType "application/json" -Body "{}" -TimeoutSec 8 | Out-Null
                Write-Host "admin stop $($s.id)"
            } catch {
                Write-Host "admin stop $($s.id) skipped"
            }
        }
    }
} catch {
    Write-Host "Admin not reachable — port kill only"
}

$ports = @(8765, 8766, 9001)
if (-not $KeepWeb) { $ports += 8090 }
if (-not $KeepTts) { $ports += 9880 }

foreach ($port in $ports) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) {
        Write-Host "free :$port"
        continue
    }
    $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $pids) {
        try {
            $p = Get-Process -Id $procId -ErrorAction Stop
            Write-Host "stop :$port pid=$procId ($($p.ProcessName))"
            Stop-Process -Id $procId -Force -ErrorAction Stop
        } catch {
            Write-Host "skip :$port pid=$procId ($($_.Exception.Message))"
        }
    }
}

Start-Sleep -Seconds 1
foreach ($port in $ports) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        Write-Host "still held :$port"
    } else {
        Write-Host "ok free :$port"
    }
}

# Record real-voice samples for hey 小哀, then retrain.
# Run on the PC that has the SAME mic path you'll use later (or the Pi mic via USB).
#
#   .\record.ps1 pos          # 50x wake word (hands off keyboard after Enter)
#   .\record.ps1 neg-speech  # near-homophones / your chat
#   .\record.ps1 neg-silence
#   .\record.ps1 neg-keyboard
#   .\record.ps1 neg-tv
#   .\record.ps1 archive-tts # move old Edge-TTS clips aside
#   .\record.ps1 train       # retrain + copy onnx into clients/rpi/models/

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet(
        "pos", "neg-speech", "neg-partial", "neg-silence", "neg-keyboard", "neg-tv", "neg-music",
        "archive-tts", "archive-pos", "train", "list", "test"
    )]
    [string]$Action,

    [int]$PosCount = 50,
    [int]$PosEverySec = 10,
    [double]$Threshold = 0.5
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
try { chcp 65001 | Out-Null } catch {}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Trainer = Join-Path $Root "train_workspace\custom-wakeword-trainer"
$Data = Join-Path $Trainer "data"
$Py = "E:\Projects\Base Projects\VoiceForge\.venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    $Py = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $Py) { throw "No Python found (VoiceForge .venv or PATH)." }

# Fail fast if mic capture deps missing
& $Py -c "import sounddevice" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing sounddevice into: $Py"
    & (Join-Path (Split-Path $Py) "pip.exe") install sounddevice
}

$env:WW_DATA = $Data
$env:WW_PHRASE = "hey_xiaoai"
$env:WW_NO_ACAV = "1"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"

function Invoke-Record {
    param([Parameter(Mandatory = $true)][string[]]$RecordArgs)
    Set-Location $Trainer
    & $Py -u scripts\record_sessions.py @RecordArgs
}

switch ($Action) {
    "list" {
        $pos = @(Get-ChildItem (Join-Path $Data "session-pos\*.wav") -ErrorAction SilentlyContinue).Count
        $neg = @(Get-ChildItem (Join-Path $Data "session-neg\*.wav") -ErrorAction SilentlyContinue).Count
        Write-Host "session-pos: $pos wav"
        Write-Host "session-neg: $neg wav"
        Write-Host "data: $Data"
    }
    "archive-tts" {
        $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
        foreach ($name in @("session-pos", "session-neg")) {
            $src = Join-Path $Data $name
            if (-not (Test-Path $src)) { continue }
            $dst = Join-Path $Data ("archive_tts_{0}_{1}" -f $name, $stamp)
            New-Item -ItemType Directory -Force -Path $dst | Out-Null
            Get-ChildItem $src -Filter "*.wav" | Move-Item -Destination $dst
            Write-Host "moved $name -> $dst"
        }
        Write-Host "TTS clips archived. Ready for your voice."
    }
    "archive-pos" {
        $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $src = Join-Path $Data "session-pos"
        if (Test-Path $src) {
            $dst = Join-Path $Data ("archive_pos_{0}" -f $stamp)
            New-Item -ItemType Directory -Force -Path $dst | Out-Null
            Get-ChildItem $src -Filter "*.wav" | Move-Item -Destination $dst
            Write-Host "moved session-pos -> $dst"
        }
        Write-Host "Old positives archived. Re-record with .\record.ps1 pos"
    }
    "pos" {
        Write-Host ""
        Write-Host "=== POS: say ONLY the wake phrase (hey xiao ai) ==="
        Write-Host "- Press Enter once, then hands OFF the keyboard"
        Write-Host "- Speak when you see >>> NOW <<<"
        Write-Host "- Vary: normal / quiet / loud / fast / slow / turn away / farther"
        Write-Host "- $PosCount clips, ~$([math]::Round($PosCount * $PosEverySec / 60, 1)) min"
        Write-Host ""
        Invoke-Record -RecordArgs @("pos", "$PosCount", "$PosEverySec")
    }
    "neg-speech" {
        Write-Host ""
        Write-Host "=== NEG speech: talk, but NEVER the full wake phrase ==="
        Write-Host ""
        Invoke-Record -RecordArgs @("neg", "180", "speech")
    }
    "neg-partial" {
        Write-Host ""
        Write-Host "=== NEG partial: ONLY half-phrases (hey OR xiaoai alone) ==="
        Write-Host "Never say the full wake word in this session."
        Write-Host ""
        Invoke-Record -RecordArgs @("neg", "180", "partial")
    }
    "neg-silence" {
        Write-Host ""
        Write-Host "=== NEG silence: empty room ==="
        Write-Host ""
        Invoke-Record -RecordArgs @("neg", "60", "silence")
    }
    "neg-keyboard" {
        Write-Host ""
        Write-Host "=== NEG keyboard: type hard ==="
        Write-Host ""
        Invoke-Record -RecordArgs @("neg", "120", "keyboard")
    }
    "neg-tv" {
        Write-Host ""
        Write-Host "=== NEG tv: speakers / YouTube ==="
        Write-Host ""
        Invoke-Record -RecordArgs @("neg", "180", "tv")
    }
    "neg-music" {
        Write-Host ""
        Write-Host "=== NEG music: headphone bleed ==="
        Write-Host ""
        Invoke-Record -RecordArgs @("neg", "120", "music")
    }
    "train" {
        Set-Location $Trainer
        & $Py -u scripts\train.py
        $onnx = Join-Path $Trainer "hey_xiaoai.onnx"
        $dst = Join-Path $Root "..\models\hey_xiaoai.onnx"
        New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
        Copy-Item $onnx $dst -Force
        Write-Host "copied -> $dst"
    }
    "test" {
        Write-Host ""
        Write-Host "=== Live wake test (Ctrl+C to stop) ==="
        Write-Host "Say: hey xiao ai   threshold=$Threshold"
        Write-Host ""
        Set-Location $Root
        & $Py -u test_wake.py --threshold $Threshold
    }
}

# Anki Puppeteer: opens Anki (if needed), then starts voice control.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Anki = Join-Path $env:LOCALAPPDATA "Programs\Anki\anki.exe"
$Python = Join-Path $Root ".venv\Scripts\python.exe"

try {
    $Host.UI.RawUI.WindowTitle = "Anki Puppeteer"
} catch {}

function Write-Step([string]$text) {
    Write-Host $text
}

if (-not (Test-Path $Python)) {
    Write-Host "The voice program is not installed at $Root"
    Write-Host "Expected Python at $Python"
    Read-Host "Press Enter to close"
    exit 1
}

if (-not (Get-Process -Name "anki" -ErrorAction SilentlyContinue)) {
    if (-not (Test-Path $Anki)) {
        Write-Host "Could not find Anki at $Anki"
        Read-Host "Press Enter to close"
        exit 1
    }
    Write-Step "Opening Anki..."
    Start-Process -FilePath $Anki
} else {
    Write-Step "Anki is already open."
}

Write-Step "Waiting for Anki to be ready..."
$ready = $false
for ($i = 0; $i -lt 45; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8765" -Method POST -ContentType "application/json" -Body '{"action":"version","version":6}' -TimeoutSec 2 -UseBasicParsing
        if ($resp.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
    }
    if (-not $ready) {
        Start-Sleep -Seconds 1
    }
}

if ($ready) {
    Write-Step "Anki is ready."
} else {
    Write-Step "Anki is open, but the voice add-on is not answering yet."
    Write-Step "Start a review in Anki, then press Enter here."
    Read-Host
}

Write-Host ""
Write-Step "Voice control is on. Say: show, again, hard, good, easy, undo."
Write-Step "Close this window to stop."
Write-Host ""

Set-Location $Root
& $Python -u -m anki_puppeteer --stt tiny
$code = $LASTEXITCODE
if ($code -ne 0) {
    Write-Host ""
    Write-Host "The voice program stopped (code $code)."
    Read-Host "Press Enter to close"
}
exit $code

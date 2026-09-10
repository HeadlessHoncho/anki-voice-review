# Builds the .ico and puts "Anki Puppeteer" in the Start menu.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Assets = Join-Path $Root "assets"
$Scripts = Join-Path $Root "scripts"
$SrcJpg = Join-Path $Assets "anki-puppeteer-icon-src.jpg"
$Ico = Join-Path $Assets "anki-puppeteer.ico"
$Launcher = Join-Path $Scripts "Start-AnkiPuppeteer.ps1"
$StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$Shortcut = Join-Path $StartMenu "Anki Puppeteer.lnk"

if (-not (Test-Path $SrcJpg)) {
    throw "Missing icon source $SrcJpg"
}

Add-Type -AssemblyName System.Drawing
$src = [System.Drawing.Image]::FromFile($SrcJpg)
$pngs = @()
try {
    foreach ($size in 16, 32, 48, 64, 128, 256) {
        $bmp = New-Object System.Drawing.Bitmap $size, $size
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
        $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
        $g.Clear([System.Drawing.Color]::Transparent)
        $g.DrawImage($src, 0, 0, $size, $size)
        $g.Dispose()
        $pngPath = Join-Path $env:TEMP ("anki-puppeteer-$size.png")
        $bmp.Save($pngPath, [System.Drawing.Imaging.ImageFormat]::Png)
        $bmp.Dispose()
        $pngs += $pngPath
    }
} finally {
    $src.Dispose()
}

$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
& $py -c @"
import struct, pathlib
paths = r'''$($pngs -join '|')'''.split('|')
entries = []
offset = 6 + 16 * len(paths)
blobs = []
for p in paths:
    data = pathlib.Path(p).read_bytes()
    blobs.append(data)
    entries.append((data, offset))
    offset += len(data)
out = bytearray()
out += struct.pack('<HHH', 0, 1, len(paths))
off = 6 + 16 * len(paths)
for data in blobs:
    # PNG IHDR: width/height at bytes 16-23
    w = struct.unpack('>I', data[16:20])[0]
    h = struct.unpack('>I', data[20:24])[0]
    out += struct.pack('<BBBBHHII', w if w < 256 else 0, h if h < 256 else 0, 0, 0, 1, 32, len(data), off)
    off += len(data)
for data in blobs:
    out += data
pathlib.Path(r'$Ico').write_bytes(out)
print('wrote', r'$Ico', len(out), 'bytes')
"@

New-Item -ItemType Directory -Force -Path $StartMenu | Out-Null
$w = New-Object -ComObject WScript.Shell
$s = $w.CreateShortcut($Shortcut)
$s.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$s.Arguments = "-NoLogo -ExecutionPolicy Bypass -File `"$Launcher`""
$s.WorkingDirectory = $Root
$s.WindowStyle = 1
$s.Description = "Anki Puppeteer: open Anki and review cards by voice"
$s.IconLocation = "$Ico,0"
$s.Save()

Write-Host "Start menu shortcut: $Shortcut"
Write-Host "Look for 'Anki Puppeteer' in the Start menu."

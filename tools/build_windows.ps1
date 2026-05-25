$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Icon = Join-Path $Root "src\heartopia_painter\resources\app_icon.ico"
$Resources = Join-Path $Root "src\heartopia_painter\resources"
$Main = Join-Path $Root "main.py"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing venv Python: $Python"
}
if (-not (Test-Path -LiteralPath $Icon)) {
    throw "Missing app icon: $Icon"
}

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --uac-admin `
    --name "Heartopia Image Painter" `
    --icon "$Icon" `
    --paths (Join-Path $Root "src") `
    --add-data "$Resources;heartopia_painter\resources" `
    "$Main"

$Exe = Join-Path $Root "dist\Heartopia Image Painter.exe"
if (-not (Test-Path -LiteralPath $Exe)) {
    throw "Build did not create: $Exe"
}

Write-Host "Built: $Exe"

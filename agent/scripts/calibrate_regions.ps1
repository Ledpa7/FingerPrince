$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venvPython = Join-Path $root ".venv\\Scripts\\python.exe"
if (-not (Test-Path $venvPython)) {
  throw "Venv python not found at $venvPython. Run integration\\start_agent.ps1 once to create .venv."
}

Write-Host "Region calibration will open a draggable/resizable window (most reliable)." -ForegroundColor Cyan
Write-Host "1) Red box: drag/resize to cover VS Code Codex INPUT area, click OK." -ForegroundColor Yellow
Write-Host "2) Blue box: drag/resize to cover VS Code Codex OUTPUT (transcript) area, click OK." -ForegroundColor Yellow
Write-Host "Shortcuts: Enter = OK, Esc = Cancel." -ForegroundColor Yellow

& $venvPython (Join-Path $root "region_picker.py") --mode window

Write-Host "Done. Check agent\\.env for IDE_INPUT_REGION / IDE_OUTPUT_REGION." -ForegroundColor Green

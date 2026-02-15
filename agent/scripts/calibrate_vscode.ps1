$ErrorActionPreference = "Stop"

# Calibrate VS Code chat UI targets without needing to click a web button.
# You will hover your mouse over the target UI areas when prompted.

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = Join-Path $root ".venv\\Scripts\\python.exe"
if (-not (Test-Path $py)) {
  throw "Venv python not found at $py. Run integration/start_agent.ps1 once to create the venv."
}

function Write-Utf8NoBom([string]$path, [string]$text) {
  [System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))
}

function Upsert-EnvLine([string]$content, [string]$key, [string]$value) {
  $pattern = "(?m)^\\s*" + [regex]::Escape($key) + "\\s*=.*$"
  $line = "$key=$value"
  if ($content -match $pattern) {
    return [regex]::Replace($content, $pattern, $line)
  }
  if ($content -and -not $content.EndsWith("`n")) { $content += "`n" }
  return $content + $line + "`n"
}

$envPath = Join-Path $root ".env"
$envContent = if (Test-Path $envPath) { Get-Content $envPath -Raw } else { "" }

$title = Read-Host "VS Code window title substring? (default: Visual Studio Code)"
if (-not $title) { $title = "Visual Studio Code" }

$w = Read-Host "Template width (default 240)"
if (-not $w) { $w = "240" }
$h = Read-Host "Template height (default 120)"
if (-not $h) { $h = "120" }

Write-Host ""
Write-Host "[1/2] Hover your mouse over the VS Code chat INPUT box." -ForegroundColor Cyan
Write-Host "      Capturing in 5 seconds..." -ForegroundColor DarkGray
Start-Sleep -Seconds 5

$inputPath = & $py -c "import pyautogui, os; from pathlib import Path; import time; w=int(os.environ.get('W','$w')); h=int(os.environ.get('H','$h')); p=pyautogui.position(); left=max(0,int(p.x-w//2)); top=max(0,int(p.y-h//2)); out=Path('assets'); out.mkdir(parents=True, exist_ok=True); f=out/'ide_input_template.png'; pyautogui.screenshot(region=(left,top,w,h)).save(f); print(str(f))"

Write-Host ""
Write-Host "[2/2] Hover your mouse over the VS Code chat OUTPUT/TRANSCRIPT area." -ForegroundColor Cyan
Write-Host "      Capturing in 5 seconds..." -ForegroundColor DarkGray
Start-Sleep -Seconds 5

$outputPath = & $py -c "import pyautogui, os; from pathlib import Path; import time; w=int(os.environ.get('W','$w')); h=int(os.environ.get('H','$h')); p=pyautogui.position(); left=max(0,int(p.x-w//2)); top=max(0,int(p.y-h//2)); out=Path('assets'); out.mkdir(parents=True, exist_ok=True); f=out/'ide_output_template.png'; pyautogui.screenshot(region=(left,top,w,h)).save(f); print(str(f))"

$envContent = Upsert-EnvLine $envContent "IDE_WINDOW_TITLE_SUBSTR" $title
$envContent = Upsert-EnvLine $envContent "IDE_INPUT_IMAGE" $inputPath
$envContent = Upsert-EnvLine $envContent "IDE_OUTPUT_IMAGE" $outputPath

Write-Utf8NoBom $envPath $envContent

Write-Host ""
Write-Host "Saved:" -ForegroundColor Green
Write-Host "- $inputPath" -ForegroundColor Green
Write-Host "- $outputPath" -ForegroundColor Green
Write-Host ""
Write-Host "Updated .env with IDE_* settings. Restart the agent to apply." -ForegroundColor Yellow


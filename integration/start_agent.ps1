$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "agent")

# Prevent accidental double-runs: use the agent's singleton lock port (default 45321).
$lockPort = 45321
$envPath = Join-Path (Get-Location) ".env"
if (Test-Path $envPath) {
  $line = Get-Content $envPath -ErrorAction SilentlyContinue | Where-Object { $_ -match '^AGENT_LOCK_PORT=' } | Select-Object -First 1
  if ($line) {
    $v = ($line -split '=', 2)[1].Trim()
    if ($v -match '^\d+$') { $lockPort = [int]$v }
  }
}
try {
  $listener = Get-NetTCPConnection -State Listen -LocalPort $lockPort -ErrorAction SilentlyContinue
  if ($listener) {
    Write-Host "Agent already running (lock port $lockPort is listening). Stop it (Ctrl+C) before starting again." -ForegroundColor Yellow
    exit 0
  }
} catch {
  # Ignore; some environments may not have Get-NetTCPConnection.
}

function Resolve-PythonPath {
  # 1) python on PATH
  $pyCmd = Get-Command python -ErrorAction SilentlyContinue
  if ($pyCmd) {
    $path = if ($pyCmd.Path) { $pyCmd.Path } else { $pyCmd.Source }
    if ($path -and ($path -notlike "*\\WindowsApps\\python.exe")) {
      return $path
    }
  }

  # 2) py launcher
  $launcher = Get-Command py -ErrorAction SilentlyContinue
  if ($launcher) {
    # Prefer explicit 3.x
    $v = (& $launcher.Source -3 --version 2>&1)
    if ($v -match "^Python\s+\d+\.\d+\.\d+") {
      return "$($launcher.Source) -3"
    }
  }

  # 3) Common install locations
  $candidates = @()
  $local = $env:LocalAppData
  if ($local) {
    $candidates += Get-ChildItem -Path (Join-Path $local "Programs\\Python\\Python*\\python.exe") -ErrorAction SilentlyContinue
  }
  $pf = $env:ProgramFiles
  if ($pf) {
    $candidates += Get-ChildItem -Path (Join-Path $pf "Python*\\python.exe") -ErrorAction SilentlyContinue
  }
  $pfx86 = ${env:ProgramFiles(x86)}
  if ($pfx86) {
    $candidates += Get-ChildItem -Path (Join-Path $pfx86 "Python*\\python.exe") -ErrorAction SilentlyContinue
  }

  if ($candidates.Count -gt 0) {
    # pick newest by directory name sort (Python313 > Python312, etc.)
    $best = $candidates | Sort-Object FullName -Descending | Select-Object -First 1
    return $best.FullName
  }

  return $null
}

$pythonSpec = Resolve-PythonPath
if (-not $pythonSpec) {
  throw @"
No usable Python found.

Fix options:
1) Re-run Python installer and enable 'Add python.exe to PATH'.
2) Or install the Python Launcher (py) and use that.

After fixing, verify in a NEW PowerShell:
  where.exe python
  python --version
  where.exe py
  py --version
"@
}

# If pythonSpec is like 'C:\path\py.exe -3', split it.
$pythonParts = $pythonSpec -split "\s+", 2
$pythonExe = $pythonParts[0]
$pythonArgs = @()
if ($pythonParts.Count -gt 1) {
  $pythonArgs = @($pythonParts[1])
}

# Validate version output (best-effort)
$verOut = & $pythonExe @($pythonArgs + @("--version")) 2>&1
if ($verOut -notmatch "^Python\s+\d+\.\d+\.\d+") {
  throw "Resolved Python does not look valid: $pythonSpec (output: $verOut)"
}

Write-Host "Using: $pythonSpec ($verOut)" -ForegroundColor Cyan

if (-not (Test-Path ".venv")) {
  & $pythonExe @($pythonArgs + @("-m", "venv", ".venv"))
}

$venvPython = Join-Path (Get-Location) ".venv\\Scripts\\python.exe"
if (-not (Test-Path $venvPython)) {
  throw "Venv python not found at $venvPython. Delete .venv and re-run."
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt
& $venvPython main.py

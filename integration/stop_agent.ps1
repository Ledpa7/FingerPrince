$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot

# Prefer the agent's singleton lock port (default 45321) to identify the main process.
$lockPort = 45321
$envPath = Join-Path (Join-Path $root "agent") ".env"
if (Test-Path $envPath) {
  $line = Get-Content $envPath -ErrorAction SilentlyContinue | Where-Object { $_ -match '^AGENT_LOCK_PORT=' } | Select-Object -First 1
  if ($line) {
    $v = ($line -split '=', 2)[1].Trim()
    if ($v -match '^\d+$') { $lockPort = [int]$v }
  }
}

$mainPid = $null
try {
  $listener = Get-NetTCPConnection -State Listen -LocalPort $lockPort -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($listener) { $mainPid = $listener.OwningProcess }
} catch {
  # Ignore environments without Get-NetTCPConnection.
}

# Best-effort: stop the main PID (lock port owner) plus any other python main.py processes under ServerVibe/agent.
$candidates = @()
if ($mainPid) {
  $candidates += [pscustomobject]@{ ProcessId = $mainPid }
}
$candidates += Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
  $_.Name -eq "python.exe" -and $_.CommandLine -match "ServerVibe" -and $_.CommandLine -match "main\\.py"
} | Select-Object -ExpandProperty ProcessId | ForEach-Object { [pscustomobject]@{ ProcessId = $_ } }

$candidates = $candidates | Select-Object -Unique ProcessId

if (-not $candidates) {
  Write-Host "No running agent process found." -ForegroundColor Yellow
  exit 0
}

$pids = ($candidates | Select-Object -ExpandProperty ProcessId)
Write-Host ("Stopping agent PID(s): " + (($pids -join ", "))) -ForegroundColor Cyan

foreach ($procId in $pids) {
  try {
    Stop-Process -Id $procId -Force -ErrorAction Stop
  } catch {
    Write-Host ("Failed to stop PID " + $procId + ": " + $_.Exception.Message) -ForegroundColor Red
  }
}

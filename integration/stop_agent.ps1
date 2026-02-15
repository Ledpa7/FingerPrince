$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$agentDir = Join-Path $root "agent"

# Best-effort: find python processes that look like the ServerVibe agent.
$candidates = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
  $_.Name -eq "python.exe" -and $_.CommandLine -match "ServerVibe\\\\agent" -and $_.CommandLine -match "main\\.py"
}

if (-not $candidates) {
  Write-Host "No running agent process found." -ForegroundColor Yellow
  exit 0
}

$pids = ($candidates | Select-Object -ExpandProperty ProcessId)
Write-Host ("Stopping agent PID(s): " + (($pids -join ", "))) -ForegroundColor Cyan

foreach ($pid in $pids) {
  try {
    Stop-Process -Id $pid -Force -ErrorAction Stop
  } catch {
    Write-Host ("Failed to stop PID " + $pid + ": " + $_.Exception.Message) -ForegroundColor Red
  }
}


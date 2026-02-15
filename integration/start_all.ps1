$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot

Write-Host "Starting ServerVibe (web + agent)..." -ForegroundColor Cyan

# Start web in a new PowerShell window (keeps logs visible).
Start-Process powershell -WorkingDirectory (Join-Path $root "web") -ArgumentList @(
  "-NoExit",
  "-Command",
  "Set-Location '$($root)\\web'; npm install; npm run dev"
)

# Start agent in a new PowerShell window.
Start-Process powershell -WorkingDirectory (Join-Path $root "agent") -ArgumentList @(
  "-NoExit",
  "-Command",
  "Set-Location '$($root)\\agent'; & '$($root)\\integration\\start_agent.ps1'"
)

Write-Host "Launched. If you need to stop the agent: run integration\\stop_agent.ps1" -ForegroundColor Yellow


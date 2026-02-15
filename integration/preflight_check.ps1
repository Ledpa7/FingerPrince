param()

$root = Split-Path -Parent $PSScriptRoot
$agentEnv = Join-Path $root "agent\.env"
$webEnv = Join-Path $root "web\.env.local"

Write-Host "[Preflight] Server Vibe Step4" -ForegroundColor Cyan

if (-not (Test-Path $agentEnv)) {
  Write-Host "- agent/.env missing" -ForegroundColor Red
} else {
  Write-Host "- agent/.env found" -ForegroundColor Green
}

if (-not (Test-Path $webEnv)) {
  Write-Host "- web/.env.local missing" -ForegroundColor Red
} else {
  Write-Host "- web/.env.local found" -ForegroundColor Green
}

$agentContent = if (Test-Path $agentEnv) { Get-Content $agentEnv -Raw } else { "" }
$webContent = if (Test-Path $webEnv) { Get-Content $webEnv -Raw } else { "" }

function Check-Placeholder($text, $token) {
  return ($text -match [regex]::Escape($token))
}

$issues = @()
if (Check-Placeholder $agentContent "YOUR_PROJECT_REF") { $issues += "agent SUPABASE_URL placeholder" }
if (Check-Placeholder $agentContent "YOUR_SUPABASE_SERVICE_ROLE_KEY") { $issues += "agent SUPABASE_KEY placeholder" }
if (Check-Placeholder $webContent "NEXT_PUBLIC_SUPABASE_URL=") { }
if ($webContent -match "NEXT_PUBLIC_SUPABASE_URL=\s*$") { $issues += "web NEXT_PUBLIC_SUPABASE_URL empty" }
if ($webContent -match "NEXT_PUBLIC_SUPABASE_ANON_KEY=\s*$") { $issues += "web NEXT_PUBLIC_SUPABASE_ANON_KEY empty" }

if ($issues.Count -gt 0) {
  Write-Host "\n[Action Needed]" -ForegroundColor Yellow
  $issues | ForEach-Object { Write-Host "- $_" -ForegroundColor Yellow }
} else {
  Write-Host "\nNo placeholder issues detected." -ForegroundColor Green
}

$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
  $_.IPAddress -notlike "127.*" -and $_.PrefixOrigin -ne "WellKnown"
} | Select-Object -First 1 -ExpandProperty IPAddress)

if ($ip) {
  Write-Host "\nMobile URL: http://$ip`:3000" -ForegroundColor Cyan
} else {
  Write-Host "\nMobile URL: <IP 확인 실패>" -ForegroundColor Yellow
}

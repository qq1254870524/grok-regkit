# restart_all_hidden_18r40.ps1 — no console windows for web/matrix/monitors
$ErrorActionPreference = 'Continue'
$Root = 'C:\Users\zhang\grok-regkit'
$Tools = Join-Path $Root 'tools'
$startHidden = Join-Path $Tools 'start_hidden.ps1'
$startWeb = Join-Path $Tools 'start_web8092_hidden.ps1'

function Kill-ByPat([string]$pat, [string]$label) {
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { ($_.Name -match '^(python|pythonw)\.exe$') -and $_.CommandLine -and ($_.CommandLine -match $pat) } |
    ForEach-Object {
      Write-Host "[kill] $label PID=$($_.ProcessId)"
      Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "=== hide/restart grok-regkit related python (no windows) ==="

# Kill visible agent processes we own (not granian venv path carefully)
Kill-ByPat 'matrix_18r40_multithread|matrix_18r40_live_mon|session_monitor_loop' 'matrix/mon'
Kill-ByPat 'matrix_runs\\_codex_watchdog|matrix_runs/_codex_watchdog' 'watchdog'
Kill-ByPat 'matrix_runs\\_codex_agent_poll|matrix_runs/_codex_agent_poll' 'agent_poll'
Kill-ByPat 'matrix_runs\\_codex_bg_watch|matrix_runs/_codex_bg_watch' 'bg_watch'
Kill-ByPat 'matrix_runs\\_codex_status_snap|matrix_runs/_codex_status_snap' 'status_snap'
Kill-ByPat 'matrix_runs\\_codex_pulse_loop|matrix_runs/_codex_pulse_loop' 'pulse'
Kill-ByPat 'web\\server\.py|web/server\.py|uvicorn web\.server' 'web'
Start-Sleep -Seconds 1

# Web hidden formal
& powershell -NoProfile -ExecutionPolicy Bypass -File $startWeb

# Matrix hidden (continue 18r40)
& powershell -NoProfile -ExecutionPolicy Bypass -File $startHidden `
  -Name 'matrix18r40' -FilePath 'python' `
  -ArgumentList @('-B','tools\matrix_18r40_multithread.py') `
  -WorkDir $Root -Match 'matrix_18r40_multithread' -KillMatch `
  -OutLog 'logs\matrix18r40.out.log' -ErrLog 'logs\matrix18r40.err.log'

# Monitors hidden
& powershell -NoProfile -ExecutionPolicy Bypass -File $startHidden `
  -Name 'watchdog' -FilePath 'python' `
  -ArgumentList @('-B','matrix_runs\_codex_watchdog.py') `
  -WorkDir $Root -Match '_codex_watchdog\.py' -KillMatch

& powershell -NoProfile -ExecutionPolicy Bypass -File $startHidden `
  -Name 'agent_poll' -FilePath 'python' `
  -ArgumentList @('-B','matrix_runs\_codex_agent_poll.py') `
  -WorkDir $Root -Match '_codex_agent_poll\.py' -KillMatch

& powershell -NoProfile -ExecutionPolicy Bypass -File $startHidden `
  -Name 'bg_watch' -FilePath 'python' `
  -ArgumentList @('-B','matrix_runs\_codex_bg_watch.py') `
  -WorkDir $Root -Match '_codex_bg_watch\.py' -KillMatch

& powershell -NoProfile -ExecutionPolicy Bypass -File $startHidden `
  -Name 'status_snap' -FilePath 'python' `
  -ArgumentList @('-B','matrix_runs\_codex_status_snap.py') `
  -WorkDir $Root -Match '_codex_status_snap\.py' -KillMatch

& powershell -NoProfile -ExecutionPolicy Bypass -File $startHidden `
  -Name 'pulse' -FilePath 'python' `
  -ArgumentList @('-B','matrix_runs\_codex_pulse_loop.py') `
  -WorkDir $Root -Match '_codex_pulse_loop\.py' -KillMatch

& powershell -NoProfile -ExecutionPolicy Bypass -File $startHidden `
  -Name 'matrix_live_mon' -FilePath 'python' `
  -ArgumentList @('-B','C:\Users\zhang\Desktop\codex_aidate_tmp\matrix_18r40_live_mon.py') `
  -WorkDir 'C:\Users\zhang\Desktop\codex_aidate_tmp' -Match 'matrix_18r40_live_mon' -KillMatch `
  -OutLog (Join-Path $Root 'logs\matrix_live_mon.out.log') `
  -ErrLog (Join-Path $Root 'logs\matrix_live_mon.err.log')

# Side services: restart hidden if not listening
function PortUp([int]$p) {
  try {
    $c = New-Object Net.Sockets.TcpClient
    $iar = $c.BeginConnect('127.0.0.1', $p, $null, $null)
    $ok = $iar.AsyncWaitHandle.WaitOne(700, $false)
    if (-not $ok) { $c.Close(); return $false }
    $c.EndConnect($iar); $c.Close(); return $true
  } catch { return $false }
}

if (-not (PortUp 8010)) {
  $g2a = 'C:\Users\zhang\grok-regkit-services1\grok2api1'
  $py = Join-Path $g2a '.venv\Scripts\python.exe'
  if (Test-Path $py) {
    Start-Process -FilePath $py -ArgumentList @('-m','granian','--interface','asgi','--host','127.0.0.1','--port','8010','app.main:app') `
      -WorkingDirectory $g2a -WindowStyle Hidden -PassThru `
      -RedirectStandardOutput (Join-Path $Root 'logs\granian8010.out.log') `
      -RedirectStandardError (Join-Path $Root 'logs\granian8010.err.log') | Out-Null
    Write-Host "[granian8010] hidden start"
  }
} else { Write-Host "[granian8010] already up (leave)" }

if (-not (PortUp 8318)) {
  $svc = 'C:\Users\zhang\grok-regkit-services1'
  $cpa = Join-Path $svc 'cpa_gateway1\cpa_gateway1.py'
  if (-not (Test-Path $cpa)) { $cpa = Join-Path $svc 'cpa_gateway1.py' }
  $py = if (Test-Path 'C:\Python312\python.exe') { 'C:\Python312\python.exe' } else { 'python' }
  Start-Process -FilePath $py -ArgumentList @('-B', $cpa, 'serve') `
    -WorkingDirectory (Split-Path $cpa -Parent) -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $Root 'logs\cpa8318.out.log') `
    -RedirectStandardError (Join-Path $Root 'logs\cpa8318.err.log') | Out-Null
  Write-Host "[cpa8318] hidden start"
} else { Write-Host "[cpa8318] already up (leave)" }

Start-Sleep -Seconds 2
Write-Host "=== ports ==="
foreach ($p in 8092,8010,8318) {
  Write-Host ("port {0} = {1}" -f $p, (PortUp $p))
}
Write-Host "=== related procs ==="
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    ($_.Name -match '^(python|pythonw)\.exe$') -and $_.CommandLine -and (
      $_.CommandLine -match 'grok-regkit\\web|uvicorn web\.server|matrix_18r40|_codex_watchdog|_codex_agent_poll|_codex_bg_watch|_codex_status_snap|_codex_pulse|matrix_18r40_live_mon|cpa_gateway|granian'
    )
  } |
  ForEach-Object {
    $cl = $_.CommandLine
    if ($cl.Length -gt 120) { $cl = $cl.Substring(0,120) + '...' }
    Write-Host ("PID={0} {1}" -f $_.ProcessId, $cl)
  }
Write-Host "DONE hidden restart"

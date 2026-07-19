# start_web8092_hidden.ps1 — formal grok-regkit web on 8092, NO console window
# Agents MUST use this (or equivalent CreateNoWindow). Never Start-Process with visible console / WindowTitle web8092.
$ErrorActionPreference = 'Stop'
$Root = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $Root
$logDir = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$outLog = Join-Path $logDir 'web8092.out.log'
$errLog = Join-Path $logDir 'web8092.err.log'

$listen = Get-NetTCPConnection -LocalPort 8092 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listen) {
  Write-Host "[web8092] already listening PID=$($listen.OwningProcess) (no new window)"
  exit 0
}

Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match 'web\\server\.py|web/server\.py' } |
  ForEach-Object {
    Write-Host "[web8092] stopping stale PID=$($_.ProcessId)"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }
Start-Sleep -Milliseconds 400

$py = if (Test-Path 'C:\Python312\python.exe') { 'C:\Python312\python.exe' } else { (Get-Command python).Source }

# Hidden + log redirect, no console window
$p = Start-Process -FilePath $py -ArgumentList '-B','web\server.py' `
  -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput $outLog -RedirectStandardError $errLog

$ok = $false
for ($i = 0; $i -lt 50; $i++) {
  Start-Sleep -Milliseconds 200
  if (Get-NetTCPConnection -LocalPort 8092 -State Listen -ErrorAction SilentlyContinue) { $ok = $true; break }
}
if ($ok) {
  Write-Host "[web8092] hidden OK PID=$($p.Id) http://127.0.0.1:8092"
  Write-Host "[web8092] logs: $outLog | $errLog"
  exit 0
}
Write-Host "[web8092] process PID=$($p.Id) but 8092 not listening; see $errLog"
exit 1

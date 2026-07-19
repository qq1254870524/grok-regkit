$ErrorActionPreference = "Continue"
$log = "C:\Users\zhang\grok-regkit\matrix_runs\force_switch_2round.log"
function L($m){ Add-Content $log ("{0} {1}" -f (Get-Date -Format o), $m) }
L "FORCE switch begin"
# stop register only
try { Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8092/api/stop" -TimeoutSec 10 | Out-Null; L "api/stop ok" } catch { L "api/stop $($_)" }
Start-Sleep -Seconds 4
try {
  $st = Invoke-RestMethod "http://127.0.0.1:8092/api/status" -TimeoutSec 5
  L "status run=$($st.running) s=$($st.success) p=$($st.pending_sso)"
  if ($st.running) {
    Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8092/api/stop" -TimeoutSec 10 | Out-Null
    Start-Sleep -Seconds 3
  }
} catch { L "status $_" }

# kill matrix processes and previous switch waiter if any
Get-CimInstance Win32_Process | Where-Object {
  ($_.Name -match 'python') -and ($_.CommandLine -match 'matrix_cross_run')
} | ForEach-Object { L "kill matrix $($_.ProcessId)"; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Get-CimInstance Win32_Process | Where-Object {
  ($_.Name -match 'powershell') -and ($_.CommandLine -match 'switch_to_2round.ps1')
} | ForEach-Object { L "kill old switch $($_.ProcessId)"; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Start-Sleep -Seconds 2

# confirm 8010/8317/8318 still up
foreach ($port in 8010,8317,8318,8092) {
  $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  L "port $port listen=$([bool]$c)"
}

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$out = "C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r21_2round_$ts"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$env:PYTHONDONTWRITEBYTECODE = "1"
# matrix uses hardcoded OUT under matrix_runs with timestamp - check if env MATRIX_OUT supported
Set-Location "C:\Users\zhang\grok-regkit"
$p = Start-Process -FilePath "C:\Python312\python.exe" -ArgumentList @("-B","tools\matrix_cross_run.py","2","720") -WorkingDirectory "C:\Users\zhang\grok-regkit" -WindowStyle Hidden -RedirectStandardOutput (Join-Path $out "runner_console.log") -RedirectStandardError (Join-Path $out "runner_console.err.log") -PassThru
Set-Content "C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r21_active.txt" $out
L "started matrix pid=$($p.Id) out=$out"
L "FORCE_SWITCH_DONE"

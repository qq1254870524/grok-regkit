$ErrorActionPreference = "Continue"
$log = "C:\Users\zhang\grok-regkit\matrix_runs\switch_to_2round.log"
function L($m){ $t=(Get-Date -Format o); Add-Content $log "$t $m"; Write-Output "$t $m" }

L "waiting for current 8092 job to finish..."
for ($i=0; $i -lt 60; $i++) {
  try {
    $st = Invoke-RestMethod "http://127.0.0.1:8092/api/status" -TimeoutSec 5
    L "wait i=$i run=$($st.running) s=$($st.success) p=$($st.pending_sso) f=$($st.fail)"
    if (-not $st.running) { break }
  } catch { L "status err $_" }
  Start-Sleep -Seconds 5
}

# stop only register job if still running
try {
  Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8092/api/stop" -TimeoutSec 8 | Out-Null
  L "posted /api/stop"
} catch { L "stop post: $_" }
Start-Sleep -Seconds 3

# kill only matrix_cross_run.py
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'matrix_cross_run' } | ForEach-Object {
  L "killing matrix pid=$($_.ProcessId)"
  Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2

# ensure no leftover register job
try {
  $st = Invoke-RestMethod "http://127.0.0.1:8092/api/status" -TimeoutSec 5
  L "after stop run=$($st.running)"
  if ($st.running) {
    Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8092/api/stop" -TimeoutSec 8 | Out-Null
    Start-Sleep -Seconds 2
  }
} catch { L "post-stop status: $_" }

# start 2-round matrix
$outRoot = "C:\Users\zhang\grok-regkit\matrix_runs"
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:MATRIX_OUT = Join-Path $outRoot "matrix_18r21_2round_$ts"
New-Item -ItemType Directory -Force -Path $env:MATRIX_OUT | Out-Null
L "starting matrix ROUNDS=2 OUT=$($env:MATRIX_OUT)"
Set-Location "C:\Users\zhang\grok-regkit"
$p = Start-Process -FilePath "C:\Python312\python.exe" -ArgumentList @("-B","tools\matrix_cross_run.py","2","720") -WorkingDirectory "C:\Users\zhang\grok-regkit" -WindowStyle Hidden -RedirectStandardOutput (Join-Path $env:MATRIX_OUT "runner_console.log") -RedirectStandardError (Join-Path $env:MATRIX_OUT "runner_console.err.log") -PassThru
L "matrix pid=$($p.Id) started"
Set-Content -Path (Join-Path $outRoot "matrix_18r21_active.txt") -Value $env:MATRIX_OUT
L "SWITCH_DONE"

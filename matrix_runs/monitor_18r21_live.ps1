$run = "C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r21_20260719_023216"
$out = "C:\Users\zhang\grok-regkit\matrix_runs\monitor_18r21_live.log"
for ($i=0; $i -lt 120; $i++) {
  $ts = Get-Date -Format "HH:mm:ss"
  $line = "[$ts] "
  try {
    $st = (Invoke-WebRequest "http://127.0.0.1:8092/api/status" -UseBasicParsing -TimeoutSec 5).Content | ConvertFrom-Json
    $line += "run=$($st.running) s=$($st.success) f=$($st.fail) p=$($st.pending_sso) phase=$($st.phase) "
  } catch { $line += "st_err " }
  if (Test-Path "$run\runner.log") { $line += "last=" + (Get-Content "$run\runner.log" -Tail 1) + " " }
  if (Test-Path "$run\summary.jsonl") { $line += "sumN=" + (Get-Content "$run\summary.jsonl" | Measure-Object).Count }
  Add-Content $out $line -Encoding UTF8
  $alive = Get-CimInstance Win32_Process -EA SilentlyContinue | Where-Object { $_.CommandLine -match "matrix_cross_run.py" }
  if (-not $alive -and $i -gt 3) { Add-Content $out "[$ts] matrix done"; break }
  Start-Sleep 30
}

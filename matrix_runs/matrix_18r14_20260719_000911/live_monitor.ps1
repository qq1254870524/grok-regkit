$out = "C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r14_20260719_000911\live_monitor.txt"
$end = (Get-Date).AddMinutes(40)
while ((Get-Date) -lt $end) {
  $ts = Get-Date -Format "HH:mm:ss"
  try {
    $st = Invoke-RestMethod -Uri "http://127.0.0.1:8092/api/status" -TimeoutSec 5
    $line = "$ts running=$($st.running) s=$($st.success) f=$($st.fail) p=$($st.pending_sso) kind=$($st.job_kind)"
  } catch { $line = "$ts status_err=$_" }
  $sum = ""
  $sf = "C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r14_20260719_000911\summary.jsonl"
  if (Test-Path $sf) {
    $n = (Get-Content $sf | Measure-Object).Count
    $last = Get-Content $sf -Tail 1 -ErrorAction SilentlyContinue
    $sum = " summary_n=$n last=$last"
  }
  $rl = "C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r14_20260719_000911\runner.log"
  $rt = if (Test-Path $rl) { (Get-Content $rl -Tail 1) } else { "" }
  Add-Content -Path $out -Value ($line + $sum + " runner=$rt") -Encoding utf8
  if (-not $st.running -and $n -ge 1) {
    # keep monitoring while matrix runner continues next cells
  }
  # stop if runner process gone and not running
  $rp = Get-Process -Id 159064 -ErrorAction SilentlyContinue
  if (-not $rp -and -not $st.running) { Add-Content $out "$ts MATRIX_RUNNER_EXIT"; break }
  Start-Sleep -Seconds 25
}

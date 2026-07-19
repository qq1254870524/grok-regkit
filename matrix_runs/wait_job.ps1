$out = "C:\Users\zhang\grok-regkit\matrix_runs\live_status_18r21.txt"
$deadline = (Get-Date).AddMinutes(4)
while ((Get-Date) -lt $deadline) {
  try {
    $st = Invoke-RestMethod "http://127.0.0.1:8092/api/status" -TimeoutSec 5
    $line = "$(Get-Date -Format o) run=$($st.running) s=$($st.success) f=$($st.fail) p=$($st.pending_sso) fin=$($st.finished_at)"
    Add-Content -Path $out -Value $line
    if (-not $st.running) { Add-Content -Path $out -Value "JOB_DONE"; break }
  } catch { Add-Content -Path $out -Value "err $_" }
  Start-Sleep -Seconds 15
}

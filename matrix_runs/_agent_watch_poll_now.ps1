$root="C:\Users\zhang\grok-regkit"
$out="$root\matrix_runs\matrix_18r29_20260719_070041"
$log="$root\matrix_runs\_agent_finish_poll.log"
for ($i=0; $i -lt 120; $i++) {
  $ts = Get-Date -Format "HH:mm:ss"
  $board = if (Test-Path "$root\matrix_runs\_progress_board_18r29.txt") { Get-Content "$root\matrix_runs\_progress_board_18r29.txt" -Raw } else { "" }
  $tail = (Get-Content "$root\matrix_runs\matrix_18r29_runner_console.log" -Tail 3) -join " | "
  $rep = Test-Path "$out\REPORT.md"
  $zip = Test-Path "$root\packages\stable-2026-07-19-matrix-singlethread-18r29.zip"
  $flag = Test-Path "$root\matrix_runs\_agent_matrix_done.flag"
  $web = ""
  try { $web = (Invoke-WebRequest http://127.0.0.1:8092/api/status -UseBasicParsing -TimeoutSec 3).Content } catch { $web = $_.Exception.Message }
  $line = "[$ts] report=$rep zip=$zip flag=$flag | $tail"
  Add-Content -Path $log -Value $line
  Add-Content -Path $log -Value "  board_direct=$((($board -split "`n") | Where-Object { $_ -match 'pending_sso_recovery__direct' }) -join '')"
  Add-Content -Path $log -Value "  web=$web"
  if ($rep -and $zip -and $flag) { Add-Content -Path $log -Value "[$ts] ALL DONE"; break }
  if ($rep -and -not $zip) { Add-Content -Path $log -Value "[$ts] REPORT ready, waiting publish..." }
  Start-Sleep -Seconds 45
}

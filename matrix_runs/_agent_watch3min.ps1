$deadline = (Get-Date).AddMinutes(3)
$log = "C:\Users\zhang\grok-regkit\matrix_runs\_watch_18r29_agent2.txt"
while ((Get-Date) -lt $deadline) {
  $ts = Get-Date -Format o
  $st = ""
  try { $st = (Invoke-WebRequest -Uri "http://127.0.0.1:8092/api/status" -TimeoutSec 3 -UseBasicParsing).Content } catch { $st = $_.Exception.Message }
  $tail = (Get-Content "C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r29_runner_console.log" -Tail 3 -ErrorAction SilentlyContinue) -join " | "
  Add-Content $log ("$ts | $st | $tail")
  if (Test-Path "C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r29_20260719_070041\REPORT.md") { Add-Content $log "REPORT_READY"; break }
  Start-Sleep -Seconds 30
}
Get-Content "C:\Users\zhang\grok-regkit\matrix_runs\_progress_board_18r29.txt" -ErrorAction SilentlyContinue | Set-Content "C:\Users\zhang\grok-regkit\matrix_runs\_agent_board_snap2.txt" -Encoding utf8
(Get-Content "C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r29_runner_console.log" -Tail 25 -ErrorAction SilentlyContinue) | Set-Content "C:\Users\zhang\grok-regkit\matrix_runs\_agent_console_snap2.txt" -Encoding utf8
try { (Invoke-WebRequest "http://127.0.0.1:8092/api/status" -TimeoutSec 3 -UseBasicParsing).Content | Set-Content "C:\Users\zhang\grok-regkit\matrix_runs\_agent_status_snap2.txt" -Encoding utf8 } catch { $_.Exception.Message | Set-Content "C:\Users\zhang\grok-regkit\matrix_runs\_agent_status_snap2.txt" }

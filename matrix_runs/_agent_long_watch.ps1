$ErrorActionPreference = "SilentlyContinue"
$root = "C:\Users\zhang\grok-regkit"
$out = Join-Path $root "matrix_runs\matrix_18r29_20260719_070041"
$snap = Join-Path $root "matrix_runs\_agent_long_snap.txt"
$log = Join-Path $root "matrix_runs\_agent_long_watch.log"
$deadline = (Get-Date).AddMinutes(20)
function Write-Snap($msg) {
  $ts = Get-Date -Format o
  Add-Content $log "$ts $msg"
  $board = Get-Content (Join-Path $root "matrix_runs\_progress_board_18r29.txt")
  $console = (Get-Content (Join-Path $root "matrix_runs\matrix_18r29_runner_console.log") -Tail 8) -join "`n"
  $st = ""
  try { $st = (Invoke-WebRequest "http://127.0.0.1:8092/api/status" -TimeoutSec 3 -UseBasicParsing).Content } catch { $st = $_.Exception.Message }
  $sum = ""
  if (Test-Path (Join-Path $out "summary.jsonl")) { $sum = (Get-Content (Join-Path $out "summary.jsonl") -Tail 3) -join "`n" }
  $report = Test-Path (Join-Path $out "REPORT.md")
  $mtx = Get-Process -Id 58728,156116 -ErrorAction SilentlyContinue
  $body = @(
    "ts=$ts report=$report matrix_procs=$($mtx.Count)",
    "STATUS=$st",
    "BOARD:",
    ($board -join "`n"),
    "CONSOLE:",
    $console,
    "SUMMARY_TAIL:",
    $sum
  ) -join "`n"
  Set-Content -Path $snap -Value $body -Encoding utf8
  if ($report) { Add-Content $log "REPORT_READY"; return $true }
  return $false
}
[void](Write-Snap "start")
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Seconds 45
  if (Write-Snap "tick") { break }
  # stall detect: running>10min same started_at
  try {
    $j = (Invoke-WebRequest "http://127.0.0.1:8092/api/status" -TimeoutSec 3 -UseBasicParsing).Content | ConvertFrom-Json
    if ($j.running -and $j.started_at) {
      $age = [double]((Get-Date).ToUniversalTime() - [datetime]'1970-01-01').TotalSeconds - [double]$j.started_at
      # started_at may be local weird epoch; skip complex
    }
  } catch {}
}
[void](Write-Snap "end")

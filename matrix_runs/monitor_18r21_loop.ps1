$m = "C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r21_20260719_023216"
$out = "C:\Users\zhang\grok-regkit\matrix_runs\live_monitor_18r21.txt"
$end = (Get-Date).AddMinutes(12)
while ((Get-Date) -lt $end) {
  $lines = @()
  $lines += "=== $(Get-Date -Format o) ==="
  if (Test-Path (Join-Path $m "runner.log")) {
    $lines += "--- runner tail ---"
    $lines += (Get-Content (Join-Path $m "runner.log") -Tail 20)
  }
  if (Test-Path (Join-Path $m "summary.jsonl")) {
    $lines += "--- summary count ---"
    $sc = @(Get-Content (Join-Path $m "summary.jsonl")).Count
    $lines += "rows=$sc"
    $lines += (Get-Content (Join-Path $m "summary.jsonl") -Tail 8)
  }
  try {
    $s = Invoke-RestMethod "http://127.0.0.1:8092/api/status" -TimeoutSec 5
    $lines += "status running=$($s.running) phase=$($s.phase) s=$($s.success) f=$($s.fail) p=$($s.pending_sso) last=$($s.last_event)"
  } catch { $lines += "status err" }
  $alive = (Get-Process -Id 154288 -ErrorAction SilentlyContinue) -ne $null
  $lines += "matrix_pid_154288_alive=$alive"
  $lines += "files:"
  $lines += ((Get-ChildItem $m -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | ForEach-Object { "$($_.LastWriteTime.ToString('HH:mm:ss')) $($_.Length) $($_.Name)" }) -join "`n")
  $text = $lines -join "`n"
  Set-Content -Path $out -Value $text -Encoding UTF8
  # also append history
  Add-Content -Path ($out + ".hist") -Value (($lines | Select-Object -First 3) -join " ")
  if (-not $alive) {
    Add-Content -Path $out -Value "MATRIX DONE"
    break
  }
  Start-Sleep -Seconds 45
}

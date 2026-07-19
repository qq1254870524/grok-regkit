$ErrorActionPreference = "Continue"
$root = "C:\Users\zhang\grok-regkit"
$out = "$root\matrix_runs\matrix_18r29_20260719_070041"
$log = "$root\matrix_runs\_agent_complete_to_release.log"
$tag = "stable-2026-07-19-matrix-singlethread-18r29"
function L($m){ $line = "[$(Get-Date -Format 'HH:mm:ss')] $m"; Add-Content $log $line; Write-Output $line }
L "complete_to_release watcher start"
for ($i=0; $i -lt 200; $i++) {
  $rep = Test-Path "$out\REPORT.md"
  $zip = Test-Path "$root\packages\$tag.zip"
  $flag = Test-Path "$root\matrix_runs\_agent_matrix_done.flag"
  $tail = ((Get-Content "$root\matrix_runs\matrix_18r29_runner_console.log" -Tail 2) -join " || ")
  $direct = ""
  if (Test-Path "$root\matrix_runs\_progress_board_18r29.txt") {
    $direct = ((Get-Content "$root\matrix_runs\_progress_board_18r29.txt") | Where-Object { $_ -match "pending_sso_recovery__direct" } | Select-Object -First 1)
  }
  $web = "n/a"
  try {
    $j = (Invoke-WebRequest http://127.0.0.1:8092/api/status -UseBasicParsing -TimeoutSec 4).Content | ConvertFrom-Json
    $web = "run=$($j.running) phase=$($j.phase) s=$($j.success) jobs=$($j.jobs_finished)/$($j.jobs_started)"
  } catch { $web = $_.Exception.Message }
  L "i=$i rep=$rep zip=$zip flag=$flag | $direct | $web | $tail"
  if ($rep -and -not $zip) {
    # ensure publish alive
    $pub = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match '_auto_publish_18r29' }
    if (-not $pub) {
      L "restart _auto_publish_18r29"
      Start-Process -FilePath "C:\Python312\python.exe" -ArgumentList "-B","tools\_auto_publish_18r29.py" -WorkingDirectory $root -WindowStyle Hidden
    }
  }
  if ($rep -and $zip) {
    if (-not $flag) {
      L "zip ready; run companions if needed"
      try { & "C:\Python312\python.exe" -B "$root\tools\_publish_companions_18r29.py" 2>&1 | Out-String | ForEach-Object { L $_ } } catch { L "companions err $_" }
      "DONE $(Get-Date -Format o)`n$direct`nzip=$zip" | Set-Content "$root\matrix_runs\_agent_matrix_done.flag" -Encoding UTF8
      L "wrote done flag"
    }
    L "ALL COMPLETE"
    break
  }
  Start-Sleep -Seconds 40
}
L "watcher exit"

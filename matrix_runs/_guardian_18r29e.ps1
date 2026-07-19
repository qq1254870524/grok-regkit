$root = "C:\Users\zhang\grok-regkit"
$out = "$root\matrix_runs\matrix_18r29_20260719_070041"
$log = "$root\matrix_runs\_guardian_18r29e.txt"
$end = (Get-Date).AddHours(5)
function W($m){ $line = "$(Get-Date -Format s) $m"; Add-Content $log $line; Write-Output $line }
while ((Get-Date) -lt $end) {
  $matrixAlive = [bool](Get-Process -Id 156116 -ErrorAction SilentlyContinue)
  $webOk = $false
  try { $null = Invoke-WebRequest http://127.0.0.1:8092/health -TimeoutSec 3 -UseBasicParsing; $webOk = $true } catch {}
  $report = Test-Path "$out\REPORT.md"
  if ($report) { W "REPORT_READY"; break }
  if (-not $webOk) {
    W "WEB_DOWN restart hidden"
    try { Start-Process powershell.exe -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',"$root\tools\start_web8092_hidden.ps1" -WindowStyle Hidden } catch { W "web restart fail $($_.Exception.Message)" }
    Start-Sleep 8
  }
  if (-not $matrixAlive) {
    W "MATRIX_DEAD - do not auto-restart full matrix (manual/guardian resume only)"
    # leave marker; auto_publish waits for REPORT only
  }
  # services that must stay up
  foreach ($pair in @(@(8010,"g2a"),@(8080,"s2a"),@(8317,"cpaapi"),@(8318,"cpagw"))) {
    $port=$pair[0]; $name=$pair[1]
    $ok=$false
    try { $null=Invoke-WebRequest "http://127.0.0.1:$port/" -TimeoutSec 2 -UseBasicParsing; $ok=$true } catch {
      try { $null=Invoke-WebRequest "http://127.0.0.1:$port/health" -TimeoutSec 2 -UseBasicParsing; $ok=$true } catch {}
    }
    if (-not $ok) { W "SERVICE_DOWN $name port=$port (not auto-killing register)" }
  }
  # progress line
  try {
    $s = (Invoke-WebRequest http://127.0.0.1:8092/api/status -TimeoutSec 4 -UseBasicParsing).Content | ConvertFrom-Json
    W "alive=$matrixAlive web=$webOk phase=$($s.phase) sess_ok=$($s.session_success) jobs=$($s.jobs_started)/$($s.jobs_finished)"
  } catch { W "status_err" }
  Start-Sleep -Seconds 120
}
W "guardian exit"

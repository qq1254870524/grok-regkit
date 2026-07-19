$ErrorActionPreference='Continue'
$log='C:\Users\zhang\grok-regkit\matrix_runs\monitor_18r21.log'
$outRoot='C:\Users\zhang\grok-regkit\matrix_runs'
function L($m){ Add-Content $log ("{0} {1}" -f (Get-Date -Format 'HH:mm:ss'), $m) }
L 'monitor start'
for ($i=0; $i -lt 400; $i++) {
  try {
    $st = Invoke-RestMethod 'http://127.0.0.1:8092/api/status' -TimeoutSec 5
    $mat = Get-ChildItem $outRoot -Directory | Where-Object { $_.Name -like 'matrix_18r19_20260719_022*' -or $_.Name -like 'matrix_18r21*' } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $runner=''
    $sumN=0
    if ($mat) {
      $rp = Join-Path $mat.FullName 'runner.log'
      $sp = Join-Path $mat.FullName 'summary.jsonl'
      if (Test-Path $rp) { $runner = (Get-Content $rp -Tail 1) }
      if (Test-Path $sp) { $sumN = (Get-Content $sp | Measure-Object -Line).Lines }
    }
    $alive = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'matrix_cross_run.py 2' } | Select-Object -First 1
    L ("i=$i run=$($st.running) s=$($st.success) p=$($st.pending_sso) f=$($st.fail) sumN=$sumN matrixPid=$($alive.ProcessId) last=$runner")
    if (-not $alive) {
      L 'MATRIX_PROCESS_GONE'
      # wait a bit for final summary
      Start-Sleep 5
      if ($mat -and (Test-Path (Join-Path $mat.FullName 'summary.jsonl'))) {
        L 'FINAL_SUMMARY'
        Get-Content (Join-Path $mat.FullName 'summary.jsonl') | ForEach-Object { L $_ }
        Get-Content (Join-Path $mat.FullName 'runner.log') | ForEach-Object { L $_ }
      }
      break
    }
  } catch { L "err $_" }
  Start-Sleep -Seconds 30
}
L 'monitor end'

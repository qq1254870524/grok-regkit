Start-Sleep -Seconds 150
$root='C:\Users\zhang\grok-regkit'
$out=Join-Path $root 'matrix_runs\matrix_18r29_20260719_070041'
$st=''
try{$st=(Invoke-WebRequest 'http://127.0.0.1:8092/api/status' -TimeoutSec 3 -UseBasicParsing).Content}catch{$st=$_.Exception.Message}
$body=@(
  "ts=$(Get-Date -Format o)",
  "STATUS=$st",
  'BOARD:',
  ((Get-Content (Join-Path $root 'matrix_runs\_progress_board_18r29.txt') -EA SilentlyContinue) -join "`n"),
  'CONSOLE_TAIL:',
  ((Get-Content (Join-Path $root 'matrix_runs\matrix_18r29_runner_console.log') -Tail 12 -EA SilentlyContinue) -join "`n"),
  'SUMMARY_TAIL:',
  ((Get-Content (Join-Path $out 'summary.jsonl') -Tail 5 -EA SilentlyContinue) -join "`n"),
  "REPORT=$(Test-Path (Join-Path $out 'REPORT.md'))",
  "MATRIX=$((Get-Process -Id 58728,156116 -EA SilentlyContinue | Measure-Object).Count)"
) -join "`n"
Set-Content (Join-Path $root 'matrix_runs\_agent_snap_150s.txt') $body -Encoding utf8

Start-Sleep -Seconds 180
$root='C:\Users\zhang\grok-regkit'
$out=Join-Path $root 'matrix_runs\matrix_18r29_20260719_070041'
$st=''; try{$st=(Invoke-WebRequest 'http://127.0.0.1:8092/api/status' -TimeoutSec 3 -UseBasicParsing).Content}catch{$st=$_.Exception.Message}
$paths=@(
 'C:\Users\zhang\grok-regkit-services',
 'C:\Users\zhang\sub2api-src',
 'C:\Users\zhang\grok-regkit-services1\grok2api1',
 'C:\Users\zhang\grok-regkit-services1'
) | ForEach-Object { if(Test-Path $_){"OK $_"} else {"MISS $_"} }
$body=@(
 "ts=$(Get-Date -Format o)",
 "STATUS=$st",
 'BOARD:',
 ((Get-Content (Join-Path $root 'matrix_runs\_progress_board_18r29.txt') -EA SilentlyContinue) -join "`n"),
 'CONSOLE:',
 ((Get-Content (Join-Path $root 'matrix_runs\matrix_18r29_runner_console.log') -Tail 15 -EA SilentlyContinue) -join "`n"),
 'SUMMARY:',
 ((Get-Content (Join-Path $out 'summary.jsonl') -Tail 6 -EA SilentlyContinue) -join "`n"),
 "REPORT=$(Test-Path (Join-Path $out 'REPORT.md'))",
 'COMPANIONS:',
 ($paths -join "`n"),
 'OUT_FILES:',
 ((Get-ChildItem $out -File | Sort-Object LastWriteTime -Descending | Select-Object -First 12 | ForEach-Object { "$($_.LastWriteTime.ToString('HH:mm:ss')) $($_.Name) $($_.Length)" }) -join "`n")
) -join "`n"
Set-Content (Join-Path $root 'matrix_runs\_agent_snap_180s.txt') $body -Encoding utf8

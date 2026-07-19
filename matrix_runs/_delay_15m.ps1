Start-Sleep -Seconds 900
Copy-Item 'C:\Users\zhang\grok-regkit\matrix_runs\_agent_py_snap.txt' 'C:\Users\zhang\grok-regkit\matrix_runs\_agent_delay_15m.txt' -Force -ErrorAction SilentlyContinue
& 'C:\Python312\python.exe' -B 'C:\Users\zhang\grok-regkit\matrix_runs\_recalc_board.py' | Out-File 'C:\Users\zhang\grok-regkit\matrix_runs\_agent_board_15m.txt' -Encoding utf8
try{(Invoke-WebRequest 'http://127.0.0.1:8092/api/status' -TimeoutSec 3 -UseBasicParsing).Content | Out-File 'C:\Users\zhang\grok-regkit\matrix_runs\_agent_status_15m.txt' -Encoding utf8}catch{.Exception.Message | Out-File 'C:\Users\zhang\grok-regkit\matrix_runs\_agent_status_15m.txt'}
Get-Content 'C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r29_runner_console.log' -Tail 20 | Out-File 'C:\Users\zhang\grok-regkit\matrix_runs\_agent_console_15m.txt' -Encoding utf8
if(Test-Path 'C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r29_20260719_070041\REPORT.md'){ 'REPORT' | Out-File 'C:\Users\zhang\grok-regkit\matrix_runs\_agent_report_flag.txt' }

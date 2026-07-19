Start-Sleep -Seconds 200
$out='C:\Users\zhang\grok-regkit\matrix_runs\_wait200.txt'
$lines=@((Get-Date -Format o))
try{$s=Invoke-RestMethod http://127.0.0.1:8092/api/status -TimeoutSec 5; $lines+="run=$($s.running) phase=$($s.phase) s=$($s.success) f=$($s.fail) p=$($s.pending_sso) last=$($s.last_event)"}catch{$lines+=$_.Exception.Message}
$lines+='---runner---'; $lines+=@(Get-Content 'C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r24_weak_20260719_033411\runner.log' -Tail 20 -EA SilentlyContinue)
$lines+='---done---'; $lines+= (Test-Path 'C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r24_weak_20260719_033411\DONE.txt')
if(Test-Path 'C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r24_weak_20260719_033411\DONE.txt'){$lines+=Get-Content 'C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r24_weak_20260719_033411\DONE.txt'}
$lines+='---procs---'; $lines+=@(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ?{$_.CommandLine -match 'matrix_rerun|post_matrix'} | %{ "$($_.ProcessId) $($_.CommandLine.Substring(0,[Math]::Min(100,$_.CommandLine.Length)))"})
$lines+='---post---'; $lines+=@(Get-Content 'C:\Users\zhang\grok-regkit\matrix_runs\_post_matrix_r25_release.log' -Tail 12 -EA SilentlyContinue)
$lines|Set-Content $out -Encoding UTF8

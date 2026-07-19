Start-Sleep -Seconds 240
$out='C:\Users\zhang\grok-regkit\matrix_runs\_wait_pending.txt'
$lines=@((Get-Date -Format o))
try{$s=Invoke-RestMethod http://127.0.0.1:8092/api/status -TimeoutSec 5; $lines+="run=$($s.running) phase=$($s.phase) job=$($s.job_kind) s=$($s.success) f=$($s.fail) p=$($s.pending_sso) last=$($s.last_event)"}catch{$lines+=$_.Exception.Message}
$lines+='---runner---'; $lines+=@(Get-Content 'C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r24_weak_20260719_033411\runner.log' -Tail 25 -EA SilentlyContinue)
$lines+='---done---'; $df='C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r24_weak_20260719_033411\DONE.txt'; $lines+= (Test-Path $df); if(Test-Path $df){$lines+=Get-Content $df}
$lines+='---procs---'; $lines+=@(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ?{$_.CommandLine -match 'matrix_rerun|post_matrix'} | %{ "$($_.ProcessId) $($_.CommandLine.Substring(0,[Math]::Min(110,$_.CommandLine.Length)))"})
$lines+='---post---'; $lines+=@(Get-Content 'C:\Users\zhang\grok-regkit\matrix_runs\_post_matrix_r25_release.log' -Tail 15 -EA SilentlyContinue)
$lines+='---files---'; $lines+=@(Get-ChildItem 'C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r24_weak_20260719_033411' | Sort LastWriteTime -Desc | Select -First 15 | %{ "$($_.LastWriteTime.ToString('HH:mm:ss')) $($_.Length) $($_.Name)" })
$lines|Set-Content $out -Encoding UTF8

$out='C:\Users\zhang\grok-regkit\matrix_runs\_agent_poll_18r29.txt'
'' | Set-Content $out
for($i=0;$i -lt 24;$i++){
  try {
    $s=Invoke-RestMethod 'http://127.0.0.1:8092/api/status' -TimeoutSec 4
    $ev = [string]$s.last_event
    if($ev.Length -gt 140){ $ev = $ev.Substring(0,140) }
    $line = "{0} phase={1} run={2} ok={3} fail={4} p={5} jobs={6}/{7} evt={8}" -f (Get-Date -Format 'HH:mm:ss'),$s.phase,$s.running,$s.session_success,$s.session_fail,$s.session_pending_sso,$s.jobs_started,$s.jobs_finished,$ev
  } catch { $line = "{0} API_ERR {1}" -f (Get-Date -Format 'HH:mm:ss'),$_ }
  Add-Content $out $line
  if($s -and -not $s.running){ Add-Content $out 'IDLE'; break }
  Start-Sleep -Seconds 12
}
# append console tail + file list
Add-Content $out '---CONSOLE---'
Get-Content C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r29_runner_console.log -Tail 12 | Add-Content $out
Add-Content $out '---FILES---'
Get-ChildItem C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r29_20260719_070041 -Filter 'browser__*' | Sort-Object LastWriteTime -Descending | Select-Object -First 6 | ForEach-Object { "$($_.Name) $($_.LastWriteTime) $($_.Length)" } | Add-Content $out

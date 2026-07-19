$ErrorActionPreference="Continue"
$out="C:\Users\zhang\grok-regkit\matrix_runs\_peer_18r28h_monitor.txt"
$tail="C:\Users\zhang\grok-regkit\matrix_runs\_peer_18r28h_live_tail.txt"
$rep="C:\Users\zhang\grok-regkit\matrix_runs\_peer_18r28h_report.txt"
function San([string]$t){ if($null -eq $t){return $t}; return ($t -replace 'mail_token=\{[^\}]*\}','mail_token={...}' -replace '("access_token"\s*:\s*")[^"]+','$1***' -replace '(token=)[A-Za-z0-9_\-\.=+/]{30,}','$1***' -replace "(password=')[^']+","password='***" -replace '(socks5h://)[^\s|]+','$1***' -replace '(code=)[A-Z0-9\-]{4,12}','$1***') }
function Lines{ try{ $r=Invoke-WebRequest -Uri 'http://127.0.0.1:8092/api/logs/snapshot?limit=150' -TimeoutSec 10 -UseBasicParsing; $j=$r.Content|ConvertFrom-Json; if($j.logs){return @($j.logs)}; if($j.lines){return @($j.lines)}; return @($r.Content -split "`n") } catch { return @("snap_err=$($_.Exception.Message)") } }
function St{ try{ Invoke-RestMethod -Uri 'http://127.0.0.1:8092/api/status' -TimeoutSec 5 } catch { $null } }
$start=Get-Date; $last=""; $hist=New-Object System.Collections.Generic.List[string]; $idle=0
"monitor_start=$(Get-Date -Format o)"|Set-Content $out -Encoding UTF8
while(((Get-Date)-$start).TotalMinutes -lt 30){
  $s=St; $L=@(Lines|%{San "$_"}); $L|Set-Content $tail -Encoding UTF8
  $st=if($s){"run=$($s.running) phase=$($s.phase) s=$($s.success)/$($s.target) f=$($s.fail) ps=$($s.pending_sso) js=$($s.jobs_started) jf=$($s.jobs_finished) last=$($s.last_event)"}else{"status_null"}
  $t=$L -join "`n"
  $bad=($t -match 'submit boost') -or ($t -match 'auth-error-retry') -or (($t -match 're-fill submit') -and ($t -match 'page_err=auth_error') -and ($t -notmatch 'NO second login'))
  $row="[$(Get-Date -Format 'HH:mm:ss')] $st bad_second=$bad one=$(($t -match 'ONE login submit')) block=$(($t -match 'login_submit_done=1')) imm=$(($t -match 'IMMEDIATE re-register')) aolmiss=$(($t -match 'AOL missing password')) ok=$(($t -match 'OK immediate SSO'))"
  if($row -ne $last){$hist.Add($row); $last=$row; $idle=0} else {$idle++}
  @("updated=$(Get-Date -Format o)";$row;"----";$hist.ToArray()[-40..-1])|Set-Content $out -Encoding UTF8
  if($s -and -not $s.running -and $s.phase -eq 'finished' -and $idle -ge 2){break}
  Start-Sleep -Seconds 5
}
$s=St; $L=@(Lines|%{San "$_"}); $L|Set-Content $tail -Encoding UTF8; $t=$L -join "`n"
$keys=$L|?{$_ -match 'ONE login|login_submit_done|block_refill|NO second|IMMEDIATE|page_err|submit boost|re-fill submit|auth-error-retry|OK immediate|get_oai_code|AOL missing|poll_timeout|actual_send|re-register result|pending_sso 恢复结束|当前统计|start recover|CreateEmail done|code ok|VerifyEmail|early_no'}
$repTxt=@(
"# peer 18r28h report"
"finished_at=$(Get-Date -Format o)"
"status=$(if($s){$s|ConvertTo-Json -Compress -Depth 5}else{'null'})"
"bad_submit_boost=$(($t -match 'submit boost'))"
"one_login_keyword=$(($t -match 'ONE login submit'))"
"login_submit_done=$(($t -match 'login_submit_done=1'))"
"no_second=$(($t -match 'NO second login click'))"
"ok_sso=$(($t -match 'OK immediate SSO'))"
"aol_missing=$(($t -match 'AOL missing password'))"
""
"## key_lines"
)+@($keys|Select-Object -Last 100)
$repTxt|Set-Content $rep -Encoding UTF8
"DONE s=$($s.success) f=$($s.fail)"|Add-Content $out -Encoding UTF8

$ErrorActionPreference = "Continue"
$out = "C:\Users\zhang\grok-regkit\matrix_runs\_peer_18r28g_monitor.txt"
$tailf = "C:\Users\zhang\grok-regkit\matrix_runs\_peer_18r28g_live_tail.txt"
$report = "C:\Users\zhang\grok-regkit\matrix_runs\_peer_18r28g_report.txt"
function Sanitize([string]$t) {
  if ($null -eq $t) { return $t }
  return ($t -replace "mail_token=\{[^\}]*\}","mail_token={...}" `
    -replace '("access_token"\s*:\s*")[^"]+','$1***' `
    -replace '("refresh_token"\s*:\s*")[^"]+','$1***' `
    -replace "(token=)[A-Za-z0-9_\-\.=+/]{30,}","`$1***" `
    -replace "(password=')[^']+","password='***" `
    -replace "(b64:)[A-Za-z0-9+/=]{20,}","`$1***" `
    -replace "(socks5h://)[^\s|]+","`$1***")
}
function Get-Lines {
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8092/api/logs/snapshot?limit=150" -TimeoutSec 10 -UseBasicParsing
    $txt = $r.Content
    try {
      $j = $txt | ConvertFrom-Json
      if ($j.logs) { return @($j.logs) }
      if ($j.lines) { return @($j.lines) }
    } catch {}
    return @($txt -split "`n")
  } catch { return @("snap_err=$($_.Exception.Message)") }
}
function Get-St {
  try { return Invoke-RestMethod -Uri "http://127.0.0.1:8092/api/status" -TimeoutSec 5 } catch { return $null }
}
$start = Get-Date
$idle = 0
$lastSig = ""
$hist = New-Object System.Collections.Generic.List[string]
"monitor_start=$(Get-Date -Format o)" | Set-Content $out -Encoding UTF8
while (((Get-Date) - $start).TotalMinutes -lt 25) {
  $s = Get-St
  $lines = @(Get-Lines | ForEach-Object { Sanitize ("$_") })
  $lines | Set-Content $tailf -Encoding UTF8
  $st = if ($s) { "run=$($s.running) phase=$($s.phase) s=$($s.success)/$($s.target) f=$($s.fail) ps=$($s.pending_sso) js=$($s.jobs_started) jf=$($s.jobs_finished) last=$($s.last_event)" } else { "status_null" }
  $text = $lines -join "`n"
  $checks = [ordered]@{
    no_second_login = ($text -match "NO second login click")
    immediate_rereg = ($text -match "IMMEDIATE re-register")
    auth_error = ($text -match "page_err=auth_error")
    bad_password = ($text -match "page_err=bad_password")
    refill_submit_after_err = ($text -match "re-fill submit" -and $text -match "page_err=")
    aol_missing = ($text -match "AOL missing password")
    route_outlook = ($text -match "get_oai_code route" -and $text -match "provider=outlook")
    ok_sso = ($text -match "OK immediate SSO")
    stop_web = ($text -match "stop requested from web")
    job_end = ($text -match "pending_sso 恢复结束" -or $text -match "web job thread finished")
  }
  # Detect BAD pattern: after auth_error, another click login without IMMEDIATE
  $bad_second = $false
  for ($i=0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match "page_err=auth_error" -and $lines[$i] -notmatch "IMMEDIATE re-register") {
      # look ahead 8 lines for re-click without IMMEDIATE nearby
      $win = ($lines[$i..([Math]::Min($i+8,$lines.Count-1))] -join "`n")
      if ($win -match "re-fill submit|auth-error-retry|click after turnstile" -and $win -notmatch "NO second login click|IMMEDIATE re-register|STOP further sign-in") {
        $bad_second = $true
      }
    }
  }
  $sig = "$st|$($checks.Values -join ',')|bad=$bad_second"
  $row = "[$(Get-Date -Format 'HH:mm:ss')] $st bad_second_login=$bad_second checks=$($checks | ConvertTo-Json -Compress)"
  if ($sig -ne $lastSig) {
    $hist.Add($row)
    $lastSig = $sig
    $idle = 0
  } else { $idle++ }
  @(
    "updated=$(Get-Date -Format o)"
    $row
    "---- recent unique ----"
  ) + $hist.ToArray()[-30..-1] | Set-Content $out -Encoding UTF8

  if ($s -and -not $s.running -and ($s.phase -eq "finished" -or $s.jobs_finished -ge 1)) {
    if ($idle -ge 2) { break }
  }
  Start-Sleep -Seconds 5
}
$s = Get-St
$lines = @(Get-Lines | ForEach-Object { Sanitize ("$_") })
$lines | Set-Content $tailf -Encoding UTF8
$all = $lines -join "`n"
# extract key evidence lines
$keys = $lines | Where-Object {
  $_ -match "NO second login|IMMEDIATE re-register|page_err=|AOL missing|get_oai_code route|OK immediate SSO|re-register result|pending_sso 恢复结束|stop requested|actual_send|poll_timeout|CreateEmail skip|login failed|re-fill submit|auth-error-retry|success|fail"
}
$rep = @(
  "# peer 18r28g monitor report"
  "finished_at=$(Get-Date -Format o)"
  "status=$(if($s){$s|ConvertTo-Json -Compress -Depth 5}else{'null'})"
  ""
  "## verdict_checks"
  "- NO second login click present: $([bool]($all -match 'NO second login click'))"
  "- IMMEDIATE re-register present: $([bool]($all -match 'IMMEDIATE re-register'))"
  "- AOL missing password: $([bool]($all -match 'AOL missing password'))"
  "- OK immediate SSO: $([bool]($all -match 'OK immediate SSO'))"
  "- stop requested mid-job: $([bool]($all -match 'stop requested from web'))"
  "- re-fill submit lines: $(([regex]::Matches($all,'re-fill submit')).Count)"
  ""
  "## key_lines"
) + @($keys | Select-Object -Last 80)
$rep | Set-Content $report -Encoding UTF8
"DONE report=$report status_run=$($s.running) s=$($s.success) f=$($s.fail)" | Add-Content $out -Encoding UTF8

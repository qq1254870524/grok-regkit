$ErrorActionPreference = "Continue"
$out = "C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r24_weak_20260719_033411"
$pulse = "C:\Users\zhang\grok-regkit\matrix_runs\_live_pulse_r24b.txt"
$report = "C:\Users\zhang\grok-regkit\matrix_runs\_peer_weak_done_report.txt"
$progress = "C:\Users\zhang\grok-regkit\matrix_runs\_peer_weak_monitor_progress.txt"
$pidWeak = 156952
$known = @("pending_sso","early_no_new_mail","profile_fill_fail","sso_timeout","email_login_fail","empty_log","success","stop_requested")
function Write-Prog($msg) {
  $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg
  Add-Content -Path $progress -Value $line -Encoding UTF8
}
function Get-StatusText {
  try {
    $s = Invoke-RestMethod "http://127.0.0.1:8092/api/status" -TimeoutSec 5
    return @{ ok=$true; running=[bool]$s.running; phase=[string]$s.phase; text=("running={0} phase={1} s={2} p={3} f={4}" -f $s.running,$s.phase,$s.success,$s.pending_sso,$s.fail) }
  } catch {
    return @{ ok=$false; running=$false; phase=""; text="status_err" }
  }
}
function Get-ClassSummary {
  if (-not (Test-Path "$out\summary.jsonl")) { return "no_summary" }
  $map = @{}
  Get-Content "$out\summary.jsonl" | ForEach-Object {
    try {
      $j = $_ | ConvertFrom-Json
      $k = "{0}|r{1}" -f $j.cell, $j.round
      $map[$k] = [string]$j.class
    } catch {}
  }
  $g = $map.Values | Group-Object | Sort-Object Name | ForEach-Object { "{0}={1}" -f $_.Name, $_.Count }
  return ($g -join ", ")
}
"" | Set-Content -Path $progress -Encoding UTF8
Write-Prog "monitor start weak_pid=$pidWeak"
$lastClasses = ""
$deadStable = 0
$lastRunLen = -1
$lastRunWrite = Get-Date
for ($i = 0; $i -lt 360; $i++) {
  Start-Sleep -Seconds 20
  $alive = [bool](Get-Process -Id $pidWeak -ErrorAction SilentlyContinue)
  $st = Get-StatusText
  $classes = Get-ClassSummary
  $runTail = ""
  $runLen = 0
  if (Test-Path "$out\runner.log") {
    $ri = Get-Item "$out\runner.log"
    $runLen = $ri.Length
    if ($ri.LastWriteTime -gt $lastRunWrite) { $lastRunWrite = $ri.LastWriteTime }
    $runTail = ((Get-Content "$out\runner.log" -Tail 4) -join " || ")
  }
  if ($classes -ne $lastClasses) {
    Write-Prog ("CLASS_UPDATE unique_dedupe_classes: {0}" -f $classes)
    $lastClasses = $classes
  }
  if (($i % 9) -eq 0) {
    Write-Prog ("tick weak={0} {1} classes={2}" -f ($(if($alive){"ALIVE"}else{"DEAD"})), $st.text, $classes)
    if ($runTail) { Write-Prog ("runner: {0}" -f $runTail) }
  }
  $doneLine = $false
  if (Test-Path "$out\runner.log") {
    $txt = Get-Content "$out\runner.log" -Raw -ErrorAction SilentlyContinue
    if ($txt -match "DONE|ALL DONE|weak done|finished all|matrix complete") { $doneLine = $true }
  }
  if (-not $alive) {
    $stableNoRun = (-not $st.running)
    $noNew = ($runLen -eq $lastRunLen)
    $age = ((Get-Date) - $lastRunWrite).TotalSeconds
    if ($doneLine -or ($stableNoRun -and $noNew -and $age -gt 30)) {
      $deadStable++
    } else {
      $deadStable = 0
    }
    Write-Prog ("weak DEAD check deadStable={0}/2 doneLine={1} running={2} noNew={3} age={4:n0}s" -f $deadStable, $doneLine, $st.running, $noNew, $age)
    if ($deadStable -ge 2) { break }
  }
  $lastRunLen = $runLen
}
# Build report
$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("weak_matrix_done_report") | Out-Null
$lines.Add(("generated={0}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))) | Out-Null
$lines.Add(("out={0}" -f $out)) | Out-Null
$aliveFinal = [bool](Get-Process -Id $pidWeak -ErrorAction SilentlyContinue)
$lines.Add(("weak_pid=156952 alive={0}" -f $aliveFinal)) | Out-Null
$lines.Add("post_pipeline_note=do_not_interfere (expected auto package/push)") | Out-Null
if (Test-Path "$out\runner.log") {
  $lines.Add("--- runner tail ---") | Out-Null
  Get-Content "$out\runner.log" -Tail 40 | ForEach-Object { $lines.Add($_) | Out-Null }
}
$map = [ordered]@{}
if (Test-Path "$out\summary.jsonl") {
  Get-Content "$out\summary.jsonl" | ForEach-Object {
    try {
      $j = $_ | ConvertFrom-Json
      $k = "{0}|{1}" -f $j.cell, $j.round
      $map[$k] = $j
    } catch {}
  }
}
$lines.Add("--- per cell+round (deduped last) ---") | Out-Null
$okN = 0; $failN = 0
$byClass = @{}
$byCell = @{}
foreach ($k in $map.Keys) {
  $j = $map[$k]
  $cls = [string]$j.class
  if (-not $cls) { $cls = "(empty)" }
  if ($j.ok) { $okN++ } else { $failN++ }
  if (-not $byClass.ContainsKey($cls)) { $byClass[$cls] = 0 }
  $byClass[$cls]++
  $cell = [string]$j.cell
  if (-not $byCell.ContainsKey($cell)) {
    $byCell[$cell] = @{ ok = 0; fail = 0; classes = @{} }
  }
  if ($j.ok) { $byCell[$cell].ok++ } else { $byCell[$cell].fail++ }
  if (-not $byCell[$cell].classes.ContainsKey($cls)) { $byCell[$cell].classes[$cls] = 0 }
  $byCell[$cell].classes[$cls]++
  $lines.Add(("{0} r{1} class={2} ok={3} s={4} p={5} f={6} t={7}s" -f $j.cell, $j.round, $cls, $j.ok, $j.success, $j.pending_sso, $j.fail, $j.elapsed_s)) | Out-Null
}
$lines.Add("--- totals deduped ---") | Out-Null
$lines.Add(("rounds={0} success_ok={1} fail_or_pending={2}" -f $map.Count, $okN, $failN)) | Out-Null
$lines.Add("--- class counts ---") | Out-Null
foreach ($c in ($byClass.Keys | Sort-Object)) { $lines.Add(("{0}={1}" -f $c, $byClass[$c])) | Out-Null }
$lines.Add("--- per cell success/fail ---") | Out-Null
foreach ($c in ($byCell.Keys | Sort-Object)) {
  $info = $byCell[$c]
  $cs = ($info.classes.GetEnumerator() | ForEach-Object { "{0}={1}" -f $_.Key, $_.Value }) -join ", "
  $lines.Add(("{0} ok={1} fail={2} [{3}]" -f $c, $info.ok, $info.fail, $cs)) | Out-Null
}
$new = @()
foreach ($c in $byClass.Keys) {
  if ($known -notcontains $c) { $new += $c }
}
$lines.Add("--- NEW failure modes ---") | Out-Null
if ($new.Count) { $lines.Add(($new -join ", ")) | Out-Null } else { $lines.Add("(none beyond known set)") | Out-Null }
$st = Get-StatusText
$lines.Add("--- 8092 final ---") | Out-Null
$lines.Add($st.text) | Out-Null
if (Test-Path $pulse) {
  $lines.Add("--- pulse tail ---") | Out-Null
  Get-Content $pulse -Tail 20 | ForEach-Object { $lines.Add($_) | Out-Null }
}
$lines | Set-Content -Path $report -Encoding UTF8
Write-Prog ("WROTE report alive={0} rounds={1}" -f $aliveFinal, $map.Count)

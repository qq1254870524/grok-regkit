$outDir = "C:\Users\zhang\grok-regkit\matrix_runs"
$summary = "$outDir\matrix_18r29_20260719_070041\summary.jsonl"
$end = (Get-Date).AddHours(5)
while ((Get-Date) -lt $end) {
  try {
    $st = $null
    try { $st = (Invoke-WebRequest -Uri http://127.0.0.1:8092/api/status -TimeoutSec 4 -UseBasicParsing).Content | ConvertFrom-Json } catch {}
    $alive = [bool](Get-Process -Id 156116 -ErrorAction SilentlyContinue)
    $classes = @{}
    $cells = @{}
    $rows = 0
    if (Test-Path $summary) {
      Get-Content $summary | ForEach-Object {
        $j = $_ | ConvertFrom-Json
        $rows++
        $c = if ($j.class) { $j.class } else { 'unknown' }
        if (-not $classes.ContainsKey($c)) { $classes[$c]=0 }; $classes[$c]++
        $key = $j.cell
        if (-not $cells.ContainsKey($key)) { $cells[$key] = @{rounds=0; ok=0; classes=@{}} }
        $cells[$key].rounds++
        if ($j.ok) { $cells[$key].ok++ }
        if (-not $cells[$key].classes.ContainsKey($c)) { $cells[$key].classes[$c]=0 }
        $cells[$key].classes[$c]++
      }
    }
    $obj = [ordered]@{
      ts=(Get-Date).ToString('s'); running=if($st){[bool]$st.running}else{$null}; phase=if($st){$st.phase}else{$null}
      event=if($st){$st.last_event}else{$null}; session_success=if($st){$st.session_success}else{$null}
      session_pending=if($st){$st.session_pending_sso}else{$null}; matrix_alive=$alive; summary_rows=$rows
      classes=$classes; cells=$cells; report_ready=(Test-Path "$outDir\matrix_18r29_20260719_070041\REPORT.md")
    }
    $obj | ConvertTo-Json -Depth 8 | Set-Content "$outDir\_progress_18r29.json" -Encoding UTF8
    $line = "{0} phase={1} run={2} ok={3} p={4} rows={5} alive={6} evt={7}" -f (Get-Date -Format 'HH:mm:ss'), $obj.phase, $obj.running, $obj.session_success, $obj.session_pending, $rows, $alive, $obj.event
    Add-Content "$outDir\_agent_poll_18r29.txt" $line
    if ($obj.report_ready) { Add-Content "$outDir\_agent_poll_18r29.txt" "REPORT_READY"; break }
    if (-not $alive) { Add-Content "$outDir\_agent_poll_18r29.txt" "MATRIX_DEAD"; Start-Sleep 30; continue }
  } catch {
    Add-Content "$outDir\_agent_poll_18r29.txt" ("{0} poll_err={1}" -f (Get-Date -Format 'HH:mm:ss'), $_.Exception.Message)
  }
  Start-Sleep -Seconds 45
}

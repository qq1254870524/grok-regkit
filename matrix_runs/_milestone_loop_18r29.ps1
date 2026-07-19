$root = "C:\Users\zhang\grok-regkit"
$summary = "$root\matrix_runs\matrix_18r29_20260719_070041\summary.jsonl"
$mile = "$root\matrix_runs\_milestone_18r29.txt"
$end = (Get-Date).AddHours(4)
$last = ""
while ((Get-Date) -lt $end) {
  try {
    $cells = @{}
    if (Test-Path $summary) {
      Get-Content $summary | ForEach-Object {
        $j = $_ | ConvertFrom-Json
        $k = $j.cell
        if (-not $cells.ContainsKey($k)) { $cells[$k] = @{r=0;ok=0} }
        # rough count unique max round with ok preference not exact
        if ([int]$j.round -gt $cells[$k].r) { $cells[$k].r = [int]$j.round }
        if ($j.ok) { $cells[$k].ok++ }
      }
    }
    $snap = ($cells.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Key)=$($_.Value.r)/ok~$($_.Value.ok)" }) -join " | "
    $st = ""
    try { $st = (Invoke-WebRequest http://127.0.0.1:8092/api/status -TimeoutSec 4 -UseBasicParsing).Content } catch { $st = $_.Exception.Message }
    $line = "$(Get-Date -Format s) matrix=$(Get-Process -Id 156116 -EA SilentlyContinue | ForEach-Object {'alive'}) report=$(Test-Path $root\matrix_runs\matrix_18r29_20260719_070041\REPORT.md) $snap"
    if ($snap -ne $last) {
      Add-Content $mile $line
      $last = $snap
    }
    Add-Content "$root\matrix_runs\_agent_poll_18r29.txt" $line
    if (Test-Path $root\matrix_runs\matrix_18r29_20260719_070041\REPORT.md) { Add-Content $mile "REPORT_READY $(Get-Date -Format s)"; break }
  } catch { Add-Content $mile "$(Get-Date -Format s) err=$($_.Exception.Message)" }
  Start-Sleep -Seconds 90
}

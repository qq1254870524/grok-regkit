$out = "C:\Users\zhang\grok-regkit\matrix_runs\_sample_18r35.txt"
1..200 | ForEach-Object {
  try {
    $s = Invoke-RestMethod http://127.0.0.1:8092/api/status -TimeoutSec 8
    $line = "{0} ok={1} fail={2} pend={3} skip={4} phase={5} running={6} | {7}" -f (Get-Date -Format "HH:mm:ss"), $s.success, $s.fail, $s.pending_sso, $s.skipped, $s.phase, $s.running, (($s.last_event)+"").Substring(0, [Math]::Min(160, (($s.last_event)+"").Length))
  } catch { $line = "{0} ERR {1}" -f (Get-Date -Format "HH:mm:ss"), $_.Exception.Message }
  Add-Content -Path $out -Value $line -Encoding utf8
  # also check matrix jsonl
  $jl = "C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r30_20260720_003737.jsonl"
  if (Test-Path $jl) { Add-Content -Path $out -Value ("JSONL " + (Get-Content $jl -Raw).Substring(0, [Math]::Min(500, (Get-Content $jl -Raw).Length))) }
  if (Test-Path "C:\Users\zhang\grok-regkit\matrix_runs\_matrix_18r35_DONE.flag") { Add-Content $out "DONE FLAG"; break }
  Start-Sleep -Seconds 60
}

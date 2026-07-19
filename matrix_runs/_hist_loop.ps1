$base='C:\Users\zhang\grok-regkit\matrix_runs'
for($i=1; $i -le 40; $i++){
  Start-Sleep -Seconds 240
  $ts=Get-Date -Format 'HHmmss'
  Copy-Item "$base\_monitor_18r29.txt" "$base\_hist_$ts.txt" -Force -EA SilentlyContinue
  if(Test-Path "$base\_18r29_READY.txt"){ Copy-Item "$base\_18r29_READY.txt" "$base\_READY_COPY.txt" -Force; break }
  if(Test-Path "$base\matrix_18r29_20260719_070041\REPORT.md"){ break }
}

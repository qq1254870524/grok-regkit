$out = "C:\Users\zhang\grok-regkit\matrix_runs\_pending_watch.txt"
function W($m){ Add-Content -Path $out -Value ("[{0}] {1}" -f (Get-Date -Format o), $m) -Encoding UTF8 }
"" | Set-Content $out -Encoding UTF8
for($i=0; $i -lt 40; $i++){
  try {
    $st = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8092/api/status -TimeoutSec 5).Content
    W "status $st"
    $j = $st | ConvertFrom-Json
    if(-not $j.running){
      try {
        $logs = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8092/api/logs/snapshot?limit=300" -TimeoutSec 10).Content
        [IO.File]::WriteAllText("C:\Users\zhang\grok-regkit\matrix_runs\_pending_ts2.json", $logs, [Text.UTF8Encoding]::new($false))
        W "saved logs"
      } catch { W "logerr $($_.Exception.Message)" }
      W "DONE"
      break
    }
  } catch { W "err $($_.Exception.Message)" }
  Start-Sleep -Seconds 12
}

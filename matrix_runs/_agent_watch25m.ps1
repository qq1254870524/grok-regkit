$root='C:\Users\zhang\grok-regkit'
$out=Join-Path $root 'matrix_runs\matrix_18r29_20260719_070041'
$snap=Join-Path $root 'matrix_runs\_agent_snap_latest.txt'
$log=Join-Path $root 'matrix_runs\_agent_watch_long2.log'
$deadline=(Get-Date).AddMinutes(25)
function Snap([string]$tag){
  $ts=Get-Date -Format o
  $st=''; try{$st=(Invoke-WebRequest 'http://127.0.0.1:8092/api/status' -TimeoutSec 3 -UseBasicParsing).Content}catch{$st=$_.Exception.Message}
  $console=(Get-Content (Join-Path $root 'matrix_runs\matrix_18r29_runner_console.log') -Tail 12 -EA SilentlyContinue) -join "`n"
  $sum=(Get-Content (Join-Path $out 'summary.jsonl') -Tail 4 -EA SilentlyContinue) -join "`n"
  $newest=(Get-ChildItem $out -File -EA SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 8 | ForEach-Object {"$($_.LastWriteTime.ToString('HH:mm:ss')) $($_.Name)"}) -join ' | '
  $report=Test-Path (Join-Path $out 'REPORT.md')
  $mtx=(Get-Process -Id 58728,156116 -EA SilentlyContinue | Measure-Object).Count
  $web=@(8092,8080,8010,8317) | ForEach-Object { $p=$_; try{(Invoke-WebRequest "http://127.0.0.1:$p/" -TimeoutSec 2 -UseBasicParsing)|Out-Null; "$p=OK"}catch{"$p=DOWN"} }
  $body=@(
    "tag=$tag ts=$ts report=$report matrix=$mtx",
    "ports=$($web -join ',')",
    "STATUS=$st",
    "NEWEST=$newest",
    "CONSOLE:",$console,
    "SUMMARY:",$sum
  ) -join "`n"
  Set-Content $snap $body -Encoding utf8
  Add-Content $log "$ts $tag report=$report matrix=$mtx | $((($st|ConvertFrom-Json -EA SilentlyContinue).phase)) | $newest"
  return $report
}
[void](Snap 'start')
while((Get-Date) -lt $deadline){
  Start-Sleep -Seconds 50
  if(Snap 'tick'){ break }
}
[void](Snap 'end')

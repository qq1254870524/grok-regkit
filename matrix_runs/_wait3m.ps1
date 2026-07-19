Start-Sleep -Seconds 180
$out = "C:\Users\zhang\grok-regkit\matrix_runs\_wait3m.txt"
$lines = @()
$lines += (Get-Date -Format o)
try { $st = Invoke-RestMethod http://127.0.0.1:8092/api/status -TimeoutSec 5; $lines += ($st | ConvertTo-Json -Compress) } catch { $lines += $_.Exception.Message }
$lines += '---runner---'
$lines += @(Get-Content "C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r24_weak_20260719_033411\runner.log" -Tail 20 -ErrorAction SilentlyContinue)
$lines += '---files---'
$lines += @(Get-ChildItem "C:\Users\zhang\grok-regkit\matrix_runs\matrix_18r24_weak_20260719_033411" | Sort-Object LastWriteTime -Descending | Select-Object -First 12 | ForEach-Object { "$($_.LastWriteTime) $($_.Length) $($_.Name)" })
$lines += '---procs---'
$lines += @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'matrix_rerun|post_matrix|server\.py' } | ForEach-Object { "$($_.ProcessId) $($_.CommandLine.Substring(0,[Math]::Min(120,$_.CommandLine.Length)))" })
$lines += '---post---'
$lines += @(Get-Content "C:\Users\zhang\grok-regkit\matrix_runs\_post_matrix_r25_release.log" -Tail 8 -ErrorAction SilentlyContinue)
$lines | Set-Content -Path $out -Encoding UTF8

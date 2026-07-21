$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root
$logDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$outLog = Join-Path $logDir "matrix18r42.out.log"
$errLog = Join-Path $logDir "matrix18r42.err.log"
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -and ($_.CommandLine -match "matrix_18r42_silent_mt") } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 400
$py = if (Test-Path "C:\Python312\python.exe") { "C:\Python312\python.exe" } else { (Get-Command python).Source }
$p = Start-Process -FilePath $py -ArgumentList @("-B", "tools\matrix_18r42_silent_mt.py") -WorkingDirectory $Root -WindowStyle Hidden -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog
Write-Host "matrix18r42 started PID=$($p.Id) hidden"
Start-Sleep -Seconds 2
if (Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessId -eq $p.Id }) {
  Write-Host "alive"
} else {
  Write-Host "exited early"
  Get-Content $errLog -Tail 30 -ErrorAction SilentlyContinue
}

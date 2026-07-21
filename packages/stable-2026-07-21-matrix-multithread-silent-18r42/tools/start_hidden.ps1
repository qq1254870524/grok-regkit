# start_hidden.ps1 — generic no-console launcher for grok-regkit agents
# Usage:
#   .\tools\start_hidden.ps1 -Name web -FilePath python -ArgumentList @('-B','web\server.py') -WorkDir ROOT -OutLog logs\x.out.log -ErrLog logs\x.err.log
#   .\tools\start_hidden.ps1 -Name matrix -Match 'matrix_18r40' -FilePath python -ArgumentList @('-B','tools\matrix_18r40_multithread.py') ...
param(
  [Parameter(Mandatory=$true)][string]$Name,
  [Parameter(Mandatory=$true)][string]$FilePath,
  [string[]]$ArgumentList = @(),
  [string]$WorkDir = "",
  [string]$OutLog = "",
  [string]$ErrLog = "",
  [string]$Match = "",
  [switch]$KillMatch,
  [switch]$SkipIfMatchRunning
)

$ErrorActionPreference = 'Stop'
$Root = if ($WorkDir) { $WorkDir } else { Resolve-Path (Join-Path $PSScriptRoot '..') }
Set-Location $Root
$logDir = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
if (-not $OutLog) { $OutLog = Join-Path $logDir ("{0}.out.log" -f $Name) }
if (-not $ErrLog) { $ErrLog = Join-Path $logDir ("{0}.err.log" -f $Name) }
if (-not [System.IO.Path]::IsPathRooted($OutLog)) { $OutLog = Join-Path $Root $OutLog }
if (-not [System.IO.Path]::IsPathRooted($ErrLog)) { $ErrLog = Join-Path $Root $ErrLog }

function Get-MatchedPython {
  param([string]$Pat)
  if (-not $Pat) { return @() }
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
      ($_.Name -match '^(python|pythonw)\.exe$') -and $_.CommandLine -and ($_.CommandLine -match $Pat)
    }
}

if ($Match) {
  $exist = @(Get-MatchedPython -Pat $Match)
  if ($exist.Count -gt 0 -and $SkipIfMatchRunning) {
    Write-Host "[$Name] already running PIDs=$($exist.ProcessId -join ',') (skip)"
    exit 0
  }
  if ($KillMatch -and $exist.Count -gt 0) {
    foreach ($p in $exist) {
      Write-Host "[$Name] kill PID=$($p.ProcessId)"
      Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 500
  }
}

# Resolve python
$fp = $FilePath
if ($fp -eq 'python' -or $fp -eq 'python.exe') {
  if (Test-Path 'C:\Python312\python.exe') { $fp = 'C:\Python312\python.exe' }
  else { $fp = (Get-Command python -ErrorAction SilentlyContinue).Source }
}
if (-not $fp) { throw "python not found" }

# Truncate old logs lightly (keep last 200KB if huge)
foreach ($lf in @($OutLog, $ErrLog)) {
  if (Test-Path $lf) {
    $len = (Get-Item $lf).Length
    if ($len -gt 2MB) {
      Remove-Item $lf -Force -ErrorAction SilentlyContinue
    }
  }
}

$argLine = ($ArgumentList | ForEach-Object { $_ }) -join ' '
Write-Host "[$Name] hidden start: $fp $argLine"
Write-Host "[$Name] cwd=$Root out=$OutLog err=$ErrLog"

$p = Start-Process -FilePath $fp -ArgumentList $ArgumentList `
  -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog

if (-not $p) { throw "[$Name] Start-Process failed" }
Write-Host "[$Name] PID=$($p.Id) WindowStyle=Hidden"
exit 0

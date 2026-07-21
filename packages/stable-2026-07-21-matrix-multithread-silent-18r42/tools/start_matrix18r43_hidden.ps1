# Start 18r43 silent stable matrix hidden (no Python console window)
$ErrorActionPreference = 'Stop'
$Root = 'C:\Users\zhang\grok-regkit'
$Py = 'C:\Python312\python.exe'
$Matrix = Join-Path $Root 'tools\matrix_18r43_silent_stable_mt.py'
$Silence = Join-Path $Root 'tools\_silence_safe_drission.py'
$LogDir = Join-Path $Root 'matrix_runs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Start-HiddenPython([string]$script, [string]$name) {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $Py
  $psi.Arguments = "-B `"$script`""
  $psi.WorkingDirectory = $Root
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
  $p = [System.Diagnostics.Process]::Start($psi)
  Write-Host "started $name pid=$($p.Id)"
  return $p.Id
}

# ensure silence edge_safe
if (Test-Path $Silence) {
  $sil = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match '_silence_safe_drission' }
  if (-not $sil) {
    Start-HiddenPython $Silence 'silence'
  } else {
    Write-Host "silence already running pid=$($sil.ProcessId)"
  }
}

$pidM = Start-HiddenPython $Matrix 'matrix_18r43'
Set-Content -LiteralPath (Join-Path $LogDir '_matrix_18r43.pid') -Value $pidM -Encoding ascii
Write-Host "18r43 matrix launched pid=$pidM workers=20 preheat=40 count=1000 hybrid+socks5+pending_sso"

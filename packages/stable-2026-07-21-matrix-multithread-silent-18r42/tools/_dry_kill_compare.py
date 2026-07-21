import subprocess
ps_old = r"""
$pat = 'DrissionPage|userData|\.chrome-data|chromedriver|accounts\.x\.ai|grok-regkit|auto_port'
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Name -match '^(chrome|msedge|chromedriver)\.exe$' -and
    $_.CommandLine -and ($_.CommandLine -match $pat)
  } | ForEach-Object { '{0}|{1}' -f $_.Name, $_.ProcessId }
"""
ps_new = r"""
$pat = 'DrissionPage|\.chrome-data|grok-regkit|auto_port|accounts\.x\.ai'
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Name -match '^(chrome|chromedriver)\.exe$' -and
    $_.CommandLine -and ($_.CommandLine -match $pat)
  } | ForEach-Object { '{0}|{1}' -f $_.Name, $_.ProcessId }
"""
for label, ps in [('OLD', ps_old), ('NEW', ps_new)]:
    out = subprocess.check_output(
        ['powershell', '-NoProfile', '-Command', ps],
        text=True, encoding='utf-8', errors='ignore', timeout=30,
    )
    lines = [x.strip() for x in out.splitlines() if x.strip()]
    edge = sum(1 for x in lines if x.lower().startswith('msedge'))
    chrome = sum(1 for x in lines if x.lower().startswith('chrome'))
    print(label, 'total', len(lines), 'chrome', chrome, 'msedge', edge)

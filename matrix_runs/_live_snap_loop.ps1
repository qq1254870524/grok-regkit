$root = "C:\Users\zhang\grok-regkit"
$out = "$root\matrix_runs\matrix_18r29_20260719_070041"
$end = (Get-Date).AddHours(4)
while ((Get-Date) -lt $end) {
  $lines = @()
  $lines += (Get-Date).ToString("s")
  try { $lines += (Invoke-WebRequest http://127.0.0.1:8092/api/status -TimeoutSec 5 -UseBasicParsing).Content } catch { $lines += $_.Exception.Message }
  $lines += "---console---"
  $lines += @(Get-Content "$root\matrix_runs\matrix_18r29_runner_console.log" -Tail 15)
  $cells = & C:\Python312\python.exe -B -c "import json;from collections import defaultdict;p=r'C:/Users/zhang/grok-regkit/matrix_runs/matrix_18r29_20260719_070041/summary.jsonl';cells=defaultdict(list)
for line in open(p,encoding='utf-8'):
 j=json.loads(line);cells[j['cell']].append(j)
for c,rows in cells.items():
 byr={}
 for r in rows:
  rn=r['round'];prev=byr.get(rn)
  if prev is None or (r.get('ok') and not prev.get('ok')): byr[rn]=r
 print('%s: %d/%d'%(c,sum(1 for r in byr.values() if r.get('ok')),len(byr)))
print('report', __import__('pathlib').Path(r'C:/Users/zhang/grok-regkit/matrix_runs/matrix_18r29_20260719_070041/REPORT.md').exists())"
  $lines += "---cells---"
  $lines += @($cells)
  $lines | Set-Content "$root\matrix_runs\_live_snap_18r29.txt" -Encoding UTF8
  if (Test-Path "$out\REPORT.md") { break }
  Start-Sleep -Seconds 180
}

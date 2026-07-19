Start-Sleep -Seconds 240
$root = "C:\Users\zhang\grok-regkit"
$o = New-Object System.Collections.Generic.List[string]
$o.Add((Get-Date).ToString("s"))
try { $o.Add((Invoke-WebRequest http://127.0.0.1:8092/api/status -TimeoutSec 5 -UseBasicParsing).Content) } catch { $o.Add($_.Exception.Message) }
$o.Add("---console---")
Get-Content "$root\matrix_runs\matrix_18r29_runner_console.log" -Tail 25 | ForEach-Object { $o.Add($_) }
$o.Add("---cells---")
& C:\Python312\python.exe -B -c "import json;from collections import defaultdict;p=r'C:/Users/zhang/grok-regkit/matrix_runs/matrix_18r29_20260719_070041/summary.jsonl';cells=defaultdict(list)
for line in open(p,encoding='utf-8'):
 j=json.loads(line);cells[j['cell']].append(j)
for c,rows in cells.items():
 byr={}
 for r in rows:
  rn=r['round'];prev=byr.get(rn)
  if prev is None or (r.get('ok') and not prev.get('ok')): byr[rn]=r
 print('%s: %d/%d'%(c,sum(1 for r in byr.values() if r.get('ok')),len(byr)))
print('report', __import__('pathlib').Path(r'C:/Users/zhang/grok-regkit/matrix_runs/matrix_18r29_20260719_070041/REPORT.md').exists())" | ForEach-Object { $o.Add($_) }
@(156116,18416) | ForEach-Object { if (Get-Process -Id $_ -EA SilentlyContinue) { $o.Add("$_ alive") } else { $o.Add("$_ DEAD") } }
$o | Set-Content "$root\matrix_runs\_snap4m_18r29.txt" -Encoding UTF8

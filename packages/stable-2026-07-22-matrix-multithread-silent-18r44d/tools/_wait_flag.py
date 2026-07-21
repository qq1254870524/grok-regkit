import time, sys
from pathlib import Path
sec = int(sys.argv[1]) if len(sys.argv) > 1 else 360
p = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('matrix_runs/_wait_flag.txt')
time.sleep(sec)
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(time.strftime('%Y-%m-%d %H:%M:%S'), encoding='utf-8')
print('done', p)

import time
from pathlib import Path
p=Path(r'C:\Users\zhang\grok-regkit\matrix_runs\_progress_pack2_18r29.txt')
# wait until file mentions socks5 aol 10 or browser or 12 min wall after start content changes enough
start=p.read_text(encoding='utf-8',errors='replace') if p.exists() else ''
t0=time.time()
while time.time()-t0<720:
    time.sleep(30)
    if not p.exists():
        continue
    t=p.read_text(encoding='utf-8',errors='replace')
    if 'browser__' in t or 'hybrid__socks5_list__aol: 10/10' in t or 'REPORT' in t and 'report=True' in t:
        Path(r'C:\Users\zhang\grok-regkit\matrix_runs\_gate_pack2.txt').write_text('ready\n',encoding='utf-8')
        break
    # also if socks5 outlook done 10
    if 'hybrid__socks5_list__outlook: 10/10' in t and 'hybrid__socks5_list__aol:' in t:
        # at least entered aol
        if 'hybrid__socks5_list__aol: 3/' in t or 'hybrid__socks5_list__aol: 4/' in t or 'hybrid__socks5_list__aol: 5/' in t or 'hybrid__socks5_list__aol: 10/' in t:
            Path(r'C:\Users\zhang\grok-regkit\matrix_runs\_gate_pack2.txt').write_text('mid\n'+t[:500],encoding='utf-8')
            # don't break early unless enough progress - wait for more
            pass
    # write heartbeat
    Path(r'C:\Users\zhang\grok-regkit\matrix_runs\_gate_pack2_hb.txt').write_text(t.splitlines()[0] if t else 'empty',encoding='utf-8')
else:
    Path(r'C:\Users\zhang\grok-regkit\matrix_runs\_gate_pack2.txt').write_text('timeout\n',encoding='utf-8')

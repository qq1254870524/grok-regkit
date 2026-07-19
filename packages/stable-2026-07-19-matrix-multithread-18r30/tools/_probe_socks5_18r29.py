import socket, struct, time, urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

def parse_line(line):
    line=line.strip()
    if not line or line.startswith('#'): return None
    # host:port:user:pass
    parts=line.split(':')
    if len(parts)<2: return None
    host=parts[0]; port=int(parts[1])
    user=parts[2] if len(parts)>2 else ''
    pw=':'.join(parts[3:]) if len(parts)>3 else ''
    return host,port,user,pw,line

def socks5_connect_test(host,port,user,pw, timeout=12):
    t0=time.time()
    s=socket.create_connection((host,port), timeout=timeout)
    s.settimeout(timeout)
    # greeting
    if user:
        s.sendall(b'\x05\x01\x02')
    else:
        s.sendall(b'\x05\x01\x00')
    resp=s.recv(2)
    if len(resp)<2 or resp[0]!=5:
        s.close(); return False, f'bad greeting {resp!r}', time.time()-t0
    if resp[1]==2:
        u=user.encode(); p=pw.encode()
        s.sendall(bytes([1,len(u)])+u+bytes([len(p)])+p)
        ar=s.recv(2)
        if len(ar)<2 or ar[1]!=0:
            s.close(); return False, f'auth fail {ar!r}', time.time()-t0
    elif resp[1]!=0:
        s.close(); return False, f'method {resp[1]}', time.time()-t0
    # CONNECT api.ipify.org:80
    dest=b'api.ipify.org'
    req=b'\x05\x01\x00\x03'+bytes([len(dest)])+dest+struct.pack('!H',80)
    s.sendall(req)
    hdr=s.recv(4)
    if len(hdr)<4 or hdr[1]!=0:
        s.close(); return False, f'connect status {hdr!r}', time.time()-t0
    atyp=hdr[3]
    if atyp==1: s.recv(4+2)
    elif atyp==3:
        ln=s.recv(1)[0]; s.recv(ln+2)
    elif atyp==4: s.recv(16+2)
    # HTTP
    s.sendall(b'GET / HTTP/1.1\r\nHost: api.ipify.org\r\nConnection: close\r\n\r\n')
    data=b''
    while True:
        try:
            chunk=s.recv(4096)
        except Exception:
            break
        if not chunk: break
        data+=chunk
    s.close()
    body=data.split(b'\r\n\r\n',1)[-1].decode('utf-8','replace').strip()
    return True, body[:80], time.time()-t0

lines=Path('socks5_proxies.txt').read_text(encoding='utf-8',errors='ignore').splitlines()
proxies=[parse_line(x) for x in lines]
proxies=[p for p in proxies if p]
print(f'testing {len(proxies)} proxies')
ok=0
for host,port,user,pw,raw in proxies:
    try:
        good, info, el = socks5_connect_test(host,port,user,pw)
    except Exception as e:
        good, info, el = False, str(e), 0
    print(('OK' if good else 'FAIL'), f'{host}:{port}:{user}', f'{el:.1f}s', info)
    if good: ok+=1
print(f'SUMMARY ok={ok}/{len(proxies)}')
Path('matrix_runs/_socks5_probe_18r29.txt').write_text(open(0).read() if False else '', encoding='utf-8')

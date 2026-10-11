#!/usr/bin/env python3
"""Find free TCP ports, avoiding conflicts with other projects."""
import socket, json, argparse
from contextlib import closing

def is_port_free(port: int) -> bool:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        try:
            s.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False

def find_free_port(start=5000, end=5999) -> int:
    for p in range(start, end + 1):
        if is_port_free(p):
            return p
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def find_multiple_ports(count=3, start=5000, end=5999):
    ports, cur = [], start
    while len(ports) < count and cur <= end:
        if is_port_free(cur):
            ports.append(cur)
        cur += 1
    return ports

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--count', type=int, default=1)
    ap.add_argument('--start', type=int, default=5000)
    ap.add_argument('--end',   type=int, default=5999)
    ap.add_argument('--json',  action='store_true')
    a = ap.parse_args()
    ports = find_multiple_ports(a.count, a.start, a.end)
    if a.json:
        print(json.dumps({'ports': ports, 'primary': ports[0] if ports else None}))
    else:
        for p in ports: print(p)

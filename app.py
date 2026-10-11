#!/usr/bin/env python3
"""Aflathoon Exchange Platform - entrypoint."""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from app import create_app

app = create_app()


def _port_is_free(port: int) -> bool:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('127.0.0.1', port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _pick_port() -> int:
    """Use FLASK_PORT if free, otherwise scan upward from FLASK_PORT+1."""
    preferred = int(os.getenv('FLASK_PORT', '9105') or 9105)

    if _port_is_free(preferred):
        return preferred

    # Try up to 30 ports above the preferred one
    for offset in range(1, 31):
        candidate = preferred + offset
        if _port_is_free(candidate):
            print(f"[app] port {preferred} busy, using {candidate} instead")
            return candidate

    # Last resort: OS-assigned ephemeral
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 0))
    p = s.getsockname()[1]
    s.close()
    print(f"[app] no ports near {preferred} free, using ephemeral {p}")
    return p


if __name__ == '__main__':
    port = _pick_port()
    debug = os.getenv('FLASK_ENV', 'development') == 'development'

    banner = "=" * 60
    print()
    print(banner)
    print("  AFLATHOON EXCHANGE")
    print(f"  http://127.0.0.1:{port}")
    print(banner)
    print()

    app.run(host='0.0.0.0', port=port, debug=debug, use_reloader=False)

#!/usr/bin/env python3
"""Aflathoon Exchange Platform - entrypoint."""
import os
import sys
from dotenv import load_dotenv

# Load .env before importing the app factory
load_dotenv()

from app import create_app

app = create_app()


def _port_is_free(port: int) -> bool:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('127.0.0.1', port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _pick_port() -> int:
    """Use FLASK_PORT if free, otherwise find a free port above 9100."""
    preferred = int(os.getenv('FLASK_PORT', '0') or 0)
    if preferred and _port_is_free(preferred):
        return preferred
    if preferred:
        print(f"[app] port {preferred} is in use, picking a free one...")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
    from find_free_port import find_free_port
    return find_free_port(start=9100, end=9999)


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

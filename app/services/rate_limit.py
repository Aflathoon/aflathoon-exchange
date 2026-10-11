"""
Simple in-process rate limiter keyed by arbitrary string.

Not distributed — for multi-worker deployments, swap in Redis.
For a single Gunicorn worker (current setup) this is fine.
"""
import time
from threading import Lock
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self):
        self._buckets = defaultdict(deque)
        self._lock = Lock()

    def hit(self, key, max_events, window_seconds):
        """
        Record an event for `key`.
        Returns (allowed: bool, retry_after_seconds: int).
        """
        now = time.time()
        cutoff = now - window_seconds
        with self._lock:
            q = self._buckets[key]
            # Drop old
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= max_events:
                retry_after = int(q[0] + window_seconds - now) + 1
                return False, max(retry_after, 1)
            q.append(now)
            return True, 0

    def reset(self, key):
        with self._lock:
            self._buckets.pop(key, None)


# Singleton
_limiter = RateLimiter()


def get_limiter():
    return _limiter


# --- Flask decorator ------------------------------------------------------
from functools import wraps
from flask import request, jsonify, abort
from flask_login import current_user


def limit(key_prefix, max_events, window_seconds, by='user', json_response=False):
    """
    Decorator that enforces a per-user (or per-IP) limit.

    by:
      'user'  -> current_user.id (falls back to IP if anonymous)
      'ip'    -> request.remote_addr
      'form:<field>' -> value of that form field (e.g. 'form:email')
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Determine the key value
            if by == 'ip':
                keyval = request.remote_addr or 'unknown'
            elif by.startswith('form:'):
                field = by.split(':', 1)[1]
                keyval = (request.form.get(field) or '').strip().lower() or 'empty'
            else:
                uid = getattr(current_user, 'id', None) if getattr(current_user, 'is_authenticated', False) else None
                keyval = f"u{uid}" if uid else (request.remote_addr or 'anon')

            key = f"{key_prefix}:{by}:{keyval}"
            allowed, retry_after = _limiter.hit(key, max_events, window_seconds)

            if not allowed:
                msg = f"Too many requests. Try again in {retry_after}s."
                if json_response:
                    resp = jsonify({'error': msg, 'retry_after': retry_after})
                    resp.status_code = 429
                    resp.headers['Retry-After'] = str(retry_after)
                    return resp
                abort(429, description=msg)

            return f(*args, **kwargs)
        return wrapper
    return decorator

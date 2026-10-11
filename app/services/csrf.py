"""
Lightweight CSRF protection — no Flask-WTF dependency.

How it works:
  - A random token is generated per session and stored in Flask's session.
  - Every POST form embeds the token via {{ csrf_token() }}.
  - before_request checks that form POSTs carry a matching token.
  - AJAX POSTs can send X-CSRF-Token header instead.

Exempt paths: anything that isn't a state-changing request on our own forms.
"""
import secrets
from flask import session, request, abort, jsonify
from markupsafe import Markup


CSRF_SESSION_KEY = '_csrf_token'
CSRF_HEADER = 'X-CSRF-Token'
CSRF_FORM_FIELD = 'csrf_token'


def get_token():
    """Return the session's CSRF token, generating one if needed."""
    tok = session.get(CSRF_SESSION_KEY)
    if not tok:
        tok = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = tok
    return tok


def rotate_token():
    """Force a new token (call on login/logout)."""
    session[CSRF_SESSION_KEY] = secrets.token_urlsafe(32)


def validate():
    """
    Called from before_request. Only validates POST/PUT/PATCH/DELETE
    on same-origin requests.
    """
    if request.method in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
        return None

    # Allow specific safe exceptions
    # (Flask-Login's next redirect, static files, etc.)
    path = request.path or ''
    if path.startswith('/static/'):
        return None

    expected = session.get(CSRF_SESSION_KEY)

    # Accept token from form or header
    submitted = None
    if request.form:
        submitted = request.form.get(CSRF_FORM_FIELD)
    if not submitted:
        submitted = request.headers.get(CSRF_HEADER)
    if not submitted and request.is_json:
        try:
            data = request.get_json(silent=True) or {}
            submitted = data.get(CSRF_FORM_FIELD)
        except Exception:
            pass

    if not expected or not submitted or not secrets.compare_digest(expected, submitted):
        # Reject: JSON vs HTML response
        if request.is_json or request.headers.get('Accept', '').startswith('application/json'):
            resp = jsonify({'error': 'CSRF token missing or invalid'})
            resp.status_code = 400
            return resp
        abort(400, description='CSRF token missing or invalid')

    return None


def inject_template_helper():
    """Return a Jinja-callable that emits the CSRF hidden input or token."""
    def csrf_token():
        return get_token()
    def csrf_input():
        return Markup(f'<input type="hidden" name="{CSRF_FORM_FIELD}" value="{get_token()}">')
    return {'csrf_token': csrf_token, 'csrf_input': csrf_input}

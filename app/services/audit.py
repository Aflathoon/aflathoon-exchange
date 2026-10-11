"""
Central audit logging. Call log() from anywhere.
Fails silently so audit never breaks the request path.
"""
import json
from flask import request, has_request_context
from flask_login import current_user
from app import db
from app.models.audit_log import AuditLog


def _snapshot(obj, fields):
    if obj is None:
        return None
    out = {}
    for f in fields:
        try:
            v = getattr(obj, f)
            if hasattr(v, 'isoformat'):
                v = v.isoformat()
            elif hasattr(v, 'value'):     # Enum
                v = v.value
            out[f] = v
        except Exception:
            pass
    return out


def log(action, entity=None, entity_type=None, entity_id=None,
        summary=None, before=None, after=None):
    """
    Record an audit event.
      action        -> "user.verify_email" etc
      entity        -> model instance (optional); its id/type auto-detected
      before/after  -> dicts of changed fields (optional)
    """
    try:
        actor_id = None
        actor_username = None
        if current_user and getattr(current_user, 'is_authenticated', False):
            actor_id = getattr(current_user, 'id', None)
            actor_username = getattr(current_user, 'username', None)

        if entity is not None:
            entity_type = entity_type or type(entity).__name__.lower()
            entity_id = entity_id or getattr(entity, 'id', None)

        ip = None
        ua = None
        if has_request_context():
            ip = request.headers.get('X-Forwarded-For', request.remote_addr or '')
            ip = ip.split(',')[0].strip() if ip else None
            ua = (request.user_agent.string or '')[:300]

        row = AuditLog(
            actor_id=actor_id,
            actor_username=actor_username,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            summary=(summary or '')[:400],
            before_json=json.dumps(before) if before else None,
            after_json=json.dumps(after) if after else None,
            ip_address=ip,
            user_agent=ua,
        )
        db.session.add(row)
        db.session.commit()
    except Exception:
        # Never let audit break the caller
        try:
            db.session.rollback()
        except Exception:
            pass


# Convenience helpers
def log_user_action(user, action, summary, before=None, after=None):
    log(f"user.{action}", entity=user, summary=summary, before=before, after=after)

def log_company_action(company, action, summary, before=None, after=None):
    log(f"company.{action}", entity=company, summary=summary, before=before, after=after)

def log_transaction_action(tx, action, summary):
    log(f"transaction.{action}", entity=tx, summary=summary)

def log_assistant_action(action, summary, entity_type=None, entity_id=None):
    log(f"assistant.{action}", entity_type=entity_type, entity_id=entity_id, summary=summary)

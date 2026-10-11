import json
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, session
from flask_login import current_user
from app import db
from app.models.alert import Alert
from app.services import audit


alerts_bp = Blueprint('alerts', __name__)


@alerts_bp.route('/api/alerts/active')
def active():
    """Return alerts not yet dismissed by the current user."""
    q = Alert.query.filter(
        (Alert.expires_at.is_(None)) | (Alert.expires_at > datetime.utcnow())
    ).order_by(Alert.created_at.desc()).limit(20)

    uid = getattr(current_user, 'id', None)
    out = []
    for a in q:
        if uid and a.is_dismissed_by(uid):
            continue
        out.append({
            'id': a.id,
            'severity': a.severity,
            'title': a.title,
            'body': a.body,
            'link_url': a.link_url,
            'link_label': a.link_label,
            'created_at': a.created_at.isoformat() if a.created_at else None,
        })
    return jsonify({'alerts': out})


@alerts_bp.route('/api/alerts/<int:aid>/dismiss', methods=['POST'])
def dismiss(aid):
    a = Alert.query.get_or_404(aid)
    uid = getattr(current_user, 'id', None)
    if not uid:
        return jsonify({'ok': False, 'error': 'not logged in'}), 401

    ids = list(a.dismissed_by_ids())
    if uid not in ids:
        ids.append(uid)
        a.dismissed_by = json.dumps(ids)
        db.session.commit()
    return jsonify({'ok': True})

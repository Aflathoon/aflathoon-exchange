from datetime import datetime
from app import db


class Alert(db.Model):
    """Operator-facing banner. Shown on all admin pages until dismissed."""
    __tablename__ = 'alerts'

    id = db.Column(db.Integer, primary_key=True)
    severity = db.Column(db.String(20), default='info')   # info / warning / critical
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text)
    link_url = db.Column(db.String(300))
    link_label = db.Column(db.String(60))
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    expires_at = db.Column(db.DateTime)
    dismissed_by = db.Column(db.Text)   # JSON list of user ids who dismissed it

    def dismissed_by_ids(self):
        import json
        try:
            return set(json.loads(self.dismissed_by or '[]'))
        except Exception:
            return set()

    def is_dismissed_by(self, user_id):
        return user_id in self.dismissed_by_ids()

    def is_expired(self):
        return self.expires_at and self.expires_at < datetime.utcnow()

    def __repr__(self):
        return f'<Alert {self.severity}: {self.title[:40]}>'

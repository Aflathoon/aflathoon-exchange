from datetime import datetime
from app import db
import json


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    actor_username = db.Column(db.String(64))                 # snapshot; survives user deletion
    action = db.Column(db.String(80), nullable=False, index=True)   # e.g. "user.verify_email"
    entity_type = db.Column(db.String(40), index=True)        # e.g. "user", "company", "transaction"
    entity_id = db.Column(db.Integer, index=True)
    summary = db.Column(db.String(400))                       # human-readable one-liner
    before_json = db.Column(db.Text)                          # JSON snapshot of relevant fields
    after_json = db.Column(db.Text)
    ip_address = db.Column(db.String(64))
    user_agent = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    actor = db.relationship('User', foreign_keys=[actor_id])

    def before(self):
        try:
            return json.loads(self.before_json) if self.before_json else {}
        except Exception:
            return {}

    def after(self):
        try:
            return json.loads(self.after_json) if self.after_json else {}
        except Exception:
            return {}

    def __repr__(self):
        return f'<AuditLog {self.action} by {self.actor_username}>'

from datetime import datetime, timedelta
from app import db


class EmailToken(db.Model):
    __tablename__ = 'email_tokens'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    token = db.Column(db.String(128), unique=True, nullable=False, index=True)
    purpose = db.Column(db.String(30), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='email_tokens')

    @property
    def is_valid(self):
        return self.used_at is None and datetime.utcnow() < self.expires_at

    @classmethod
    def new(cls, user_id, purpose, ttl_seconds):
        import secrets
        token = secrets.token_urlsafe(48)
        return cls(
            user_id=user_id,
            token=token,
            purpose=purpose,
            expires_at=datetime.utcnow() + timedelta(seconds=ttl_seconds),
        )

    def __repr__(self):
        return f'<EmailToken {self.purpose} user={self.user_id}>'

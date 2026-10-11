from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)

    # Identity
    full_name = db.Column(db.String(200))
    phone = db.Column(db.String(30))
    date_of_birth = db.Column(db.Date)
    country = db.Column(db.String(80))
    address_line1 = db.Column(db.String(200))
    address_line2 = db.Column(db.String(200))
    city = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))

    # Account flags
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    account_type = db.Column(db.String(20), default='individual')   # individual / company
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'))

    # KYC / compliance
    kyc_status = db.Column(db.String(20), default='pending')
    kyc_tier = db.Column(db.Integer, default=0)
    lei_code = db.Column(db.String(20))

    # Two-factor authentication
    two_factor_secret = db.Column(db.String(64))              # TOTP secret (base32)
    two_factor_enabled = db.Column(db.Boolean, default=False)
    two_factor_backup_codes = db.Column(db.Text)             # JSON list of hashed codes
    two_factor_confirmed_at = db.Column(db.DateTime)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    # Transactions
    transactions = db.relationship('Transaction', backref='user', lazy='dynamic')

    def set_password(self, p):
        self.password_hash = generate_password_hash(p)

    def check_password(self, p):
        return check_password_hash(self.password_hash, p)

    def __repr__(self):
        return f'<User {self.username}>'

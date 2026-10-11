from datetime import datetime
from app import db


class Company(db.Model):
    __tablename__ = 'companies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    registration_number = db.Column(db.String(80))
    jurisdiction = db.Column(db.String(80))
    tax_id = db.Column(db.String(80))
    lei_code = db.Column(db.String(20))                    # Legal Entity Identifier
    website = db.Column(db.String(200))
    industry = db.Column(db.String(120))

    # Verification lifecycle
    status = db.Column(db.String(30), default='pending')   # pending / verified / rejected / suspended
    verified_at = db.Column(db.DateTime)
    verified_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    rejection_reason = db.Column(db.Text)

    # Contact
    contact_email = db.Column(db.String(120))
    contact_phone = db.Column(db.String(30))
    address_line1 = db.Column(db.String(200))
    address_line2 = db.Column(db.String(200))
    city = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))
    country = db.Column(db.String(80))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    users = db.relationship('User', backref='company', lazy='dynamic',
                            foreign_keys='User.company_id')
    verified_by = db.relationship('User', foreign_keys=[verified_by_id], post_update=True)

    @property
    def is_verified(self):
        return self.status == 'verified'

    @property
    def user_count(self):
        return self.users.count()

    def __repr__(self):
        return f'<Company {self.name}>'

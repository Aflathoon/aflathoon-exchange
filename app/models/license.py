from datetime import datetime, date
from app import db


class License(db.Model):
    __tablename__ = 'licenses'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    license_type = db.Column(db.String(80))
    jurisdiction = db.Column(db.String(80))
    authority = db.Column(db.String(200))
    license_number = db.Column(db.String(120))
    status = db.Column(db.String(30), default='pending')
    issued_date = db.Column(db.Date)
    expiry_date = db.Column(db.Date)
    renewal_cost = db.Column(db.Numeric(20, 2), default=0)
    currency = db.Column(db.String(8), default='GBP')
    document_path = db.Column(db.String(400))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def days_to_expiry(self):
        if not self.expiry_date:
            return None
        return (self.expiry_date - date.today()).days

    @property
    def is_valid(self):
        return (self.status == 'active'
                and (self.expiry_date is None or self.days_to_expiry > 0))

    @property
    def urgency(self):
        """'expired' | 'critical' | 'soon' | 'watch' | 'ok'"""
        d = self.days_to_expiry
        if d is None: return 'ok'
        if d < 0:   return 'expired'
        if d <= 7:  return 'critical'
        if d <= 30: return 'soon'
        if d <= 90: return 'watch'
        return 'ok'


class Deadline(db.Model):
    __tablename__ = 'deadlines'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50))
    due_date = db.Column(db.Date, nullable=False)
    recurrence = db.Column(db.String(20))
    responsible = db.Column(db.String(120))
    cost_estimate = db.Column(db.Numeric(20, 2), default=0)
    currency = db.Column(db.String(8), default='GBP')
    status = db.Column(db.String(20), default='open')
    linked_license_id = db.Column(db.Integer, db.ForeignKey('licenses.id'))
    document_path = db.Column(db.String(400))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def days_left(self):
        return (self.due_date - date.today()).days

    @property
    def urgency(self):
        d = self.days_left
        if d < 0:   return 'expired'
        if d <= 7:  return 'critical'
        if d <= 30: return 'soon'
        if d <= 90: return 'watch'
        return 'ok'


class ComplianceDocument(db.Model):
    __tablename__ = 'compliance_documents'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    doc_type = db.Column(db.String(50))
    file_path = db.Column(db.String(400))
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.String(80))
    version = db.Column(db.String(20), default='1.0')
    issued_by = db.Column(db.String(200))
    issued_date = db.Column(db.Date)
    expiry_date = db.Column(db.Date)
    confidential = db.Column(db.Boolean, default=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

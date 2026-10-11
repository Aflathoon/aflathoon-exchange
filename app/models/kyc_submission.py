from datetime import datetime
from app import db


class KYCSubmission(db.Model):
    __tablename__ = 'kyc_submissions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    # Document type being submitted
    tier_requested = db.Column(db.Integer, default=1)   # 1 = basic, 2 = full
    doc_type = db.Column(db.String(40))                  # passport / national_id / drivers_licence
    doc_number = db.Column(db.String(80))

    # Uploaded files (relative paths under compliance/kyc_uploads/)
    id_front_path = db.Column(db.String(400))
    id_back_path = db.Column(db.String(400))
    selfie_path = db.Column(db.String(400))
    proof_of_address_path = db.Column(db.String(400))

    # Applicant details (as printed on documents)
    legal_name = db.Column(db.String(200))
    date_of_birth = db.Column(db.Date)
    nationality = db.Column(db.String(80))

    # Review
    status = db.Column(db.String(20), default='pending', index=True)   # pending / approved / rejected
    reviewer_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewer_notes = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    reviewed_at = db.Column(db.DateTime)

    user = db.relationship('User', foreign_keys=[user_id], backref='kyc_submissions')
    reviewer = db.relationship('User', foreign_keys=[reviewer_id])

    @property
    def is_pending(self):
        return self.status == 'pending'

    def __repr__(self):
        return f'<KYCSubmission user={self.user_id} status={self.status}>'

"""
Sanctions / PEP / watchlist storage and screening results.

Data source: OpenSanctions (https://www.opensanctions.org)
  Free bulk downloads, CC-BY 4.0 license, no API key.

Tables:
  SanctionsEntity   - one per sanctioned person/company
  SanctionsScreen   - every screening run for audit
  SanctionsHit      - a possible match requiring review
"""
import enum
from datetime import datetime
from app import db


class SanctionsStatus(enum.Enum):
    CLEAR   = 'clear'      # screened, no hits
    REVIEW  = 'review'     # one or more hits require manual review
    BLOCKED = 'blocked'    # admin confirmed a true positive
    FALSE_POSITIVE = 'false_positive'   # admin cleared it


class SanctionsListType(enum.Enum):
    SANCTIONS = 'sanctions'   # OFAC, EU, UN, UK, etc.
    PEP       = 'pep'
    WATCHLIST = 'watchlist'
    OTHER     = 'other'


class SanctionsEntity(db.Model):
    """One row per sanctioned/PEP entity from OpenSanctions."""
    __tablename__ = 'sanctions_entities'

    id = db.Column(db.Integer, primary_key=True)
    opensanctions_id = db.Column(db.String(80), unique=True, index=True)
    schema = db.Column(db.String(40))          # Person, Company, Organization
    name = db.Column(db.String(400), nullable=False, index=True)
    name_lower = db.Column(db.String(400), nullable=False, index=True)   # for fast LIKE
    aliases = db.Column(db.Text)               # JSON list of alternative names
    aliases_lower = db.Column(db.Text)         # lower-cased combined
    countries = db.Column(db.String(200))      # comma-separated ISO codes
    birth_date = db.Column(db.String(40))
    datasets = db.Column(db.Text)              # JSON list of source datasets
    list_type = db.Column(db.Enum(SanctionsListType), index=True)
    topics = db.Column(db.String(400))         # sanction, role.pep, crime, etc.
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<SanctionsEntity {self.id} {self.name[:40]}>'


class SanctionsScreen(db.Model):
    """A single screening run — audit trail."""
    __tablename__ = 'sanctions_screens'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    subject_name = db.Column(db.String(400), nullable=False)
    subject_country = db.Column(db.String(80))
    subject_type = db.Column(db.String(40))     # user, company, transaction
    context = db.Column(db.String(80))          # registration, booking, manual
    status = db.Column(db.Enum(SanctionsStatus), default=SanctionsStatus.CLEAR, index=True)
    hit_count = db.Column(db.Integer, default=0)
    best_score = db.Column(db.Float, default=0.0)   # highest match score 0-1
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    hits = db.relationship('SanctionsHit', backref='screen', lazy='dynamic',
                           cascade='all, delete-orphan')
    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<Screen {self.id} {self.subject_name[:30]} {self.status.value}>'


class SanctionsHit(db.Model):
    """A specific match between a screened subject and an entity."""
    __tablename__ = 'sanctions_hits'

    id = db.Column(db.Integer, primary_key=True)
    screen_id = db.Column(db.Integer, db.ForeignKey('sanctions_screens.id'), index=True)
    entity_id = db.Column(db.Integer, db.ForeignKey('sanctions_entities.id'), index=True)
    score = db.Column(db.Float)                 # 0..1 similarity
    matched_name = db.Column(db.String(400))
    reason = db.Column(db.String(200))          # exact, fuzzy_name, alias, country

    # Review
    reviewed = db.Column(db.Boolean, default=False, index=True)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime)
    reviewer_notes = db.Column(db.Text)
    is_true_positive = db.Column(db.Boolean)    # admin decision

    entity = db.relationship('SanctionsEntity')
    reviewer = db.relationship('User', foreign_keys=[reviewed_by_id])

    def __repr__(self):
        return f'<Hit {self.id} score={self.score:.2f}>'

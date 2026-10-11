"""
Admin AI Assistant — rule-based anomaly and task scanner.

Every check returns a list of Finding objects. Findings have severity,
a title, a detail line, and an actionable next step. No LLM required;
the "intelligence" is domain rules encoded explicitly so they're
auditable and predictable.
"""
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Callable, List
from app import db


SEVERITY_ORDER = {'critical': 0, 'warning': 1, 'info': 2}


@dataclass
class Finding:
    key: str
    severity: str            # critical / warning / info
    title: str
    detail: str
    action_label: str = ''
    action_url: str = ''
    count: int = 1
    entity_type: str = ''
    entity_id: int = 0

    def to_dict(self):
        return asdict(self)


# --------------------------------------------------------------------- checks
def check_expiring_licenses():
    from app.models.license import License
    out = []
    today = datetime.utcnow().date()

    for l in License.query.filter_by(status='active').all():
        if not l.expiry_date:
            continue
        days = (l.expiry_date - today).days
        if days < 0:
            out.append(Finding(
                key=f'license_expired_{l.id}',
                severity='critical',
                title=f'License expired: {l.name}',
                detail=f'{l.jurisdiction or ""} license expired {-days} day(s) ago. Live trading is blocked.',
                action_label='Review',
                action_url='/compliance/',
                entity_type='license', entity_id=l.id,
            ))
        elif days <= 30:
            out.append(Finding(
                key=f'license_soon_{l.id}',
                severity='critical' if days <= 7 else 'warning',
                title=f'License expires in {days}d: {l.name}',
                detail=f'{l.jurisdiction or ""} · renew soon to avoid suspension',
                action_label='Open compliance',
                action_url='/compliance/',
                entity_type='license', entity_id=l.id,
            ))
    return out


def check_unverified_companies():
    from app.models.company import Company
    cutoff = datetime.utcnow() - timedelta(hours=48)
    stale = Company.query.filter(
        Company.status == 'pending',
        Company.created_at <= cutoff,
    ).all()
    if not stale:
        return []
    return [Finding(
        key='unverified_companies',
        severity='warning',
        title=f'{len(stale)} unverified company account(s)',
        detail='Pending for over 48 hours. Review to unlock them.',
        action_label='Review companies',
        action_url='/admin/companies?status=pending',
        count=len(stale),
        entity_type='company',
    )]


def check_unverified_users():
    from app.models.user import User
    cutoff = datetime.utcnow() - timedelta(hours=24)
    stale = User.query.filter(
        User.email_verified == False,   # noqa: E712
        User.created_at <= cutoff,
        User.is_active == True,         # noqa: E712
    ).all()
    if not stale:
        return []
    return [Finding(
        key='unverified_users',
        severity='warning',
        title=f'{len(stale)} user(s) unverified after 24h',
        detail='Email verification pending. Resend or manually verify.',
        action_label='Open users',
        action_url='/admin/users',
        count=len(stale),
        entity_type='user',
    )]


def check_admins_without_2fa():
    from app.models.user import User
    admins = User.query.filter_by(is_admin=True, is_active=True).all()
    missing = [u for u in admins if not u.two_factor_enabled]
    if not missing:
        return []
    return [Finding(
        key='admins_no_2fa',
        severity='critical',
        title=f'{len(missing)} admin account(s) without 2FA',
        detail='Every admin should have two-factor authentication enabled.',
        action_label='Open users',
        action_url='/admin/users',
        count=len(missing),
        entity_type='user',
    )]


def check_unsettled_transactions():
    from app.models.transaction import Transaction, TransactionStatus
    cutoff = datetime.utcnow() - timedelta(hours=24)
    stale = Transaction.query.filter(
        Transaction.status == TransactionStatus.CONFIRMED,
        Transaction.created_at <= cutoff,
    ).all()
    if not stale:
        return []
    return [Finding(
        key='unsettled_tx',
        severity='warning',
        title=f'{len(stale)} confirmed transaction(s) unsettled >24h',
        detail='Follow up on settlement. Review the blotter.',
        action_label='Open blotter',
        action_url='/admin/blotter?status=confirmed',
        count=len(stale),
        entity_type='transaction',
    )]


def check_large_transactions():
    from app.models.transaction import Transaction
    cutoff = datetime.utcnow() - timedelta(days=1)
    threshold = 50_000
    large = Transaction.query.filter(
        Transaction.created_at >= cutoff,
        Transaction.from_amount >= threshold,
    ).all()
    if not large:
        return []
    return [Finding(
        key='large_tx_24h',
        severity='info',
        title=f'{len(large)} transaction(s) over {threshold:,} in last 24h',
        detail='Review for AML/fraud signals.',
        action_label='Review',
        action_url='/admin/blotter',
        count=len(large),
        entity_type='transaction',
    )]


def check_stale_rate_source():
    try:
        from app.services.rate_engine import get_engine
        info = get_engine().source_info()
    except Exception:
        return []
    if info.get('source') == 'fallback':
        return [Finding(
            key='rates_fallback',
            severity='warning',
            title='Rates running on fallback',
            detail='Live API key not configured or unreachable. Quotes may diverge from market.',
            action_label='View settings',
            action_url='/admin/',
            entity_type='rate_engine',
        )]
    return []


def check_missing_backups():
    import os, glob, time
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    backup_dir = os.path.join(root, 'data', 'backups')
    files = glob.glob(os.path.join(backup_dir, 'exchange-*.db'))
    if not files:
        return [Finding(
            key='no_backups',
            severity='critical',
            title='No database backups found',
            detail='Configure cron to run scripts/backup_db.sh daily.',
            action_label='View README',
            action_url='/admin/',
            entity_type='backup',
        )]
    latest = max(files, key=os.path.getmtime)
    age_hours = int((time.time() - os.path.getmtime(latest)) / 3600)
    if age_hours > 48:
        return [Finding(
            key='backup_stale',
            severity='critical',
            title=f'Latest backup is {age_hours}h old',
            detail='Expected daily backups. Check cron.',
            action_label='View backup dir',
            action_url='/admin/',
            entity_type='backup',
        )]
    return []


# --------------------------------------------------------------------- runner
CHECKS: List[Callable] = [
    check_expiring_licenses,
    check_admins_without_2fa,
    check_unverified_companies,
    check_unverified_users,
    check_unsettled_transactions,
    check_large_transactions,
    check_stale_rate_source,
    check_missing_backups,
]


def scan_all():
    findings = []
    for fn in CHECKS:
        try:
            findings.extend(fn())
        except Exception as e:
            findings.append(Finding(
                key=f'error_{fn.__name__}',
                severity='warning',
                title=f'Check failed: {fn.__name__}',
                detail=str(e)[:200],
                action_label='',
                action_url='/admin/audit',
            ))
    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), -f.count))
    return findings


def summary(findings=None):
    findings = findings if findings is not None else scan_all()
    c = sum(1 for f in findings if f.severity == 'critical')
    w = sum(1 for f in findings if f.severity == 'warning')
    i = sum(1 for f in findings if f.severity == 'info')
    return {'critical': c, 'warning': w, 'info': i, 'total': len(findings)}

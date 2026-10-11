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
    severity: str
    title: str
    detail: str
    action_label: str = ''
    action_url: str = ''
    count: int = 1
    entity_type: str = ''
    entity_id: int = 0
    action_kind: str = ''
    action_payload: dict = field(default_factory=dict)
    fix_label: str = ''
    fix_confirm: str = ''

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
        action_kind='list_company_ids',
        fix_label='→ Open each',
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
        action_kind='resend_verification_all',
        fix_label='📧 Resend to all',
        fix_confirm='Send verification emails to all unverified users?',
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
        action_kind='notify_admins_2fa',
        fix_label='🔔 Send 2FA reminder',
        fix_confirm='Email every admin without 2FA?',
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
            action_kind='reset_rate_cache',
            fix_label='↻ Refresh rates',
            fix_confirm='Clear rate cache and force a fresh fetch?',
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
            action_kind='run_backup',
            fix_label='💾 Run first backup',
            fix_confirm='Run a fresh database backup now?',
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
            action_kind='run_backup',
            fix_label='💾 Run backup now',
            fix_confirm='Run a fresh database backup now?',
            severity='critical',
            title=f'Latest backup is {age_hours}h old',
            detail='Expected daily backups. Check cron.',
            action_label='View backup dir',
            action_url='/admin/',
            entity_type='backup',
        )]
    return []


# --------------------------------------------------------------------- shipments
def check_delayed_shipments():
    """Shipments explicitly marked delayed for >24h."""
    from app.models.shipment import Shipment, ShipmentStatus
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(hours=24)
    stale = Shipment.query.filter(
        Shipment.status == ShipmentStatus.DELAYED,
        Shipment.delayed_at <= cutoff,
    ).all()
    if not stale:
        return []
    return [Finding(
        key='shipments_delayed',
        severity='critical',
        title=f'{len(stale)} shipment(s) delayed >24h',
        detail='Customers waiting. Review carrier status and update the waybill.',
        action_label='Open shipments',
        action_url='/admin/shipments?status=delayed',
        count=len(stale),
        entity_type='shipment',
        action_kind='notify_carriers_delayed',
        fix_label='📧 Flag for follow-up',
        fix_confirm=f'Flag all {len(stale)} delayed shipment(s) for carrier follow-up?',
    )]


def check_stuck_shipments():
    """Shipments stuck in customs or in_transit for >72h."""
    from app.models.shipment import Shipment, ShipmentStatus
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(hours=72)
    stale = Shipment.query.filter(
        Shipment.status.in_([ShipmentStatus.IN_TRANSIT, ShipmentStatus.CUSTOMS]),
        Shipment.created_at <= cutoff,
    ).all()
    if not stale:
        return []
    return [Finding(
        key='shipments_stuck',
        severity='warning',
        title=f'{len(stale)} shipment(s) stuck >72h',
        detail='Still in transit or customs after 3 days. Contact carrier.',
        action_label='Review',
        action_url='/admin/shipments?status=open',
        count=len(stale),
        entity_type='shipment',
    )]


def check_unassigned_shipments():
    """Booked shipments with no carrier assigned."""
    from app.models.shipment import Shipment, ShipmentStatus
    orphans = Shipment.query.filter(
        Shipment.status == ShipmentStatus.BOOKED,
        Shipment.carrier_id.is_(None),
    ).all()
    if not orphans:
        return []
    return [Finding(
        key='shipments_unassigned',
        severity='warning',
        title=f'{len(orphans)} booked shipment(s) without carrier',
        detail='Assign a carrier to move them forward.',
        action_label='Assign now',
        action_url='/admin/shipments?status=booked',
        count=len(orphans),
        entity_type='shipment',
    )]


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
    check_delayed_shipments,
    check_stuck_shipments,
    check_unassigned_shipments,
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

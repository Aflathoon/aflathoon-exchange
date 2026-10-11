import csv
import io
import os
from datetime import date, timedelta
from calendar import monthrange
from functools import wraps

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, send_file, current_app)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app import db
from app.models.license import License, Deadline, ComplianceDocument

compliance_bp = Blueprint('compliance', __name__)

ALLOWED_EXT = {'.pdf', '.png', '.jpg', '.jpeg', '.docx', '.txt', '.csv'}
MAX_SIZE = 16 * 1024 * 1024  # 16 MB


def admin_only(f):
    @wraps(f)
    @login_required
    def d(*a, **k):
        if not current_user.is_admin:
            flash('Admin only')
            return redirect(url_for('main.index'))
        return f(*a, **k)
    return d


def _docs_dir():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    d = os.path.join(root, 'compliance', 'documents')
    os.makedirs(d, exist_ok=True)
    return d


def _month_span(start: date, months: int = 12):
    """Yield (year, month) tuples starting at start's month."""
    y, m = start.year, start.month
    for _ in range(months):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


@compliance_bp.route('/')
@admin_only
def overview():
    licenses = License.query.order_by(License.expiry_date.asc().nullslast()).all()
    deadlines = Deadline.query.filter_by(status='open').order_by(Deadline.due_date.asc()).all()
    documents = ComplianceDocument.query.order_by(ComplianceDocument.uploaded_at.desc()).all()

    today = date.today()
    horizons = {h: today + timedelta(days=h) for h in (7, 30, 90)}
    alerts = {
        'expiring_7':  [l for l in licenses if l.expiry_date and today <= l.expiry_date <= horizons[7]],
        'expiring_30': [l for l in licenses if l.expiry_date and horizons[7] < l.expiry_date <= horizons[30]],
        'expiring_90': [l for l in licenses if l.expiry_date and horizons[30] < l.expiry_date <= horizons[90]],
        'deadlines_7':  [d for d in deadlines if today <= d.due_date <= horizons[7]],
        'deadlines_30': [d for d in deadlines if horizons[7] < d.due_date <= horizons[30]],
        'expired':     [l for l in licenses if l.expiry_date and l.expiry_date < today],
    }

    # Cost rollup
    def _sum(items, attr):
        return sum(float(getattr(i, attr) or 0) for i in items)

    cost = {
        'licenses_total':  _sum(licenses, 'renewal_cost'),
        'deadlines_total': _sum(deadlines, 'cost_estimate'),
        'currency': 'GBP',
        'by_jurisdiction': {},
        'by_type': {},
    }
    for l in licenses:
        j = l.jurisdiction or '—'
        t = l.license_type or '—'
        cost['by_jurisdiction'][j] = cost['by_jurisdiction'].get(j, 0) + float(l.renewal_cost or 0)
        cost['by_type'][t] = cost['by_type'].get(t, 0) + float(l.renewal_cost or 0)
    cost['grand_total'] = cost['licenses_total'] + cost['deadlines_total']

    # 12-month calendar buckets
    calendar = {}
    for y, m in _month_span(today, 12):
        calendar[(y, m)] = {'licenses': [], 'deadlines': []}
    for l in licenses:
        if l.expiry_date:
            key = (l.expiry_date.year, l.expiry_date.month)
            if key in calendar:
                calendar[key]['licenses'].append(l)
    for d in deadlines:
        key = (d.due_date.year, d.due_date.month)
        if key in calendar:
            calendar[key]['deadlines'].append(d)

    return render_template(
        'compliance/overview.html',
        licenses=licenses, deadlines=deadlines, documents=documents,
        alerts=alerts, cost=cost, calendar=calendar, today=today,
    )


@compliance_bp.route('/license/add', methods=['POST'])
@admin_only
def add_license():
    def pdate(v): return date.fromisoformat(v) if v else None
    lic = License(
        name=request.form['name'],
        license_type=request.form.get('license_type', 'msb'),
        jurisdiction=request.form.get('jurisdiction', ''),
        authority=request.form.get('authority', ''),
        license_number=request.form.get('license_number', ''),
        status=request.form.get('status', 'pending'),
        issued_date=pdate(request.form.get('issued_date')),
        expiry_date=pdate(request.form.get('expiry_date')),
        renewal_cost=request.form.get('renewal_cost') or 0,
        currency=request.form.get('currency', 'GBP'),
        document_path=request.form.get('document_path', ''),
        notes=request.form.get('notes', ''),
    )
    db.session.add(lic); db.session.commit()
    flash('License added')
    return redirect(url_for('compliance.overview'))


@compliance_bp.route('/deadline/add', methods=['POST'])
@admin_only
def add_deadline():
    dl = Deadline(
        title=request.form['title'],
        category=request.form.get('category', 'license'),
        due_date=date.fromisoformat(request.form['due_date']),
        recurrence=request.form.get('recurrence', 'none'),
        responsible=request.form.get('responsible', ''),
        cost_estimate=request.form.get('cost_estimate') or 0,
        currency=request.form.get('currency', 'GBP'),
        notes=request.form.get('notes', ''),
    )
    db.session.add(dl); db.session.commit()
    flash('Deadline added')
    return redirect(url_for('compliance.overview'))


@compliance_bp.route('/document/upload', methods=['POST'])
@admin_only
def upload_document():
    file = request.files.get('file')
    if not file or not file.filename:
        flash('No file selected'); return redirect(url_for('compliance.overview'))

    name = secure_filename(file.filename)
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_EXT:
        flash(f'File type {ext} not allowed'); return redirect(url_for('compliance.overview'))

    file.seek(0, os.SEEK_END); size = file.tell(); file.seek(0)
    if size > MAX_SIZE:
        flash('File too large (max 16 MB)'); return redirect(url_for('compliance.overview'))

    target_dir = _docs_dir()
    ts = date.today().strftime('%Y%m%d')
    fname = f"{ts}-{name}"
    target = os.path.join(target_dir, fname)
    file.save(target)

    doc = ComplianceDocument(
        title=request.form.get('title') or name,
        doc_type=request.form.get('doc_type', 'license'),
        file_path=os.path.relpath(target, start=os.path.dirname(target_dir)),
        file_size=size,
        mime_type=file.mimetype,
        version=request.form.get('version', '1.0'),
        issued_by=request.form.get('issued_by', ''),
        confidential=True,
    )
    db.session.add(doc); db.session.commit()
    flash(f'Uploaded {fname} ({size//1024} KB)')
    return redirect(url_for('compliance.overview'))


@compliance_bp.route('/export.csv')
@admin_only
def export_csv():
    """One CSV with three sections: licenses, deadlines, documents."""
    buf = io.StringIO()
    w = csv.writer(buf)

    w.writerow(['# LICENSES'])
    w.writerow(['name','type','jurisdiction','authority','number','status',
                'issued','expires','days_left','cost','currency','notes'])
    for l in License.query.order_by(License.expiry_date.asc()).all():
        w.writerow([l.name, l.license_type, l.jurisdiction, l.authority, l.license_number,
                    l.status, l.issued_date, l.expiry_date, l.days_to_expiry,
                    l.renewal_cost, l.currency, l.notes])

    w.writerow([])
    w.writerow(['# DEADLINES'])
    w.writerow(['title','category','due','days_left','responsible','cost','currency','status','notes'])
    for d in Deadline.query.order_by(Deadline.due_date.asc()).all():
        w.writerow([d.title, d.category, d.due_date, d.days_left,
                    d.responsible, d.cost_estimate, d.currency, d.status, d.notes])

    w.writerow([])
    w.writerow(['# DOCUMENTS'])
    w.writerow(['title','type','version','issued_by','file_path','size_bytes','uploaded_at'])
    for doc in ComplianceDocument.query.order_by(ComplianceDocument.uploaded_at.desc()).all():
        w.writerow([doc.title, doc.doc_type, doc.version, doc.issued_by,
                    doc.file_path, doc.file_size, doc.uploaded_at])

    data = buf.getvalue().encode('utf-8')
    return send_file(io.BytesIO(data),
                     mimetype='text/csv',
                     as_attachment=True,
                     download_name=f'aflathoon-compliance-{date.today().isoformat()}.csv')


@compliance_bp.route('/api/upcoming')
@admin_only
def upcoming_api():
    today = date.today()
    soon = today + timedelta(days=30)
    return jsonify({
        'licenses': [{'name': l.name, 'expiry': str(l.expiry_date),
                      'days': l.days_to_expiry, 'urgency': l.urgency}
                     for l in License.query.all()
                     if l.expiry_date and l.expiry_date <= soon],
        'deadlines': [{'title': d.title, 'due': str(d.due_date),
                       'days': d.days_left, 'urgency': d.urgency}
                      for d in Deadline.query.filter_by(status='open').all()
                      if d.due_date <= soon],
    })

#!/usr/bin/env bash
# =============================================================================
# Phase 2.5 — Company Admin Verification
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

echo "== Building company admin verification =="

# --- 1. Extend admin routes ---
python3 - << 'PYEOF'
from pathlib import Path
p = Path.home() / "aflathoon_exchange" / "app" / "routes" / "admin.py"
src = p.read_text()

if "companies_page" in src:
    print("  [skip] company admin routes already present")
else:
    extra = '''

# ------------------------------------------------------------------ companies
@admin_bp.route('/companies')
@admin_required
def companies_page():
    """List companies, filtered by status."""
    from app.models.company import Company

    status_filter = request.args.get('status', 'pending').strip() or 'pending'
    page = max(1, int(request.args.get('page', '1')))
    per_page = min(100, max(10, int(request.args.get('per_page', '25'))))

    q = Company.query
    if status_filter != 'all':
        q = q.filter(Company.status == status_filter)
    q = q.order_by(Company.created_at.desc())

    total = q.count()
    rows = q.offset((page - 1) * per_page).limit(per_page).all()

    counts = {
        'pending':   Company.query.filter_by(status='pending').count(),
        'verified':  Company.query.filter_by(status='verified').count(),
        'rejected':  Company.query.filter_by(status='rejected').count(),
        'suspended': Company.query.filter_by(status='suspended').count(),
        'all':       Company.query.count(),
    }

    return render_template(
        'admin/companies.html',
        rows=rows, page=page, per_page=per_page, total=total,
        pages=(total + per_page - 1) // per_page,
        status_filter=status_filter, counts=counts,
    )


@admin_bp.route('/companies/<int:cid>')
@admin_required
def company_detail(cid):
    from app.models.company import Company
    from app.models.user import User

    company = Company.query.get_or_404(cid)
    users = User.query.filter_by(company_id=cid).all()
    return render_template('admin/company_detail.html', company=company, users=users)


@admin_bp.route('/companies/<int:cid>/verify', methods=['POST'])
@admin_required
def company_verify(cid):
    from app.models.company import Company
    from app.models.user import User
    from datetime import datetime

    company = Company.query.get_or_404(cid)
    company.status = 'verified'
    company.verified_at = datetime.utcnow()
    company.verified_by_id = current_user.id
    company.rejection_reason = None

    # Upgrade KYC for all users of this company
    users = User.query.filter_by(company_id=cid).all()
    for u in users:
        u.kyc_status = 'verified'
        u.kyc_tier = 2

    db.session.commit()
    flash(f"Company '{company.name}' verified. {len(users)} user(s) upgraded to KYC tier 2.")
    return redirect(url_for('admin.company_detail', cid=cid))


@admin_bp.route('/companies/<int:cid>/reject', methods=['POST'])
@admin_required
def company_reject(cid):
    from app.models.company import Company
    company = Company.query.get_or_404(cid)
    reason = (request.form.get('reason') or '').strip() or 'Not specified'

    company.status = 'rejected'
    company.rejection_reason = reason
    company.verified_at = None
    company.verified_by_id = current_user.id

    db.session.commit()
    flash(f"Company '{company.name}' rejected.")
    return redirect(url_for('admin.company_detail', cid=cid))


@admin_bp.route('/companies/<int:cid>/suspend', methods=['POST'])
@admin_required
def company_suspend(cid):
    from app.models.company import Company
    company = Company.query.get_or_404(cid)
    company.status = 'suspended'
    db.session.commit()
    flash(f"Company '{company.name}' suspended.")
    return redirect(url_for('admin.company_detail', cid=cid))


@admin_bp.route('/companies/<int:cid>/reinstate', methods=['POST'])
@admin_required
def company_reinstate(cid):
    from app.models.company import Company
    company = Company.query.get_or_404(cid)
    company.status = 'pending'
    company.rejection_reason = None
    db.session.commit()
    flash(f"Company '{company.name}' moved back to pending.")
    return redirect(url_for('admin.company_detail', cid=cid))


# ------------------------------------------------------------------ stats update
@admin_bp.route('/api/company-stats')
@admin_required
def company_stats():
    from app.models.company import Company
    return jsonify({
        'pending':  Company.query.filter_by(status='pending').count(),
        'verified': Company.query.filter_by(status='verified').count(),
        'rejected': Company.query.filter_by(status='rejected').count(),
        'total':    Company.query.count(),
    })
'''
    p.write_text(src + extra)
    print("  [add ] company admin routes")
PYEOF

# --- 2. Admin companies list template ---
cat > app/templates/admin/companies.html << 'HTMLEOF'
{% extends "base.html" %}
{% block title %}Companies — Aflathoon{% endblock %}
{% block search_placeholder %}Search companies…{% endblock %}

{% block content %}
<h1 class="afl-page-title">Companies</h1>

<div class="tabs" style="margin-bottom:1rem">
  <a href="/admin/">Overview</a>
  <a href="/admin/blotter">Blotter</a>
  <a href="/admin/positions">Positions</a>
  <a href="/admin/users">Users</a>
  <a class="active" href="/admin/companies">Companies</a>
</div>

<div class="afl-row afl-row-3" style="margin-bottom:1rem">
  <div class="afl-card">
    <div class="afl-k">Pending</div>
    <div class="afl-v big" style="color:var(--amber)">{{ counts.pending }}</div>
  </div>
  <div class="afl-card">
    <div class="afl-k">Verified</div>
    <div class="afl-v big" style="color:var(--green)">{{ counts.verified }}</div>
  </div>
  <div class="afl-card">
    <div class="afl-k">Rejected</div>
    <div class="afl-v big" style="color:var(--red)">{{ counts.rejected }}</div>
  </div>
</div>

<div class="tabs" style="margin-bottom:.8rem">
  <a class="{{ 'active' if status_filter == 'pending' }}"   href="?status=pending">Pending ({{ counts.pending }})</a>
  <a class="{{ 'active' if status_filter == 'verified' }}"  href="?status=verified">Verified ({{ counts.verified }})</a>
  <a class="{{ 'active' if status_filter == 'rejected' }}"  href="?status=rejected">Rejected ({{ counts.rejected }})</a>
  <a class="{{ 'active' if status_filter == 'suspended' }}" href="?status=suspended">Suspended ({{ counts.suspended }})</a>
  <a class="{{ 'active' if status_filter == 'all' }}"       href="?status=all">All ({{ counts.all }})</a>
</div>

<div class="afl-card">
  <p style="color:var(--muted);font-size:.85rem;margin-top:0">
    {{ total }} companies · page {{ page }} of {{ pages or 1 }}
  </p>

  <table class="afl-table">
    <tr>
      <th>Name</th>
      <th>Jurisdiction</th>
      <th>Registration #</th>
      <th>Industry</th>
      <th>Users</th>
      <th>Status</th>
      <th>Created</th>
      <th></th>
    </tr>
    {% for c in rows %}
    <tr>
      <td>
        <a href="/admin/companies/{{ c.id }}" style="color:var(--accent);text-decoration:none;font-weight:600">{{ c.name }}</a>
        {% if c.lei_code %}<div style="color:var(--muted);font-size:.72rem">LEI {{ c.lei_code }}</div>{% endif %}
      </td>
      <td>{{ c.jurisdiction or '—' }}</td>
      <td>{{ c.registration_number or '—' }}</td>
      <td>{{ c.industry or '—' }}</td>
      <td>{{ c.user_count }}</td>
      <td><span class="afl-status {% if c.status == 'verified' %}confirmed{% elif c.status == 'pending' %}staged{% else %}failed{% endif %}">{{ c.status }}</span></td>
      <td>{{ c.created_at.strftime('%Y-%m-%d') if c.created_at else '—' }}</td>
      <td><a class="afl-link" href="/admin/companies/{{ c.id }}">Review →</a></td>
    </tr>
    {% endfor %}
    {% if not rows %}
    <tr><td colspan="8" class="afl-empty">No companies in this state</td></tr>
    {% endif %}
  </table>

  {% if pages > 1 %}
  <div style="display:flex;gap:.4rem;margin:1rem 0;flex-wrap:wrap">
    {% if page > 1 %}<a class="afl-pill" href="?status={{ status_filter }}&page={{ page-1 }}">← prev</a>{% endif %}
    {% for p in range(1, pages + 1) %}
      {% if p == page %}
        <a class="afl-pill" style="background:var(--accent);color:#fff">{{ p }}</a>
      {% elif p <= 3 or p >= pages - 2 or (p >= page - 2 and p <= page + 2) %}
        <a class="afl-pill" href="?status={{ status_filter }}&page={{ p }}">{{ p }}</a>
      {% elif p == 4 and page > 5 %}<span style="color:var(--muted)">…</span>{% endif %}
    {% endfor %}
    {% if page < pages %}<a class="afl-pill" href="?status={{ status_filter }}&page={{ page+1 }}">next →</a>{% endif %}
  </div>
  {% endif %}
</div>
{% endblock %}
HTMLEOF

# --- 3. Company detail template ---
cat > app/templates/admin/company_detail.html << 'HTMLEOF'
{% extends "base.html" %}
{% block title %}{{ company.name }} — Aflathoon{% endblock %}
{% block search_placeholder %}Company details{% endblock %}

{% block content %}
<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem">
  <div>
    <a href="/admin/companies" style="color:var(--accent);text-decoration:none;font-size:.85rem">← Companies</a>
    <h1 class="afl-page-title" style="margin:.3rem 0 0">{{ company.name }}</h1>
    <span class="afl-status {% if company.status == 'verified' %}confirmed{% elif company.status == 'pending' %}staged{% else %}failed{% endif %}" style="margin-top:.4rem;display:inline-block">{{ company.status }}</span>
  </div>
</div>

{% with messages = get_flashed_messages() %}
  {% if messages %}{% for m in messages %}
    <div class="afl-card" style="border-left:3px solid var(--green);padding:.7rem 1rem;margin:1rem 0">{{ m }}</div>
  {% endfor %}{% endif %}
{% endwith %}

<div class="afl-row afl-row-split" style="max-width:1200px;margin-top:1rem">

  <div>
    <div class="afl-card">
      <h3 class="afl-h3">Company details</h3>
      <table class="afl-table">
        <tr><td class="afl-k">Legal name</td><td>{{ company.name }}</td></tr>
        <tr><td class="afl-k">Registration #</td><td>{{ company.registration_number or '—' }}</td></tr>
        <tr><td class="afl-k">Jurisdiction</td><td>{{ company.jurisdiction or '—' }}</td></tr>
        <tr><td class="afl-k">Tax ID / VAT</td><td>{{ company.tax_id or '—' }}</td></tr>
        <tr><td class="afl-k">LEI</td><td>{{ company.lei_code or '—' }}</td></tr>
        <tr><td class="afl-k">Industry</td><td>{{ company.industry or '—' }}</td></tr>
        <tr><td class="afl-k">Website</td><td>{{ company.website or '—' }}</td></tr>
        <tr><td class="afl-k">Contact email</td><td>{{ company.contact_email or '—' }}</td></tr>
        <tr><td class="afl-k">Contact phone</td><td>{{ company.contact_phone or '—' }}</td></tr>
        <tr><td class="afl-k">Address</td><td>
          {% if company.address_line1 %}{{ company.address_line1 }}<br>{% endif %}
          {% if company.address_line2 %}{{ company.address_line2 }}<br>{% endif %}
          {% if company.city %}{{ company.city }}{% if company.postal_code %}, {{ company.postal_code }}{% endif %}<br>{% endif %}
          {{ company.country or '' }}
        </td></tr>
        <tr><td class="afl-k">Created</td><td>{{ company.created_at.strftime('%Y-%m-%d %H:%M') if company.created_at else '—' }}</td></tr>
        {% if company.verified_at %}
        <tr><td class="afl-k">Verified</td><td>{{ company.verified_at.strftime('%Y-%m-%d %H:%M') }}</td></tr>
        {% endif %}
        {% if company.rejection_reason %}
        <tr><td class="afl-k">Rejection reason</td><td style="color:var(--red-fg)">{{ company.rejection_reason }}</td></tr>
        {% endif %}
      </table>
    </div>

    <div class="afl-card">
      <h3 class="afl-h3">Users in this company ({{ users|length }})</h3>
      <table class="afl-table">
        <tr><th>Username</th><th>Email</th><th>KYC</th><th>Admin</th><th>Last login</th></tr>
        {% for u in users %}
        <tr>
          <td>{{ u.username }}</td>
          <td>{{ u.email }}</td>
          <td><span class="afl-status {% if u.kyc_status == 'verified' %}confirmed{% elif u.kyc_status == 'pending' %}staged{% else %}failed{% endif %}">{{ u.kyc_status }}</span></td>
          <td>{{ 'yes' if u.is_admin else '—' }}</td>
          <td>{{ u.last_login.strftime('%Y-%m-%d %H:%M') if u.last_login else 'never' }}</td>
        </tr>
        {% endfor %}
        {% if not users %}
        <tr><td colspan="5" class="afl-empty">No users attached</td></tr>
        {% endif %}
      </table>
    </div>
  </div>

  <div>
    <div class="afl-card">
      <h3 class="afl-h3">Actions</h3>

      {% if company.status != 'verified' %}
      <form method="post" action="/admin/companies/{{ company.id }}/verify" style="margin-bottom:.6rem">
        <button class="afl-btn" style="width:100%;background:var(--green)">✓ Approve company</button>
      </form>
      {% endif %}

      {% if company.status == 'pending' %}
      <form method="post" action="/admin/companies/{{ company.id }}/reject" style="margin-bottom:.6rem">
        <input name="reason" placeholder="Rejection reason" class="afl-in" style="width:100%;margin-bottom:.4rem">
        <button class="afl-btn" style="width:100%;background:var(--red)">✗ Reject company</button>
      </form>
      {% endif %}

      {% if company.status == 'verified' %}
      <form method="post" action="/admin/companies/{{ company.id }}/suspend" style="margin-bottom:.6rem">
        <button class="afl-btn secondary" style="width:100%">⏸ Suspend</button>
      </form>
      {% endif %}

      {% if company.status in ('rejected', 'suspended') %}
      <form method="post" action="/admin/companies/{{ company.id }}/reinstate">
        <button class="afl-btn secondary" style="width:100%">↺ Move back to pending</button>
      </form>
      {% endif %}
    </div>

    <div class="afl-card">
      <h3 class="afl-h3">Verification status</h3>
      <div class="afl-k" style="margin-top:.5rem">Current status</div>
      <div style="color:var(--text)">{{ company.status }}</div>
      <div class="afl-k" style="margin-top:.6rem">Verified by</div>
      <div style="color:var(--text)">
        {% if company.verified_by %}{{ company.verified_by.username }}{% else %}—{% endif %}
      </div>
      <div class="afl-k" style="margin-top:.6rem">Verified at</div>
      <div style="color:var(--text)">
        {% if company.verified_at %}{{ company.verified_at.strftime('%Y-%m-%d %H:%M') }}{% else %}—{% endif %}
      </div>
    </div>
  </div>
</div>
{% endblock %}
HTMLEOF

echo "  [add ] templates"

# --- 4. Add Companies link to sidebar (base.html) ---
if ! grep -q 'href="/admin/companies"' app/templates/base.html; then
    python3 - << 'PYEOF'
from pathlib import Path
p = Path.home() / "aflathoon_exchange" / "app" / "templates" / "base.html"
src = p.read_text()
needle = '<a href="/admin/users"'
if needle in src:
    # Insert a Companies link right after Users link line
    lines = src.split('\n')
    out = []
    for line in lines:
        out.append(line)
        if '<a href="/admin/users"' in line and '/admin/companies' not in src:
            indent = line[:len(line) - len(line.lstrip())]
            out.append(f'{indent}<a href="/admin/companies"     class="{{{{ \'active\' if path.startswith(\'/admin/companies\') }}}}">   <span class="ico">🏢</span> Companies</a>')
    p.write_text('\n'.join(out))
    print("  [add ] sidebar Companies link")
else:
    print("  [skip] /admin/users link not found in sidebar")
PYEOF
else
    echo "  [skip] sidebar Companies link already present"
fi

# --- 5. Verify syntax ---
echo ""
echo "== Syntax check =="
python3 -c "import ast; ast.parse(open('app/routes/admin.py').read()); print('admin.py OK')"
python3 -c "import ast; ast.parse(open('app/templates/base.html').read()) if False else None; print('base.html skipped (jinja)')"

echo ""
echo "== DONE =="
echo "Restart the server:"
echo "  pkill -f 'python app.py'; python app.py"
echo "Then visit: http://127.0.0.1:9105/admin/companies"
echo ""

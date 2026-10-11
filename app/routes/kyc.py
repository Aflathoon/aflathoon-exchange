import os
from datetime import datetime, date
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, current_app)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app import db
from app.models.kyc_submission import KYCSubmission
from app.services import audit


kyc_bp = Blueprint('kyc', __name__)

ALLOWED_EXT = {'.pdf', '.png', '.jpg', '.jpeg'}
MAX_BYTES = 8 * 1024 * 1024   # 8 MB per file


def _uploads_dir():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    d = os.path.join(root, 'compliance', 'kyc_uploads')
    os.makedirs(d, exist_ok=True)
    return d


def _save_file(file, prefix):
    if not file or not file.filename:
        return None
    name = secure_filename(file.filename)
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f'File type {ext} not allowed')
    file.seek(0, os.SEEK_END); size = file.tell(); file.seek(0)
    if size > MAX_BYTES:
        raise ValueError(f'File too large (max {MAX_BYTES // (1024*1024)} MB)')
    stamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    uid = current_user.id
    fname = f"{prefix}-u{uid}-{stamp}{ext}"
    target = os.path.join(_uploads_dir(), fname)
    file.save(target)
    return os.path.relpath(target, start=os.path.dirname(_uploads_dir()))


@kyc_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    last = (KYCSubmission.query
            .filter_by(user_id=current_user.id)
            .order_by(KYCSubmission.submitted_at.desc())
            .first())

    if request.method == 'POST':
        if last and last.status == 'pending':
            flash('You already have a pending submission. Wait for review.')
            return redirect(url_for('kyc.index'))

        try:
            sub = KYCSubmission(
                user_id=current_user.id,
                tier_requested=int(request.form.get('tier_requested') or 2),
                doc_type=request.form.get('doc_type') or 'passport',
                doc_number=(request.form.get('doc_number') or '').strip() or None,
                legal_name=(request.form.get('legal_name') or '').strip() or None,
                nationality=(request.form.get('nationality') or '').strip() or None,
            )
            dob = request.form.get('date_of_birth')
            if dob:
                try:
                    sub.date_of_birth = date.fromisoformat(dob)
                except ValueError:
                    pass

            sub.id_front_path = _save_file(request.files.get('id_front'), 'idfront')
            sub.id_back_path  = _save_file(request.files.get('id_back'),  'idback')
            sub.selfie_path   = _save_file(request.files.get('selfie'),   'selfie')
            sub.proof_of_address_path = _save_file(request.files.get('proof_of_address'), 'poa')

            if not sub.id_front_path:
                flash('ID document (front) is required.')
                return redirect(url_for('kyc.index'))

            db.session.add(sub)
            db.session.commit()

            current_user.kyc_status = 'pending'
            db.session.commit()

            audit.log('kyc.submit', entity=sub,
                      summary=f'KYC submission from {current_user.username}')
            flash('Submission received. Review usually takes 1–2 business days.')
            return redirect(url_for('kyc.index'))

        except ValueError as e:
            flash(str(e))
            return redirect(url_for('kyc.index'))
        except Exception as e:
            current_app.logger.exception('KYC submit failed')
            flash(f'Submission failed: {e}')
            return redirect(url_for('kyc.index'))

    return render_template('kyc/index.html', last=last)

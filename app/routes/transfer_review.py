from sqlalchemy.exc import IntegrityError
from flask import abort, redirect, render_template, request, url_for
from app.extensions import db
from app.models import TransferReviewCase
from app.routes.main import get_current_user, role_required
from app.services import transfer_review as service, staff_roles
from app.routes.admin import admin_bp
from app.routes.staff import staff_bp

@admin_bp.route('/admin/transfer-reviews', methods=['GET','POST'])
@role_required('admin')
def transfer_reviews():
    error=None; found=None
    if request.method=='POST':
        try:
            service.submit(get_current_user(),request.form); db.session.commit()
            return redirect(url_for('admin.transfer_reviews'))
        except (ValueError, IntegrityError) as exc:
            db.session.rollback(); error=str(exc) if isinstance(exc,ValueError) else '資料已被其他操作建立，請重新查詢。'
    elif request.args.get('student_no'):
        try: found=service.find_student(request.args.get('student_no')) or False
        except ValueError as exc: error=str(exc)
    cases=TransferReviewCase.query.order_by(TransferReviewCase.id.desc()).all()
    return render_template('transfer_reviews.html',user=get_current_user(),cases=cases,error=error,found=found,query=request.args.get('student_no',''),admin=True), (400 if error else 200)

@admin_bp.post('/admin/transfer-reviews/<int:case_id>/resubmit')
@role_required('admin')
def transfer_review_resubmit(case_id):
    return _transition(case_id,'resubmit')

@admin_bp.post('/admin/transfer-reviews/<int:case_id>/withdraw')
@role_required('admin')
def transfer_review_withdraw(case_id):
    return _transition(case_id, 'withdraw')


@staff_bp.get('/staff/transfer-reviews')
@role_required('staff')
def transfer_reviews():
    user=get_current_user()
    if not (staff_roles.is_assistant(user) or staff_roles.is_chief(user)): abort(403)
    actionable_status = 'assistant_pending' if staff_roles.is_assistant(user) else 'chief_pending'
    cases = TransferReviewCase.query.order_by(TransferReviewCase.id.desc()).all()
    return render_template('transfer_reviews.html', user=user, cases=cases, admin=False,
                           actionable_status=actionable_status)

@staff_bp.post('/staff/transfer-reviews/<int:case_id>/<action>')
@role_required('staff')
def transfer_review_action(case_id,action):
    if action not in ('confirm','return'): abort(404)
    return _transition(case_id,action)

def _transition(case_id,action):
    try:
        service.transition(case_id,get_current_user(),action,request.form); db.session.commit()
    except PermissionError: db.session.rollback(); abort(403)
    except service.Conflict as exc: db.session.rollback(); abort(409,description=str(exc))
    except ValueError as exc: db.session.rollback(); abort(400,description=str(exc))
    return redirect(url_for('admin.transfer_reviews' if action in ('resubmit', 'withdraw') else 'staff.transfer_reviews'))

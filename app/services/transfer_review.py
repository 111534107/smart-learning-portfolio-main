"""核定轉科案件：獨立於抵免，狀態異動與事件同一交易。"""
from sqlalchemy import func, update
from app.extensions import db
from app.models import User, StudentProfile, TransferReviewCase, TransferReviewEvent, AuditLog, Notification
from app.services import staff_roles, transfer_student_service

class Conflict(ValueError):
    pass

def fields(form):
    name=(form.get('class_name') or '').strip()
    try: year=int(form.get('admission_year') or 0)
    except ValueError: year=0
    if not name or len(name)>50 or not 90<=year<=200:
        raise ValueError('請填班級與有效入學學年度。')
    return name, year

def event(case, actor, action, reason=''):
    db.session.add(TransferReviewEvent(case_id=case.id, actor_id=actor.id, action=action, reason=reason, class_name=case.class_name, admission_year=case.admission_year))
    db.session.add(AuditLog(user_id=actor.id, action='transfer_review.'+action, target_type='transfer_review_case', target_id=case.id, detail_json={}))

def notify_staff(case, titles, message):
    recipients = User.query.filter(
        User.role == 'staff', User.is_active.is_(True), User.job_title.in_(titles),
    ).all()
    for person in recipients:
        db.session.add(Notification(
            recipient_id=person.id,
            message=message,
            link=f'/staff/transfer-reviews#case-{case.id}',
            notify_key=f'transfer_review:{case.id}:{case.version}',
        ))


def find_student(number):
    number=(number or '').strip()
    if not transfer_student_service.STUDENT_NO.fullmatch(number):
        raise ValueError('學號請填 9 碼數字（例如 113534105）。')
    profiles=StudentProfile.query.filter(func.lower(StudentProfile.student_no)==number.lower()).all()
    accounts=User.query.filter(func.lower(User.username)==number.lower()).all()
    if len(profiles)>1 or len(accounts)>1:
        raise Conflict('學號對應多個帳號，請先人工處理。')
    profile=profiles[0] if profiles else None
    account=accounts[0] if accounts else None
    if profile and account and profile.user_id != account.id:
        raise Conflict('學號對應多個帳號，請先人工處理。')
    user=profile.user if profile else account
    if user and (user.role != 'student' or not user.student_profile):
        raise Conflict('帳號資料不完整或非學生，請先人工處理。')
    return user

def submit(actor, form):
    number=(form.get('student_no') or '').strip()
    user=find_student(number)
    class_name, year=fields(form)
    if not user:
        if not form.get('password'):
            raise ValueError('新帳號請設定起始密碼。')
        new_form = form.to_dict() if hasattr(form, 'to_dict') else dict(form)
        new_form['student_no'] = number
        user=transfer_student_service.create(actor, new_form, create_credit=False)
    if TransferReviewCase.query.filter_by(open_key=user.id).first():
        raise Conflict('此學生已有未結案案件。')
    previous=TransferReviewCase.query.filter_by(student_id=user.id, status='closed').order_by(TransferReviewCase.id.desc()).first()
    case=TransferReviewCase(student_id=user.id, status='assistant_pending', open_key=user.id, class_name=class_name, admission_year=year, previous_case_id=previous.id if previous else None)
    db.session.add(case); db.session.flush(); event(case, actor, 'submitted')
    notify_staff(case, staff_roles.ASSISTANT_TITLES + staff_roles.CHIEF_TITLES,
                 '有轉科帳號案件送核，請到轉科核對案件查看。')
    return case

def transition(case_id, actor, action, form):
    from app.services.staff_roles import is_assistant, is_chief
    if action=='resubmit' and actor.role=='admin':
        expected, target='returned','assistant_pending'; values=dict(zip(('class_name','admission_year'),fields(form))); values.update(assistant_id=None,chief_id=None)
    elif action == 'withdraw' and actor.role == 'admin':
        expected = ('assistant_pending', 'chief_pending', 'returned')
        target, values = 'withdrawn', {'open_key': None}
    elif action=='confirm' and is_assistant(actor):
        expected, target='assistant_pending','chief_pending'; values={'assistant_id':actor.id}
    elif action=='confirm' and is_chief(actor):
        expected, target='chief_pending','closed'; values={'chief_id':actor.id,'open_key':None}
    elif action=='return' and (is_assistant(actor) or is_chief(actor)):
        expected, target=('assistant_pending' if is_assistant(actor) else 'chief_pending'),'returned'; values={}
    else:
        raise PermissionError()
    reason=(form.get('reason') or '').strip()
    if action in ('return', 'withdraw') and (not reason or len(reason) > 2000):
        raise ValueError('退回或撤回時請填原因，最多 2000 字。')
    try:
        version=int(form.get('version') or 0)
    except ValueError:
        version=0
    if version < 1:
        raise Conflict('案件版本無效，請重新整理。')
    values['status']=target
    values['version']=TransferReviewCase.version + 1
    result=db.session.execute(update(TransferReviewCase).where(TransferReviewCase.id==case_id,TransferReviewCase.status.in_(expected if isinstance(expected, tuple) else (expected,)),TransferReviewCase.version==version).values(**values).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise Conflict('案件狀態已變更或不允許此操作。')
    db.session.expire_all()
    case=db.session.get(TransferReviewCase,case_id)
    if target=='closed':
        case.student.student_profile.class_name=case.class_name
        case.student.student_profile.admission_year=case.admission_year
    event(case, actor, action, reason if action in ('return', 'withdraw') else '')
    if action == 'resubmit':
        notify_staff(case, staff_roles.ASSISTANT_TITLES + staff_roles.CHIEF_TITLES,
                     '有轉科帳號案件更正後重送，請到轉科核對案件查看。')
    elif target == 'chief_pending':
        notify_staff(case, staff_roles.CHIEF_TITLES, '科助已核對轉科案件，待主任確認。')
    return case

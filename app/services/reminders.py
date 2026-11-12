"""各學期預警與檢核日期倒數的站內通知＋電子郵件（2026-11-12）。

原本這兩項只在畫面上即時算出來，沒有通知。現在畢業缺口同步（graduation_case_service.sync_student，
學生確認成績、抵免、管理員「重新對照全科」都會跑）最後順便檢查：
- 各學期預警：某學期出現「要注意」或「請找導師討論」，通知學生與導師；同一學期同一等級只通知一次。
- 檢核日期倒數：離檢核日 30 天內、7 天內、1 天內（含當天）各提醒學生一次；日期改了會重新提醒。
用 notifications.notify_key 去重。只 flush，不 commit。
"""

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Notification
from app.services import email_notify

COUNTDOWN_BUCKETS = (1, 7, 30)
STUDENT_LINK = "/student/graduation-check"


def _teacher_link(student):
    return f"/teacher/students/{student.id}"


def _post(user, key, message, link, kind):
    """同一人同一鍵只建一筆通知；新建時一起寄信。回傳是否新建。"""
    if Notification.query.filter_by(recipient_id=user.id, notify_key=key).first() is not None:
        return False
    try:
        with db.session.begin_nested():
            db.session.add(Notification(recipient_id=user.id, notify_key=key, message=message[:255], link=link))
            db.session.flush()
    except IntegrityError:  # 並行同步已建過
        return False
    email_notify.notify(user, kind)
    return True


def sync(student, stage, advisors, today=None, curriculum=None):
    from app.services import check_dates, semester_warning
    created = 0
    warnings = semester_warning.build(student, today=today, curriculum=curriculum)
    for term in warnings.get("terms", []):
        level = term.get("level")
        if level not in ("high", "watch"):
            continue
        key = f"semwarn:{student.id}:{term['label']}:{level}"
        message = f"各學期預警：{term['label']}有新的提醒，請查看。"
        if _post(student, key, message, STUDENT_LINK, "semester_warning"):
            created += 1
        for teacher in advisors:
            if _post(teacher, key, f"各學期預警：{student.display_name} {term['label']}有新的提醒。",
                     _teacher_link(student), "semester_warning"):
                created += 1
    countdown = check_dates.countdown(stage, today=today)
    if countdown and countdown.get("days") is not None and countdown["days"] >= 0:
        days = countdown["days"]
        bucket = next((b for b in COUNTDOWN_BUCKETS if days <= b), None)
        if bucket is not None:
            key = f"countdown:{countdown['date'].isoformat()}:{bucket}"
            when = "今天" if days == 0 else f"還有 {days} 天"
            if _post(student, key, f"{countdown['label']}{when}，請登入確認資料。", STUDENT_LINK, "check_countdown"):
                created += 1
    return created

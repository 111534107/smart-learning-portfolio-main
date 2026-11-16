"""二技公告（UC-25）：擬稿、發布、下架、已讀、截止日、導師提醒。

- 截止日一律由招生資料 Agent 核准的日程（admission_schedule.load_schedule）帶出；
  2026-11-09 使用者：「不是阿agent做辛酸的嗎？讓他去查阿，我還要人工改喔」——不提供人工輸入。
  日程裡找不到「寄送備審」項目時寫「簡章未載明」。
- 未讀提示沿用站內通知（Notification.link 指向公告內容頁），導覽列「通知」數字不用另做。
"""
from datetime import date, datetime, timezone

from app.extensions import db
from app.models import (Announcement, AnnouncementRead, AuditLog, Notification, StudentTarget, User)
from app.services.admission_schedule import CHANNEL_LABELS, load_schedule
from app.services.journey_service import current_grade
from app.services.teacher_scope import students_for_teacher

READER_ROLES = ("student", "teacher", "staff")
SEND_REVIEW_KEYWORD = "寄送備審"
NOT_STATED = "簡章未載明"


def _now():
    return datetime.now(timezone.utc)


def _today():
    return date.today()


def announcement_url(announcement):
    return f"/announcements/{announcement.id}"


def _md(value):
    return f"{value.month}/{value.day}"


def _span(start, end):
    if end is None or end.date() == start.date():
        return _md(start)
    return f"{_md(start)}–{_md(end)}"


def _log(actor, action, announcement, **detail):
    db.session.add(AuditLog(user_id=actor.id, action=action, target_type="announcement", target_id=announcement.id,
                            detail_json={"title": announcement.title, **detail}))


# ---- 管理員 ----

def draft_from_schedule(channel, year, actor):
    """依已核准的日程擬一則公告草稿；同管道同學年度已有草稿就更新它。"""
    events = load_schedule().get((channel, year), [])
    label = CHANNEL_LABELS.get(channel, channel)
    title = f"{year} 學年度{label}招生日程公告"
    lines = [f"{year} 學年度{label}的招生日程已公告，請依時程準備。", ""]
    lines += [f"・{event['name']}：{_span(event['start'], event['end'])}" for event in events]
    if not any(SEND_REVIEW_KEYWORD in event["name"] for event in events):
        lines.append(f"・寄送備審資料：{NOT_STATED}")
    body = "\n".join(lines)
    draft = Announcement.query.filter_by(kind="admission", channel=channel, admission_year=year, status="draft").first()
    if draft is None:
        draft = Announcement(kind="admission", channel=channel, admission_year=year, created_by=actor.id)
        db.session.add(draft)
    draft.title, draft.body = title, body
    db.session.commit()
    return draft


def create_manual(title, body, audience, actor):
    roles = [role for role in READER_ROLES if role in set(audience)]
    if not title.strip() or not roles:
        raise ValueError("標題和對象都要填")
    announcement = Announcement(kind="admission", title=title.strip(), body=body.strip(), audience=",".join(roles),
                                created_by=actor.id)
    db.session.add(announcement)
    db.session.commit()
    return announcement


def publish(announcement, actor, now=None):
    """發布草稿，替對象角色每位啟用中的帳號建一則站內通知；回傳通知數。"""
    if announcement.status != "draft":
        raise ValueError("只有草稿可以發布")
    announcement.status = "published"
    announcement.published_by, announcement.published_at = actor.id, now or _now()
    roles = [role for role in READER_ROLES if role in announcement.audience_roles]
    recipients = User.query.filter(User.role.in_(roles), User.is_active.is_(True)).all()
    for user in recipients:
        db.session.add(Notification(recipient_id=user.id, message=f"二技公告：{announcement.title}"[:255],
                                    link=announcement_url(announcement)))
    _log(actor, "announcement.publish", announcement, recipients=len(recipients))
    db.session.commit()
    return len(recipients)


def withdraw(announcement, actor, now=None):
    if announcement.status != "published":
        raise ValueError("只有已發布的公告可以下架")
    announcement.status = "withdrawn"
    announcement.withdrawn_by, announcement.withdrawn_at = actor.id, now or _now()
    _log(actor, "announcement.withdraw", announcement)
    db.session.commit()


# ---- 閱讀端 ----

def visible_for(user):
    if user.role not in READER_ROLES:
        return []
    rows = Announcement.query.filter_by(status="published").order_by(Announcement.published_at.desc(),
                                                                      Announcement.id.desc()).all()
    return [row for row in rows if user.role in row.audience_roles]


def can_read(user, announcement):
    return announcement is not None and announcement.status == "published" and user.role in announcement.audience_roles


def unread_ids(user, announcements):
    ids = [row.id for row in announcements]
    if not ids:
        return set()
    read = {row.announcement_id for row in AnnouncementRead.query.filter(
        AnnouncementRead.user_id == user.id, AnnouncementRead.announcement_id.in_(ids))}
    return set(ids) - read


def mark_read(announcement, user, now=None):
    now = now or _now()
    if not AnnouncementRead.query.filter_by(announcement_id=announcement.id, user_id=user.id).first():
        db.session.add(AnnouncementRead(announcement_id=announcement.id, user_id=user.id, read_at=now))
    for note in Notification.query.filter_by(recipient_id=user.id, link=announcement_url(announcement), read_at=None):
        note.read_at = now
    db.session.commit()


def key_dates(announcement):
    """公告對應管道、學年度的重要日期（即時讀已核准日程）；手動公告沒有。"""
    if not announcement.channel or announcement.admission_year is None:
        return []
    events = load_schedule().get((announcement.channel, announcement.admission_year), [])
    return [{"name": event["name"], "start": event["start"], "end": event["end"], "span": _span(event["start"], event["end"]),
             "is_send_review": SEND_REVIEW_KEYWORD in event["name"]} for event in events]


def send_review_deadline(today=None):
    """最新一則已發布二技公告的寄送備審截止日；沒有公告或已過截止回傳 None。"""
    today = today or _today()
    latest = (Announcement.query.filter(Announcement.status == "published", Announcement.channel.isnot(None),
                                        Announcement.admission_year.isnot(None))
              .order_by(Announcement.published_at.desc(), Announcement.id.desc()).first())
    if latest is None:
        return None
    item = next((row for row in key_dates(latest) if row["is_send_review"]), None)
    if item is None:
        return {"announcement": latest, "deadline": None, "label": NOT_STATED}
    deadline = item["end"] or item["start"]
    if deadline.date() < today:
        return None
    return {"announcement": latest, "deadline": deadline, "label": _md(deadline)}


# ---- 導師 ----

def teacher_targets(teacher, today=None):
    """導師自己班上四、五年級的學生（10-10 使用者決定），附目標校系數。"""
    today = today or _today()
    rows = []
    for student in students_for_teacher(teacher):
        grade = current_grade(student.student_profile.admission_year, today)
        if grade in (4, 5):
            rows.append({"student": student, "grade": grade,
                         "target_count": StudentTarget.query.filter_by(student_id=student.id).count()})
    return rows


def remind_students(announcement, teacher, today=None):
    rows = teacher_targets(teacher, today)
    if not rows:
        raise ValueError("目前沒有您帶的四、五年級學生")
    message = f"{teacher.display_name}老師提醒你看二技公告：{announcement.title}"[:255]
    for row in rows:
        db.session.add(Notification(recipient_id=row["student"].id, message=message, link=announcement_url(announcement)))
    _log(teacher, "announcement.remind", announcement, student_ids=[row["student"].id for row in rows])
    db.session.commit()
    return len(rows)


def home_summary(user):
    """首頁用：最新一則看得到的公告、是否未讀；科辦另附寄送備審截止資訊。

    科辦首頁的截止卡與公告列都會用到，同一次請求只查一次（存在 flask.g）。"""
    from flask import g, has_request_context
    key = ("announcement_home", user.id)
    cache = g.setdefault("_announcement_home", {}) if has_request_context() else {}
    if key not in cache:
        rows = visible_for(user)
        latest = rows[0] if rows else None
        cache[key] = {"latest": latest, "unread": bool(latest and unread_ids(user, [latest])),
                      "deadline": send_review_deadline() if user.role == "staff" else None}
    return cache[key]

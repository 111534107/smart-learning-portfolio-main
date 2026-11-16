"""備審時間線的行事曆訂閱（.ics，2026-11-12）。

每位學生一條私密網址（users.calendar_token），在 Google 日曆「從網址新增」貼上即可，之後自動更新
（Google 大約數小時到一天重抓一次）。不需要 Google 權限、不存學生的 Google 權杖。
內容：二技技優甄審最新日程、目標校系各管道日程（重複的只列一次）、教務處兩次畢業檢核日期。
只放日程名稱與官方連結，不放成績或個資。提醒時間由學生在日曆裡自己設定。
"""

import secrets
from datetime import datetime, timedelta, timezone

from app.extensions import db

TAIPEI = timedelta(hours=8)
PRODID = "-//資管科智慧學習歷程系統//備審時間線//ZH-TW"


def ensure_token(user):
    if not user.calendar_token:
        user.calendar_token = secrets.token_urlsafe(24)
    return user.calendar_token


def reset_token(user):
    user.calendar_token = secrets.token_urlsafe(24)
    return user.calendar_token


def find_student(token):
    from app.models import User
    if not token or len(token) > 64:
        return None
    user = User.query.filter_by(calendar_token=token).first()
    if user is None or user.role != "student" or not user.is_active:
        return None
    return user


def collect_events(student):
    """回傳 [{uid, name, start, end, all_day, description, url}]，時間為台灣時間。"""
    from app.models import StudentTarget
    from app.services import check_dates
    from app.services.admission_schedule import latest_timeline, timeline

    events, seen = [], set()

    def add_timeline(tl, prefix):
        if not tl:
            return
        key = (tl["channel"], tl["year"])
        if key in seen:
            return
        seen.add(key)
        note = "（去年日程，僅供參考）" if tl.get("reference") else ""
        for index, event in enumerate(tl["events"]):
            events.append({
                "uid": f"adm-{tl['channel']}-{tl['year']}-{index}",
                "name": f"{prefix}{event['name']}{note}",
                "start": event["start"], "end": event["end"], "all_day": False,
                "description": event.get("note") or "", "url": event.get("source") or "",
            })

    add_timeline(latest_timeline("skill_review"), "二技技優甄審：")
    targets = StudentTarget.query.filter_by(student_id=student.id).order_by(StudentTarget.selected_at).all()
    for target in targets:
        tl = timeline(target.program)
        if tl:
            add_timeline(tl, f"{tl['channel_label']}：")
    dates = check_dates.dates()
    for name in ("first", "second"):
        when = dates.get(name)
        if when:
            events.append({"uid": f"gradcheck-{name}-{when.isoformat()}", "name": f"畢業檢核：{check_dates.LABELS[name]}",
                           "start": datetime(when.year, when.month, when.day), "end": None, "all_day": True,
                           "description": "教務處畢業資格檢核，請先確認成績與證照都已上傳。", "url": ""})
    return events


def _escape(text):
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _utc(local):
    return (local - TAIPEI).strftime("%Y%m%dT%H%M%SZ")


def _fold(line):
    """RFC 5545：每行最多 75 個位元組，續行以空白開頭。"""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, current = [], b""
    for char in line:
        encoded = char.encode("utf-8")
        if len(current) + len(encoded) > (75 if not parts else 74):
            parts.append(current.decode("utf-8"))
            current = b""
        current += encoded
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def build_ics(student, events=None, now=None):
    events = collect_events(student) if events is None else events
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "X-WR-CALNAME:資管科備審時間線", "X-WR-TIMEZONE:Asia/Taipei", "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
             "X-PUBLISHED-TTL:PT12H"]
    for event in events:
        lines += ["BEGIN:VEVENT", f"UID:{event['uid']}-{student.id}@ukn-portfolio", f"DTSTAMP:{stamp}"]
        if event["all_day"]:
            day = event["start"].date()
            lines += [f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
                      f"DTEND;VALUE=DATE:{(day + timedelta(days=1)).strftime('%Y%m%d')}"]
        else:
            end = event["end"] or event["start"] + timedelta(hours=1)
            lines += [f"DTSTART:{_utc(event['start'])}", f"DTEND:{_utc(end)}"]
        lines.append(f"SUMMARY:{_escape(event['name'])}")
        if event["description"]:
            lines.append(f"DESCRIPTION:{_escape(event['description'])}")
        if event["url"]:
            lines.append(f"URL:{event['url']}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def commit_token(user):
    ensure_token(user)
    db.session.commit()
    return user.calendar_token

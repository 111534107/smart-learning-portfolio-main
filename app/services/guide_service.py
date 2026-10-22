"""學生首頁的引導卡片：一次最多 3 張，每張一兩句話、一個按鈕。

規格：`docs/02_需求與設計/02_設計規格/AI_設計規格_引導卡片與科辦管理員功能清單_2026-10-10.md` 第一節。
- 依年級與學生做了什麼決定；做完的卡片自動消失（不靠「稍後再說」）。
- 「稍後再說」存在登入工作階段裡，隔 SNOOZE_HOURS 小時再出現，不用資料表。
- 文字要短（測試限 40 字內）；想講更多放到「怎麼操作」說明區。
"""

from datetime import datetime, timedelta, timezone

from flask import url_for

from app.models import AuditLog, SourceDocument, StudentTarget
from app.services import student_rules
from app.services.journey_service import build_journey
from app.services.student_progress import student_progress

MAX_CARDS = 3
SNOOZE_HOURS = 24

# 卡片代號白名單：「稍後再說」只接受這些，避免亂寫入工作階段
CARD_IDS = (
    "welcome", "meet-schools", "first-save", "confirm-docs", "upload-grades",
    "each-term", "certificates", "see-requirements", "internship",
    "target-five", "write-bio", "grad-next", "competition", "trim-targets",
)


def _card(card_id, text, button, href, level="info"):
    return {"id": card_id, "text": text, "button": button, "href": href, "level": level}


def _is_snoozed(card_id, snoozed, now):
    stamp = (snoozed or {}).get(card_id)
    if not stamp:
        return False
    try:
        until = datetime.fromisoformat(stamp) + timedelta(hours=SNOOZE_HOURS)
    except ValueError:
        return False
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return until > now


def guide_cards(user, snoozed=None, now=None):
    now = now or datetime.now(timezone.utc)
    journey = build_journey(user)
    totals = journey["totals"]
    grade = journey["current_grade"] or 1
    has_any = sum(totals.values()) > 0
    has_target = StudentTarget.query.filter_by(student_id=user.id).count() > 0
    pending_docs = SourceDocument.query.filter(
        SourceDocument.owner_id == user.id, SourceDocument.status != "confirmed").count()
    progress = student_progress(user)
    welcome_done = AuditLog.query.filter_by(user_id=user.id, action="student.welcome_done").first() is not None
    # 這個年級的資料夾裡有沒有自己新增的經歷（活動、競賽、服務、幹部）
    this_year = next((year for year in journey["years"] if year["grade"] == grade), None)
    year_records = sum(len(this_year["categories"][key]) for key in ("activity", "competition", "service", "leadership")) if this_year else 0

    cards = []
    # 有事才出現的卡片（不分年級）排最前面
    if pending_docs:
        cards.append(_card("confirm-docs", f"你有 {pending_docs} 份上傳的資料還沒確認。", "去確認",
                           url_for("student.learning_profile"), "todo"))

    if grade == 1:
        if not welcome_done:
            cards.append(_card("welcome", "五年的成果，在這裡一次收好。", "30 秒認識系統", url_for("main.student_welcome")))
        if not has_target:
            cards.append(_card("meet-schools", "先看看二技有哪些學校，挑一兩所想去的。", "去看學校", url_for("student.target_list")))
        if not has_any:
            cards.append(_card("first-save", "上課作品、社團、比賽，先存起來就不會忘。", "存第一份成果",
                               url_for("student.learning_profile_upload_page")))
    elif grade == 2:
        if not totals["grades"]:
            cards.append(_card("upload-grades", "學期成績出來了，上傳成績單。", "上傳成績單", url_for("student.learning_profile_upload_page", type="transcript")))
        if not year_records:
            cards.append(_card("each-term", "每學期留一份課程成果。", "新增成果", url_for("student.portfolio_new", category="activity")))
        if not totals["credential"]:
            cards.append(_card("certificates", "有考到證照就先存起來。", "上傳證照", url_for("student.learning_profile_upload_page", type="credential")))
    elif grade == 3:
        if not totals["credential"]:
            cards.append(_card("certificates", "整理你的證照，備審用得到。", "上傳證照", url_for("student.learning_profile_upload_page", type="credential")))
        if not totals["competition"]:
            cards.append(_card("competition", "參加過比賽嗎？記下來。", "新增競賽", url_for("student.portfolio_new", category="competition")))
        if not has_target:
            cards.append(_card("see-requirements", "看看想去的學校，備審要什麼。", "看各校要求", url_for("student.target_list")))
    elif grade == 4:
        if not year_records:
            cards.append(_card("internship", "實習的經驗，現在就整理。", "新增經歷", url_for("student.portfolio_new", category="activity")))
        if not has_target:
            cards.append(_card("see-requirements", "明年就要申請了，先看各校要求。", "看各校要求", url_for("student.target_list")))
    else:
        slots = student_rules.target_slots(user)
        if slots["limit"] is not None and slots["used"] > slots["limit"]:
            cards.append(_card("trim-targets", f"五年級最多留 {slots['limit']} 所，先取消 {slots['used'] - slots['limit']} 所。",
                               "整理目標校系", url_for("student.target_list"), "todo"))
        if not has_target:
            cards.append(_card("target-five", "選出最想申請的學校，最多 5 所。", "選校系", url_for("student.target_list"), "todo"))
        cards.append(_card("grad-next", progress["next"]["text"] + "。", "前往", progress["next"]["href"], "todo"))

    # 沒有成績的非一年級學生，仍以上傳成績單為主
    visible = [card for card in cards if not _is_snoozed(card["id"], snoozed, now)]
    seen, unique = set(), []
    for card in visible:
        if card["id"] not in seen:
            seen.add(card["id"])
            unique.append(card)
    return unique[:MAX_CARDS]

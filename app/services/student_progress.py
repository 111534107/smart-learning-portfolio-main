"""學生主線的四個步驟，以及「下一步該做什麼」。

① 收集資料：至少有一筆已確認的成績（成績單是備審的基礎）
② 選目標校系：選了至少一個
③ 補齊缺件：第一個目標校系的準備度達到 100%
④ 導師確認與下載：第一個目標校系的導師確認狀態為「已確認」

每一步是否完成是各自判斷的；「目前」是第一個還沒完成的步驟。
「下一步」只給一個最該先做的動作，避免學生不知道從哪裡開始。
"""

from flask import url_for

from app.models import SourceDocument, StudentTarget
from app.services.gap_service import ALL_LABELS, analyze_gap
from app.services.journey_service import build_journey
from app.services.package_service import latest_review

STEP_TITLES = ["收集資料", "選目標校系", "補齊缺件", "導師確認與下載"]


def _add_link(category):
    if category in ("grades", "credential"):
        return url_for("student.learning_profile_upload_page",
                       type="transcript" if category == "grades" else "credential")
    return url_for("student.portfolio_new", category=category)


def student_progress(user):
    journey = build_journey(user)
    pending_docs = SourceDocument.query.filter(
        SourceDocument.owner_id == user.id, SourceDocument.status != "confirmed").count()
    target = StudentTarget.query.filter_by(student_id=user.id).order_by(StudentTarget.selected_at, StudentTarget.id).first()
    program = target.program if target else None
    gap = analyze_gap(user, program, journey) if program else None
    review = latest_review(user, program) if program else None

    done = [
        journey["totals"]["grades"] > 0,
        program is not None,
        bool(gap) and gap["readiness"] == 100,
        bool(review) and review.status == "confirmed",
    ]
    gap_url = url_for("student.target_gap", program_id=program.id) if program else url_for("student.target_list")
    hrefs = [url_for("main.student_dashboard"), url_for("student.target_list"), gap_url, gap_url + "#review"]

    current = next((index for index, finished in enumerate(done) if not finished), None)
    steps = [{
        "no": index + 1,
        "title": title,
        "href": hrefs[index],
        "state": "done" if done[index] else ("current" if index == current else "todo"),
    } for index, title in enumerate(STEP_TITLES)]

    if pending_docs:
        action = {"text": f"確認你上傳的 {pending_docs} 份文件", "href": url_for("student.learning_profile")}
    elif not done[0]:
        action = {"text": "上傳成績單，開始整理", "href": url_for("student.learning_profile_upload_page")}
    elif not done[1]:
        action = {"text": "選一個想申請的目標校系", "href": url_for("student.target_list")}
    elif not done[2] and gap["priority_id"]:
        item = next(item for item in gap["items"] if item["id"] == gap["priority_id"])
        category = item["missing"][0]
        action = {"text": f"補上{ALL_LABELS[category]}（{item['name']} 佔 {item['weight']}%）", "href": _add_link(category)}
    elif not review or review.status == "needs_revision":
        action = {"text": "請導師確認備審內容" if not review else "依導師建議修改後再送出", "href": gap_url + "#review"}
    elif review.status == "pending":
        action = {"text": "等待導師確認中，可以先下載草稿", "href": gap_url + "#review"}
    else:
        action = {"text": "下載完整備審資料", "href": gap_url + "#review"}

    return {"steps": steps, "next": action, "program": program}

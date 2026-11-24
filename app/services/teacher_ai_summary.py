"""導師班級資料摘要：只送固定欄位的匿名總數，不傳自由文字或缺曠。"""
from app.models import LearningCourseRecord, CredentialRecord, Portfolio
from app.services import gemini_client


def summarize(students):
    ids = {s.id for s in students}
    def count(model, extra):
        return len({row[0] for row in model.query.with_entities(model.student_id).filter(model.student_id.in_(ids), *extra).distinct().all()})
    stats = {
        "人數": len(ids),
        "有已確認成績的人數": count(LearningCourseRecord, [LearningCourseRecord.confirmation_status == "confirmed"]),
        "有已確認證照的人數": count(CredentialRecord, [CredentialRecord.confirmation_status == "confirmed"]),
        "有已確認經歷的人數": count(Portfolio, [Portfolio.status == "confirmed", Portfolio.deleted_at.is_(None)]),
    }
    local = "；".join(f"{k}：{v}" for k, v in stats.items()) + "。請老師依實際資料核對。"
    if len(ids) < 5:
        return {"mode": "local", "text": local + " 人數較少，僅顯示本機統計。"}
    prompt = "請依下列匿名班級總數提供簡短資料整理建議，不推測個人身分或作出正式判斷：" + local
    try:
        response = gemini_client.chat([{"role": "user", "parts": [{"text": prompt}]}], [], "以繁體中文提出簡短建議，不做正式決定。")
        text = "".join(part.get("text", "") for part in response.get("parts", [])).strip()
        if text:
            return {"mode": "ai", "text": local + "\nAI 建議（僅供參考）：" + text}
    except gemini_client.AIUnavailable:
        pass
    return {"mode": "local", "text": local + " AI 目前無法使用，顯示本機統計。"}

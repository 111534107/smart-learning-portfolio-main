"""用本機規則整理自傳每段的證據、疑點與修改建議。"""

QUESTION_KEYS = ("motivation", "proud", "challenge", "future")

QUESTION_SUGGESTIONS = {
    "motivation": "補上讓你想讀資管的具體契機",
    "proud": "補一段你負責的部分與學到什麼",
    "challenge": "補上遇到的困難、你的做法與結果",
    "future": "補上進二技後想學的內容與目標",
}


def _question_key(title, index):
    title = title or ""
    for words, key in (
        (("動機",), "motivation"),
        (("歷程", "經驗", "成就"), "proud"),
        (("困難", "成長"), "challenge"),
        (("未來", "規劃"), "future"),
    ):
        if any(word in title for word in words):
            return key
    return QUESTION_KEYS[index] if index < len(QUESTION_KEYS) else None


def _short_title(text):
    title = (text or "").split("—", 1)[0].strip()
    return title if len(title) <= 26 else title[:25] + "…"


def review_paragraphs(paragraphs, facts, answers):
    """回傳與 paragraphs 同順序的規則式審查結果，不呼叫 AI。"""
    fact_by_id = {fact["id"]: fact for fact in facts}
    reviews = []
    for index, paragraph in enumerate(paragraphs):
        evidence = []
        for source_id in paragraph.get("sources", []):
            fact = fact_by_id.get(source_id)
            if fact:
                evidence.append({"id": source_id, "evidence_id": fact.get("evidence_id"),
                                 "title": _short_title(fact["text"]), "text": fact["text"]})

        question_key = _question_key(paragraph.get("title"), index)
        unknown = paragraph.get("unknown_sources") or []
        if unknown:
            issue = f"引用了不存在的來源 {'、'.join(unknown)}，請刪掉或改成右側清單裡的編號"
            suggestion = "來源編號只能用系統列出的資料（F1、F2…），不要自己編"
            icon = "⚠"
        elif question_key and not (answers.get(question_key) or "").strip():
            issue = "這題還沒回答"
            suggestion = QUESTION_SUGGESTIONS[question_key]
            icon = "⚠"
        elif not evidence:
            issue = "這段沒有資料佐證，請補上具體經驗"
            suggestion = QUESTION_SUGGESTIONS.get(question_key, "補一段具體的經驗與學到什麼")
            icon = "⚠"
        else:
            issue = "暫未發現資料疑點"
            suggestion = "確認內容和資料一致，再改成自己的話"
            icon = "✓"

        reviews.append({"evidence": evidence, "issue": issue, "suggestion": suggestion, "icon": icon})
    return reviews

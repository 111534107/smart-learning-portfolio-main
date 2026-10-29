"""用本機規則整理自傳每段的證據、疑點與修改建議。"""

import re

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


# 句子出現這些詞，代表在講具體經驗或行為，需要資料或回答佐證；純感想不檢查。
EXPERIENCE_WORDS = (
    "請教", "擔任", "參加", "參與", "負責", "獲得", "從小", "曾經", "帶領", "主導", "主持",
    "舉辦", "考取", "考到", "取得", "修習", "修過", "實習", "打工", "志工", "得獎", "獲獎",
    "比賽", "競賽", "指導", "自學", "開發", "架設",
)
# 講童年、一向如此的說法：學校資料不可能佐證，只有學生自己的回答寫過才算有依據。
# 只看含這些詞的那個子句，同一句後面提到真的競賽名稱也不能替它擔保。
ORIGIN_WORDS = ("從小", "小時候", "自幼", "一直以來")
SENTENCE_END = re.compile(r"(?<=[。！？])")
CLAUSE_SPLIT = re.compile(r"[，,；;]")
NOT_WORD = re.compile(r"[^0-9A-Za-z一-鿿]")
OVERLAP = 4  # 句子和資料或回答有連續 4 個字相同，就算有依據


def _normalize(text):
    return NOT_WORD.sub("", text or "").lower()


def _fact_keywords(fact_text):
    """事實冒號後的名稱拆成關鍵詞，例如「資料庫管理實務」「SQL」「85分」。"""
    body = (fact_text or "").split("：", 1)[-1]
    pieces = re.split(r"[—（）()、，,；;「」『』]", body)
    return [word for word in (_normalize(piece) for piece in pieces) if len(word) >= 2]


def _has_support(sentence, sources, keywords):
    text = _normalize(sentence)
    if any(word in text for word in keywords):
        return True
    if len(text) <= OVERLAP:
        return any(text in source for source in sources)
    grams = {text[i:i + OVERLAP] for i in range(len(text) - OVERLAP + 1)}
    return any(gram in source for source in sources for gram in grams)


def _origin_unsupported(sentence, answer_sources):
    for clause in CLAUSE_SPLIT.split(sentence):
        if any(word in clause for word in ORIGIN_WORDS) and not _has_support(clause, answer_sources, []):
            return True
    return False


def unsupported_sentences(text, facts, answers):
    """回傳在講具體經驗、卻對不到任何資料或學生回答的句子原文。寧可少抓。"""
    answer_sources = [_normalize(answer) for answer in answers.values() if answer]
    sources = [_normalize(fact["text"]) for fact in facts] + answer_sources
    keywords = [word for fact in facts for word in _fact_keywords(fact["text"])]
    result = []
    for sentence in SENTENCE_END.split(text or ""):
        sentence = sentence.strip()
        if not sentence or "請補上" in sentence or not any(word in sentence for word in EXPERIENCE_WORDS):
            continue
        if _origin_unsupported(sentence, answer_sources) or not _has_support(sentence, sources, keywords):
            result.append(sentence)
    return result


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
        unsupported = unsupported_sentences(paragraph.get("text"), facts, answers)
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
        elif unsupported:
            issue = f"有 {len(unsupported)} 句找不到資料依據"
            suggestion = "刪掉或改成你真的做過的事，再補上依據"
            icon = "⚠"
        else:
            issue = "暫未發現資料疑點"
            suggestion = "確認內容和資料一致，再改成自己的話"
            icon = "✓"

        reviews.append({"evidence": evidence, "issue": issue, "suggestion": suggestion, "icon": icon,
                        "unsupported": unsupported})
    return reviews

"""自傳草稿的規則式「證據—疑點—建議」。"""

from app.services.autobiography_review import review_paragraphs


def test_review_uses_short_evidence_title_and_keeps_full_text():
    reviews = review_paragraphs(
        [{"title": "學習歷程與具體經驗", "text": "我負責後端。", "sources": ["F1"]}],
        [{"id": "F1", "text": "競賽：校園黑客松—三人一組完成報名網站"}],
        {"proud": "黑客松時負責後端 API。"},
    )

    assert reviews[0]["evidence"] == [{
        "id": "F1",
        "evidence_id": None,
        "title": "競賽：校園黑客松",
        "text": "競賽：校園黑客松—三人一組完成報名網站",
    }]
    assert reviews[0]["issue"] == "暫未發現資料疑點"
    assert reviews[0]["icon"] == "✓"


def test_review_flags_answered_paragraph_without_evidence():
    reviews = review_paragraphs(
        [{"title": "學習歷程與具體經驗", "text": "我負責後端。", "sources": []}],
        [],
        {"proud": "黑客松時負責後端 API。"},
    )

    assert reviews[0]["issue"] == "這段沒有資料佐證，請補上具體經驗"
    assert reviews[0]["suggestion"] == "補一段你負責的部分與學到什麼"
    assert reviews[0]["icon"] == "⚠"


def test_review_prioritizes_unanswered_question_over_missing_evidence():
    reviews = review_paragraphs(
        [{"title": "困難與成長", "text": "（請補上你遇過的困難）", "sources": []}],
        [],
        {"challenge": ""},
    )

    assert reviews[0]["issue"] == "這題還沒回答"
    assert reviews[0]["suggestion"] == "補上遇到的困難、你的做法與結果"
    assert reviews[0]["icon"] == "⚠"


def test_missing_evidence_suggestion_matches_the_question():
    """沒有資料佐證時，建議要依題目給，不是每段都叫學生寫負責的部分（會議 20261011-002400 #8）。"""
    reviews = review_paragraphs(
        [{"title": "學習動機", "text": "我喜歡資訊。", "sources": []},
         {"title": "未來規劃", "text": "我想繼續學。", "sources": []}],
        [],
        {"motivation": "喜歡", "proud": "", "challenge": "", "future": "想學"},
    )
    assert reviews[0]["suggestion"] == "補上讓你想讀資管的具體契機"
    assert reviews[1]["suggestion"] == "補上進二技後想學的內容與目標"

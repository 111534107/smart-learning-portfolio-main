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


FACTS = [
    {"id": "F1", "text": "證照：TQC 資料庫應用（專業級）"},
    {"id": "F4", "text": "成績：資料庫管理實務(SQL)（2 年級，85 分）"},
]
ANSWERS = {
    "motivation": "修資料庫的課時發現自己喜歡把資料整理清楚。",
    "proud": "專題時我負責設計資料庫，畫了 ER 圖。",
    "challenge": "SQL 查詢一直寫錯，後來每天練習題目。",
    "future": "想學資料分析。",
}


def _review(text, sources=("F4",), title="學習歷程與具體經驗"):
    return review_paragraphs([{"title": title, "text": text, "sources": list(sources)}], FACTS, ANSWERS)[0]


def test_flags_sentences_without_any_support():
    """Gemini 自己補的經驗（請教、從小）在資料和回答裡都找不到，要逐句標出來。"""
    review = _review("在五專二年級修習『資料庫管理實務(SQL)』這門課時，我獲得了85分的成績。"
                     "遇到不懂的地方，我會反覆練習，並向老師和同學請教。"
                     "我從小就對如何將複雜的事物整理得有條不紊充滿興趣！")

    assert review["unsupported"] == [
        "遇到不懂的地方，我會反覆練習，並向老師和同學請教。",
        "我從小就對如何將複雜的事物整理得有條不紊充滿興趣！",
    ]
    assert review["issue"] == "有 2 句找不到資料依據"
    assert review["icon"] == "⚠"
    assert review["suggestion"] == "刪掉或改成你真的做過的事，再補上依據"


def test_sentence_backed_by_fact_is_not_flagged():
    review = _review("在五專二年級修習『資料庫管理實務(SQL)』這門課時，我獲得了85分的成績。")

    assert review["unsupported"] == []
    assert review["issue"] == "暫未發現資料疑點"
    assert review["icon"] == "✓"


def test_sentence_from_student_answer_is_not_flagged():
    review = _review("在專題中，我負責設計資料庫並畫出 ER 圖。")

    assert review["unsupported"] == []
    assert review["issue"] == "暫未發現資料疑點"


def test_feelings_and_linking_sentences_are_not_flagged():
    review = _review("這讓我更確定方向。我覺得資料整理很有趣，也很有成就感！")

    assert review["unsupported"] == []


def test_existing_issues_take_priority_over_unsupported_sentences():
    unknown = review_paragraphs(
        [{"title": "學習動機", "text": "我從小就喜歡電腦。", "sources": ["F1"], "unknown_sources": ["F9"]}],
        FACTS, ANSWERS)[0]
    no_evidence = _review("我從小就喜歡電腦。", sources=())

    assert unknown["issue"].startswith("引用了不存在的來源 F9")
    assert unknown["unsupported"] == ["我從小就喜歡電腦。"]
    assert no_evidence["issue"] == "這段沒有資料佐證，請補上具體經驗"


def test_childhood_claim_is_flagged_even_when_the_same_sentence_mentions_real_data():
    """「從小」這類說法學校資料不可能佐證；同一句有競賽名稱也要抓出來（2026-10-27 實測 Gemini 草稿）。"""
    facts = [{"id": "F3", "text": "競賽：全國商業類技藝競賽 佳作"}]
    sentence = "我從小就對電腦應用充滿好奇，在五專期間，特別是參加了全國商業類技藝競賽並獲得佳作後，讓我更有興趣。"
    reviews = review_paragraphs([{"title": "學習動機", "text": sentence, "sources": ["F3"]}], facts,
                                {"motivation": "參加競賽後想學更多。"})

    assert reviews[0]["unsupported"] == [sentence]


def test_childhood_claim_written_by_the_student_is_not_flagged():
    facts = [{"id": "F3", "text": "競賽：全國商業類技藝競賽 佳作"}]
    sentence = "我從小就喜歡拆電腦，後來參加了全國商業類技藝競賽。"
    reviews = review_paragraphs([{"title": "學習動機", "text": sentence, "sources": ["F3"]}], facts,
                                {"motivation": "從小就喜歡拆電腦。"})

    assert reviews[0]["unsupported"] == []

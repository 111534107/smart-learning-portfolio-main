"""實習履歷自傳一鍵生成：只用勾選資料與學生寫的字，家庭與未來沒寫就留空，不編造。（僅為測試資料）"""
from app.services import resume_bio_ai
from tests.test_home_desk_resume import _login, _make_app, _user  # noqa: F401


def _choices(texts=None, experiences=(), credentials=()):
    base = {key: "" for key in resume_bio_ai.SECTION_KEYS}
    base.update(texts or {})
    return {"experiences": list(experiences), "credentials": list(credentials), "texts": base, "bio_mode": "guided"}


def test_fallback_uses_only_typed_text_and_chosen_items(monkeypatch):
    app = _make_app(4)
    monkeypatch.setattr("app.services.ai_gateway.generate_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no ai")))
    with app.app_context():
        student = _user()
        choices = _choices({"family": "我家四個人，爸媽做小生意。"},
                           experiences=[{"section": "study", "line": "專二活動：資訊社社課"}],
                           credentials=[{"name": "電腦軟體應用丙級"}])
        result = resume_bio_ai.generate(student, choices)
    sections = result["sections"]
    assert result["provider"] == "rules"
    assert "爸媽做小生意" in sections["family"]
    assert "資訊社社課" in sections["study"] and "電腦軟體應用丙級" in sections["skill"]
    assert sections["future"] == "" and "future" in result["hints"]  # 沒寫就留空並提示


def test_ai_text_for_family_and_future_is_dropped_when_student_wrote_nothing(monkeypatch):
    app = _make_app(4)
    fake = {"family": "我家有三個哥哥（編的）", "study": "我參加資訊社。", "skill": "我有證照。", "future": "我想去大公司（編的）"}
    monkeypatch.setattr("app.services.ai_gateway.generate_json", lambda *a, **k: (fake, "gemini"))
    with app.app_context():
        result = resume_bio_ai.generate(_user(), _choices())
    assert result["sections"]["family"] == "" and result["sections"]["future"] == ""
    assert result["sections"]["study"] == "我參加資訊社。" and result["provider"] == "gemini"


def test_route_returns_sections_and_is_locked_before_grade_four():
    app = _make_app(4)
    client = _login(app)
    data = client.post("/student/internship-resume/bio/generate", data={"text_family": "我從小幫忙顧店。"}).get_json()
    assert set(data["sections"]) == {"family", "study", "skill", "future"}
    assert "顧店" in data["sections"]["family"]
    locked = _login(_make_app(2)).post("/student/internship-resume/bio/generate")
    assert locked.status_code == 403

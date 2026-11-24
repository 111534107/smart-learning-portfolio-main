"""導師「建議修改」：導師選一句話提出替換，學生接受（存成新版）或不接受；原文不動、不能刪除紀錄。（僅為測試資料）"""
import pytest

from app.extensions import db
from app.models import AdmissionProgram, ClassAdvisor, Notification, User
from app.services import autobiography_service, autobiography_suggestion_service as sug
from tests.test_autobiography import ANSWERS, app, choose_target, login, program  # noqa: F401


@pytest.fixture()
def setup(app):
    client = login(app)
    choose_target(app, client)
    client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})
    with app.test_request_context():
        student = User.query.filter_by(username="stu").one()
        teacher = User(username="tea", display_name="陳", role="teacher")
        teacher.set_password("pw")
        db.session.add(teacher)
        db.session.flush()
        db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name=student.student_profile.class_name, school_year=115))
        db.session.commit()
    return client


def _context(app):
    student = User.query.filter_by(username="stu").one()
    teacher = User.query.filter_by(username="tea").one()
    prog = AdmissionProgram.query.filter_by(program_code="208003").one()
    return student, teacher, autobiography_service.latest_draft(student, prog)


def _quote(output):
    text = output.content_json["paragraphs"][0]["text"]
    return text, text[:8]


def test_teacher_suggestion_keeps_original_until_student_accepts(app, setup):
    with app.test_request_context():
        student, teacher, output = _context(app)
        text, quote = _quote(output)
        suggestion = sug.add(teacher, student, output, 0, 0, len(quote), "改過的開頭")
        assert suggestion.status == "pending" and suggestion.original == quote
        assert autobiography_service.latest_draft(student, output.program if hasattr(output, "program") else
                                                   AdmissionProgram.query.filter_by(program_code="208003").one()).id == output.id
        assert output.content_json["paragraphs"][0]["text"] == text  # 還沒接受，原文不動
        assert Notification.query.filter_by(recipient_id=student.id).filter(Notification.message.like("%建議修改%")).count() == 1


def test_accept_creates_new_version_with_replacement(app, setup):
    with app.test_request_context():
        student, teacher, output = _context(app)
        text, quote = _quote(output)
        suggestion = sug.add(teacher, student, output, 0, 0, len(quote), "改過的開頭")
        new_output = sug.accept(student, suggestion.id)
        assert new_output.id != output.id
        assert new_output.content_json["paragraphs"][0]["text"].startswith("改過的開頭")
        assert suggestion.status == "accepted" and suggestion.result_output_id == new_output.id
        assert output.content_json["paragraphs"][0]["text"] == text  # 舊版保留


def test_reject_marks_rejected_and_changes_nothing(app, setup):
    with app.test_request_context():
        student, teacher, output = _context(app)
        _text, quote = _quote(output)
        suggestion = sug.add(teacher, student, output, 0, 0, len(quote), "不要的修改")
        sug.reject(student, suggestion.id)
        assert suggestion.status == "rejected"
        prog = AdmissionProgram.query.filter_by(program_code="208003").one()
        assert autobiography_service.latest_draft(student, prog).id == output.id


def test_only_the_student_can_resolve_and_only_once(app, setup):
    with app.test_request_context():
        student, teacher, output = _context(app)
        _text, quote = _quote(output)
        suggestion = sug.add(teacher, student, output, 0, 0, len(quote), "改")
        with pytest.raises(sug.SuggestionError):
            sug.accept(teacher, suggestion.id)  # 導師不能替學生接受
        sug.reject(student, suggestion.id)
        with pytest.raises(sug.SuggestionError):
            sug.accept(student, suggestion.id)  # 已處理過


def test_stale_suggestion_when_original_text_is_gone(app, setup):
    with app.test_request_context():
        student, teacher, output = _context(app)
        text, quote = _quote(output)
        suggestion = sug.add(teacher, student, output, 0, 0, len(quote), "改")
        autobiography_service.save_edits(output, ["完全不同的內容"] + [p["text"] for p in output.content_json["paragraphs"][1:]], student)
        with pytest.raises(sug.SuggestionError, match="已經改過"):
            sug.accept(student, suggestion.id)
        assert suggestion.status == "stale"


def test_validation_rejects_bad_ranges_and_empty_replacement(app, setup):
    with app.test_request_context():
        student, teacher, output = _context(app)
        with pytest.raises(sug.SuggestionError):
            sug.add(teacher, student, output, 0, 5, 5, "x")  # 沒選到字
        with pytest.raises(sug.SuggestionError):
            sug.add(teacher, student, output, 99, 0, 3, "x")  # 沒有這一段
        with pytest.raises(sug.SuggestionError):
            sug.add(teacher, student, output, 0, 0, 3, "   ")  # 空白替換（要刪字請明確填「（刪除）」不支援）


def test_routes_teacher_adds_student_accepts(app, setup):
    client = setup
    with app.test_request_context():
        student, teacher, output = _context(app)
        sid, oid = student.id, output.id
        _text, quote = _quote(output)
    tea = app.test_client()
    tea.post("/staff/login", data={"username": "tea", "password": "pw"})
    response = tea.post(f"/teacher/students/{sid}/autobiography/{oid}/suggestions",
                        data={"paragraph": 0, "start": 0, "end": len(quote), "replacement": "老師改的"})
    assert response.status_code in (200, 302)
    with app.test_request_context():
        from app.models import AutobiographySuggestion
        suggestion = AutobiographySuggestion.query.one()
        suggestion_id = suggestion.id
    other = app.test_client()
    assert other.post(f"/student/autobiography/suggestions/{suggestion_id}/accept").status_code in (401, 403)
    accepted = client.post(f"/student/autobiography/suggestions/{suggestion_id}/accept")
    assert accepted.status_code in (200, 302)
    with app.test_request_context():
        assert AutobiographySuggestion.query.one().status == "accepted"


def test_teacher_review_and_suggestion_full_lifecycle(app, setup):
    """A3 端到端測試：導師審閱頁佇列、送出建議修改、學生接受產生新版本、導師審核通過。"""
    client = setup
    with app.test_request_context():
        student, teacher, output = _context(app)
        sid, oid = student.id, output.id
        prog_id = AdmissionProgram.query.filter_by(program_code="208003").one().id
        _text, quote = _quote(output)

    tea = app.test_client()
    tea.post("/staff/login", data={"username": "tea", "password": "pw"})

    # 1. 導師進入自傳審閱頁，檢查三欄式內容
    edit_page = tea.get(f"/teacher/students/{sid}/autobiography/{oid}/edit")
    assert edit_page.status_code == 200
    html = edit_page.get_data(as_text=True)
    assert "待審閱學生" in html
    assert student.display_name in html
    assert "自傳紙張" in html or "bio-paper" in html
    assert "模式" in html

    # 2. 導師選取句子提出建議修改
    resp = tea.post(f"/teacher/students/{sid}/autobiography/{oid}/suggestions",
                    data={"paragraph": 0, "start": 0, "end": len(quote), "replacement": "完整流程替換開頭"})
    assert resp.status_code == 302

    # 3. 學生登入自傳頁面，確認收到導師建議修改
    stu_page = client.get(f"/student/autobiography?program_id={prog_id}").get_data(as_text=True)
    assert "完整流程替換開頭" in stu_page or "導師建議" in stu_page

    # 4. 學生按下接受
    with app.test_request_context():
        from app.models import AutobiographySuggestion, PackageReview
        sug_entry = AutobiographySuggestion.query.filter_by(student_id=student.id, status="pending").one()
        sug_id = sug_entry.id
        v1 = output.content_json.get("version", 1)

    accept_resp = client.post(f"/student/autobiography/suggestions/{sug_id}/accept")
    assert accept_resp.status_code == 302

    # 5. 驗證新版本已生成，包含替換後的文字
    with app.test_request_context():
        new_output = autobiography_service.latest_draft(student, AdmissionProgram.query.filter_by(program_code="208003").one())
        assert new_output.id != oid
        assert autobiography_service.version_of(new_output) == v1 + 1
        assert "完整流程替換開頭" in new_output.content_json["paragraphs"][0]["text"]

    # 6. 學生送審備審資料，導師在審查頁按下「通過」
    client.post(f"/student/targets/{prog_id}/review")
    with app.test_request_context():
        review = PackageReview.query.filter_by(student_id=student.id, rule_version_id=prog_id).order_by(PackageReview.id.desc()).first()
        assert review is not None

    decide_resp = tea.post(f"/teacher/package-reviews/{review.id}", data={
        "decision": "confirmed",
        "comment": "自傳寫得很好，核准通過！",
        "taken_at": (review.snapshot_json or {}).get("taken_at", ""),
        "autobiography_viewed": "1",
    })
    assert decide_resp.status_code == 302
    with app.test_request_context():
        updated_rev = db.session.get(PackageReview, review.id)
        assert updated_rev.status == "confirmed"

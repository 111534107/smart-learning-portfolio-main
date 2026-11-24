"""自傳小助手「幫我改」功能測試（A4 規格）。

驗證項目：
1. 送 AI 前遮蔽個資（姓名、學號換成代號，回傳後換回）。
2. 以建議修改（AutobiographySuggestion，pending 狀態）呈現，不直接覆蓋原文。
3. 防造假檢查：拒絕新增的數字、獎項、證照和具名社團經歷。
4. 路由整合測試：學生與導師端點正常運作。
"""

from unittest.mock import Mock

import pytest

from app.extensions import db
from app.models import AdmissionProgram, AutobiographySuggestion, ClassAdvisor, LearningProfileOutput, StudentProfile, User
from app.services import ai_gateway, autobiography_assistant_service, autobiography_service
from tests.test_autobiography import app  # noqa: F401


def _setup_student_with_draft(app):
    with app.app_context():
        student = User(username="stu_a4", display_name="王小明", role="student", is_active=True)
        student.set_password("pw")
        db.session.add(student)
        db.session.flush()

        profile = StudentProfile(user_id=student.id, student_no="11012345", class_name="資管五甲")
        db.session.add(profile)

        teacher = User(username="tea_a4", display_name="陳導師", role="teacher", is_active=True)
        teacher.set_password("pw")
        db.session.add(teacher)
        db.session.flush()

        db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name="資管五甲", school_year=115))

        prog = AdmissionProgram(
            school_name="雲林科技大學",
            department_name="資訊管理系",
            admission_year=115,
            program_code="DAY-YUNTECH-A4",
            status="published",
        )
        db.session.add(prog)
        db.session.flush()

        output = LearningProfileOutput(
            student_id=student.id,
            output_type=autobiography_service.OUTPUT_TYPE,
            source_snapshot_json={},
            content_json={
                "program_id": prog.id,
                "version": 1,
                "paragraphs": [
                    {
                        "title": "求學歷程",
                        "text": "我是王小明，學號 11012345，我在專科期間完成了 3 個資訊系統專案，獲益良多。"
                    },
                    {
                        "title": "未來展望",
                        "text": "我希望未來能在二技期間持續精進人工智慧與資料庫技術。"
                    }
                ]
            }
        )
        db.session.add(output)
        db.session.commit()
        return student.id, teacher.id, prog.id, output.id


def test_redact_and_unredact_personal_info(app):
    """驗證送 AI 前遮蔽個資（姓名換為 [學生姓名]，學號換為 [學號]），回傳後可正確換回。"""
    sid, _, _, _ = _setup_student_with_draft(app)
    with app.app_context():
        student = db.session.get(User, sid)
        raw_text = "我是王小明，學號 11012345，請多多指教。"

        # 1. 遮蔽個資
        redacted = autobiography_assistant_service.redact_personal_info(raw_text, student)
        assert "王小明" not in redacted
        assert "11012345" not in redacted
        assert "[學生姓名]" in redacted
        assert "[學號]" in redacted or "[號碼]" in redacted

        # 2. 還原個資
        fake_ai_output = "這段文字由 [學生姓名]（學號：[學號]）撰寫，語氣流暢。"
        unredacted = autobiography_assistant_service.unredact_personal_info(fake_ai_output, student)
        assert "[學生姓名]" not in unredacted
        assert "[學號]" not in unredacted
        assert "王小明" in unredacted
        assert "11012345" in unredacted


def test_anti_fabrication_detects_new_numbers():
    """驗證防造假檢查：比對新句子與原文，禁止新增原文沒有的數字。"""
    # 原文無 8，新句新增 8 -> 應拒絕
    orig = "在求學期間我參與了 3 個實務專案。"
    fraud_rep = "在求學期間我主導了 8 個實務專案。"
    with pytest.raises(autobiography_assistant_service.FabricationError) as exc_info:
        autobiography_assistant_service.check_fabrication(orig, fraud_rep)
    assert "8" in str(exc_info.value)

    # 原文為中文數字「三個」，新句改為「八個」或「8 個」-> 應拒絕
    orig_cn = "在求學期間我參與了三個實務專案。"
    fraud_cn = "在求學期間我參與了八個實務專案。"
    with pytest.raises(autobiography_assistant_service.FabricationError):
        autobiography_assistant_service.check_fabrication(orig_cn, fraud_cn)

    with pytest.raises(autobiography_assistant_service.FabricationError):
        autobiography_assistant_service.check_fabrication("我做過實務專案。", "我做過參個實務專案。")

    # 包含原文已有的數字，或未新增數字 -> 通過檢查
    valid_rep = "在專科修業期間，我參與了 3 個實務系統的開發與建置。"
    autobiography_assistant_service.check_fabrication(orig, valid_rep)

    pure_text_orig = "我熱愛撰寫程式並參與社團活動。"
    pure_text_rep = "我熱愛軟體開發，並積極投入各類社團運作。"
    autobiography_assistant_service.check_fabrication(pure_text_orig, pure_text_rep)


@pytest.mark.parametrize("added_claim", [
    "我也獲頒校園程式設計優勝獎。",
    "我也考取了雲端基礎證照。",
    "我也加入了星光資訊研究社。",
], ids=["award", "credential", "club"])
def test_student_assistant_rejects_new_claim_before_creating_suggestion(app, monkeypatch, added_claim):
    sid, _, _, oid = _setup_student_with_draft(app)
    with app.app_context():
        original = db.session.get(LearningProfileOutput, oid).content_json["paragraphs"][0]["text"]
    selection_start = original.index("我在專科期間")
    rewritten = "在專科修業期間，我完成了 3 項資訊系統專案。" + added_claim
    monkeypatch.setattr(ai_gateway, "generate_json", lambda *args, **kwargs: ({"rewritten": rewritten}, "fake"))

    client = app.test_client()
    client.post("/login", data={"username": "stu_a4", "password": "pw"})
    response = client.post(
        f"/student/autobiography/{oid}/assistant-rewrite",
        json={"paragraph": 0, "start": selection_start, "end": len(original)},
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "fabrication_rejected"
    with app.app_context():
        assert AutobiographySuggestion.query.filter_by(student_id=sid).count() == 0
        assert db.session.get(LearningProfileOutput, oid).content_json["paragraphs"][0]["text"] == original


@pytest.mark.parametrize("actor", ["student", "teacher"])
@pytest.mark.parametrize(("attendance", "selected"), [
    ("我本週有曠課紀錄。", "我本週有曠課紀錄"),
    ("本學期曠課 2 節，另外曾請病假。", "2 節"),
    ("校方列出本學期的曠 課紀錄。", "本學期"),
], ids=["explicit-record", "only-count", "spaced-label"])
def test_assistant_blocks_attendance_before_ai(app, monkeypatch, actor, attendance, selected):
    sid, _, _, oid = _setup_student_with_draft(app)
    ordinary = "我熱愛整理資料。"
    paragraph_text = attendance + ordinary
    with app.app_context():
        output = db.session.get(LearningProfileOutput, oid)
        output.content_json = {**output.content_json, "paragraphs": [{"title": "實測", "text": paragraph_text}]}
        db.session.commit()

    gateway = Mock(return_value=({"rewritten": "整理資料是我的興趣。"}, "fake"))
    monkeypatch.setattr(ai_gateway, "generate_json", gateway)
    client = app.test_client()
    if actor == "teacher":
        client.post("/staff/login", data={"username": "tea_a4", "password": "pw"})
        route = f"/teacher/students/{sid}/autobiography/{oid}/assistant-rewrite"
    else:
        client.post("/login", data={"username": "stu_a4", "password": "pw"})
        route = f"/student/autobiography/{oid}/assistant-rewrite"

    start = paragraph_text.index(selected)
    headers = {"X-Requested-With": "XMLHttpRequest"}
    blocked = client.post(route, data={"paragraph": 0, "start": start, "end": start + len(selected)}, headers=headers)
    gateway.assert_not_called()
    assert blocked.status_code == 400
    assert "重新選取" in blocked.get_json()["error"]
    with app.app_context():
        assert AutobiographySuggestion.query.filter_by(student_id=sid).count() == 0
        assert db.session.get(LearningProfileOutput, oid).content_json["paragraphs"][0]["text"] == paragraph_text

    allowed = client.post(route, data={"paragraph": 0, "start": len(attendance), "end": len(paragraph_text)}, headers=headers)
    assert allowed.status_code == 200
    gateway.assert_called_once()
    assert ordinary in gateway.call_args.args[0]
    assert attendance not in gateway.call_args.args[0]


@pytest.mark.parametrize(("original", "rewritten"), [
    ("我得過校園程式設計優勝獎。", "我曾榮獲校園程式設計傑出獎。"),
    ("我希望考取雲端基礎證照。", "我已取得雲端基礎證照。"),
    ("我加入星光資訊研究社。", "我加入星光資料研究社。"),
    ("我加入星光資訊研究社。", "我加入星光資訊研究社及光點桌遊社。"),
], ids=["different-award", "plan-is-not-a-credential", "different-club", "additional-club"])
def test_anti_fabrication_rejects_changed_or_added_claim(original, rewritten):
    with pytest.raises(autobiography_assistant_service.FabricationError):
        autobiography_assistant_service.check_fabrication(original, rewritten)


@pytest.mark.parametrize(("original", "rewritten"), [
    ("我得過校園程式設計優勝獎。", "在求學期間，我曾榮獲校園程式設計優勝獎。"),
    ("我考到雲端基礎證照。", "我在就學期間取得了「雲端基礎證照」。"),
    ("我加入星光資訊研究社。", "在校期間，我曾參加星光資訊研究社的活動。"),
    ("我希望考取雲端基礎證照。", "未來，我計畫取得雲端基礎證照。"),
], ids=["same-award", "same-credential", "same-club", "still-a-plan"])
def test_anti_fabrication_allows_rephrasing_existing_claim(original, rewritten):
    autobiography_assistant_service.check_fabrication(original, rewritten)


@pytest.mark.parametrize(("original", "rewritten"), [
    ("我喜歡整理資料。", "我在星光資訊研究社擔任幹部。"),
    ("我加入星光資訊研究社。", "我加入星光資訊研究社，並擔任幹部。"),
    ("我加入社團。", "我在社團擔任幹部。"),
    ("我在星光資訊研究社擔任幹部。", "我曾任星光資訊研究社社長。"),
    ("我是星光資訊研究社的社長助理。", "我在星光資訊研究社當社長。"),
    ("我希望在星光資訊研究社擔任幹部。", "我曾擔任星光資訊研究社的幹部。"),
    ("我在星光資訊研究社擔任幹部，也加入光點桌遊社。", "我擔任光點桌遊社的幹部。"),
], ids=["new-role", "membership-only", "unnamed-club", "changed-role", "club-president", "plan-is-not-a-role", "different-club-same-role"])
def test_anti_fabrication_rejects_new_club_role(original, rewritten):
    with pytest.raises(autobiography_assistant_service.FabricationError, match="社團職務"):
        autobiography_assistant_service.check_fabrication(original, rewritten)


@pytest.mark.parametrize(("original", "rewritten"), [
    ("我在星光資訊研究社擔任幹部。", "在校期間，我曾擔任「星光資訊研究社」的幹部。"),
    ("我加入星光資訊研究社，並擔任幹部。", "我曾在星光資訊研究社出任幹部。"),
    ("我希望在星光資訊研究社擔任幹部。", "我計畫擔任星光資訊研究社的幹部。"),
], ids=["same-role", "same-role-across-comma", "still-a-plan"])
def test_anti_fabrication_allows_rephrasing_existing_club_role(original, rewritten):
    autobiography_assistant_service.check_fabrication(original, rewritten)


@pytest.mark.parametrize("actor", ["student", "teacher"])
def test_assistant_returns_club_role_rejection_without_a_suggestion(app, monkeypatch, actor):
    sid, _, _, oid = _setup_student_with_draft(app)
    with app.app_context():
        original = db.session.get(LearningProfileOutput, oid).content_json["paragraphs"][1]["text"]
    rewritten = original + "我在星光資訊研究社擔任幹部。"
    gateway = Mock(return_value=({"rewritten": rewritten}, "fake"))
    monkeypatch.setattr(ai_gateway, "generate_json", gateway)
    client = app.test_client()
    if actor == "teacher":
        client.post("/staff/login", data={"username": "tea_a4", "password": "pw"})
        route = f"/teacher/students/{sid}/autobiography/{oid}/assistant-rewrite"
    else:
        client.post("/login", data={"username": "stu_a4", "password": "pw"})
        route = f"/student/autobiography/{oid}/assistant-rewrite"
    response = client.post(route, json={"paragraph": 1, "start": 0, "end": len(original)})

    gateway.assert_called_once()
    assert response.status_code == 400
    assert "社團職務" in response.get_json()["error"]
    with app.app_context():
        assert AutobiographySuggestion.query.filter_by(student_id=sid).count() == 0
        assert db.session.get(LearningProfileOutput, oid).content_json["paragraphs"][1]["text"] == original


def test_assistant_rewrite_creates_suggestion_without_overwriting(app):
    """驗證小助手改寫以建議修改（pending 狀態）呈現，不直接覆蓋原文。"""
    sid, _, _, oid = _setup_student_with_draft(app)
    with app.app_context():
        student = db.session.get(User, sid)
        output = db.session.get(LearningProfileOutput, oid)
        orig_para_text = output.content_json["paragraphs"][0]["text"]
        start = orig_para_text.index("我在專科期間")
        end = len(orig_para_text)

        # 模擬 AI 提出的精修建議（保留原數字 3，不新增數字）
        mock_replacement = "在專科修業期間，我主導並完成了 3 項資訊系統專案，累積了豐富的實務經驗。"

        suggestion = autobiography_assistant_service.rewrite_selection(
            actor=student,
            student=student,
            output=output,
            paragraph=0,
            start=start,
            end=end,
            replacement_override=mock_replacement
        )

        assert suggestion is not None
        assert suggestion.status == "pending"
        assert suggestion.author_id == student.id
        assert suggestion.original == orig_para_text[start:end]
        assert suggestion.replacement == mock_replacement

        # 確認原文完全未被修改覆蓋
        reloaded_output = db.session.get(LearningProfileOutput, output.id)
        assert reloaded_output.content_json["paragraphs"][0]["text"] == orig_para_text

        # 學生接受後才生成新版本並覆蓋
        from app.services import autobiography_suggestion_service
        new_output = autobiography_suggestion_service.accept(student, suggestion.id)
        assert new_output.id != output.id
        assert mock_replacement in new_output.content_json["paragraphs"][0]["text"]


def test_student_and_teacher_assistant_endpoints(app):
    """驗證學生與導師端點呼叫小助手幫我改。"""
    sid, tid, pid, oid = _setup_student_with_draft(app)

    client = app.test_client()

    # 1. 學生呼叫自己的自傳改寫
    client.post("/login", data={"username": "stu_a4", "password": "pw"})
    resp = client.post(
        f"/student/autobiography/{oid}/assistant-rewrite",
        data={"paragraph": "1", "start": "0", "end": "10"}
    )
    assert resp.status_code in {200, 302}

    with app.app_context():
        sug = AutobiographySuggestion.query.filter_by(student_id=sid, paragraph=1).first()
        assert sug is not None
        assert sug.status == "pending"

    # 2. 導師呼叫學生自傳改寫
    tea_client = app.test_client()
    tea_client.post("/staff/login", data={"username": "tea_a4", "password": "pw"})
    t_resp = tea_client.post(
        f"/teacher/students/{sid}/autobiography/{oid}/assistant-rewrite",
        data={"paragraph": "0", "start": "0", "end": "5"}
    )
    assert t_resp.status_code in {200, 302}

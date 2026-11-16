"""畢業門檻工作台（2026-11-16）：總覽量表、門檻區塊細項、下一步按鈕。只改呈現，數字沿用原本的計算。（僅為測試資料）"""
from app.extensions import db
from app.models import CredentialRecord, LearningCourseRecord, SourceDocument, SystemSetting, User
from app.services import graduation_board, graduation_check_service as svc
from tests.test_student_records import login, records_app


def _course(student, name, credits, score, status, year=1, semester="上"):
    return LearningCourseRecord(student_id=student.id, course_name=name, normalized_course_name=name,
                                school_year=year, semester=semester, credits=credits, score=score,
                                confirmation_status="confirmed")


def _seed(app):
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        db.session.add_all([
            _course(student, "國文", 8, 80, "passed"),
            _course(student, "會計實務", 2, 75, "passed"),
            _course(student, "會計學", 3, 40, "not_passed", semester="下"),
            _course(student, "外星語入門", 2, 90, "passed", semester="下"),
            CredentialRecord(student_id=student.id, credential_name="電腦軟體應用 丙級", level="丙級",
                             confirmation_status="confirmed"),
        ])
        db.session.commit()
        return student.id


def test_course_lists_split_counted_missing_and_unmatched(tmp_path):
    app = records_app(tmp_path)
    student_id = _seed(app)
    with app.app_context():
        student = db.session.get(User, student_id)
        curriculum = svc.load_curriculum()
        lists = graduation_board.course_lists(student, curriculum)
        credits = svc.credit_status(student, curriculum=curriculum)

        assert [c["name"] for c in lists["required"]] == ["國文"]
        assert [c["name"] for c in lists["elective"]] == ["會計實務"]
        assert [c["name"] for c in lists["unmatched"]] == ["外星語入門"]
        assert [c["name"] for c in lists["failed"]] == ["會計學"]
        # 清單加總和原本的學分計算一致（不改計算規則）
        assert sum(c["credits"] for c in lists["required"]) == credits["earned"]["required"]
        assert sum(c["credits"] for c in lists["elective"]) == credits["earned"]["elective"]
        missing = {c["name"] for c in lists["not_taken"]}
        assert "會計學" in missing and "國文" not in missing
        # 從清單挑的通識不列為「還缺」
        assert not any(c["category"] in ("進階分類通識", "通識選修") for c in lists["not_taken"])


def test_meters_reuse_evaluate_numbers(tmp_path):
    app = records_app(tmp_path)
    student_id = _seed(app)
    with app.app_context():
        student = db.session.get(User, student_id)
        result = svc.evaluate(student)
        rows = {row["item"]: row for row in graduation_board.meters(result)}
        assert rows["certificates"]["have"] == 1 and rows["certificates"]["short"] == 2
        assert rows["total_credits"]["have"] == result["credits"]["earned"]["total"]
        assert rows["total_credits"]["need"] == 220
        assert 0 < rows["total_credits"]["pct"] < 100


def test_dashboard_page_shows_overview_blocks_and_next_steps(tmp_path):
    app = records_app(tmp_path)
    student_id = _seed(app)
    with app.app_context():
        db.session.add(SourceDocument(owner_id=student_id, document_type="credential", display_name="cert.png",
                                      file_path=str(tmp_path / "cert.png"), sha256="e" * 64, status="extracted"))
        db.session.commit()
    client = app.test_client()
    login(client)
    html = client.get("/student/graduation-check").get_data(as_text=True)

    assert "畢業門檻工作台" in html and "data-grad-dashboard" in html
    assert "data-gd-ring" in html and html.count('data-open-block="') == 4
    for item in ("certificates", "required_credits", "elective_credits", "total_credits"):
        assert f'data-gd-block="{item}"' in html
    assert 'data-gd-list="counted"' in html and 'data-gd-list="not-taken"' in html
    assert "外星語入門" in html and "待人工確認" in html
    # 下一步：缺的證照連到上傳證照、待確認檔案連到我的檔案、對不到的課可先填好詢問內容
    assert "/student/learning-profile/upload?type=credential" in html
    assert 'href="/student/files"' in html
    assert 'data-prefill="這些課在畢業門檻對不到科目表' in html
    assert 'id="gd-ask"' in html
    assert "js/student-v2/graduation.js" in html


def test_met_block_shows_check_and_feedback(tmp_path):
    app = records_app(tmp_path)
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        db.session.add(SystemSetting(key=svc.TODAY_SETTING_KEY, value="2022-09-01"))  # 111 入學、專一上，還沒有已結束學期
        for name in ("電腦軟體應用 丙級", "網頁設計 丙級", "軟體應用 乙級"):
            db.session.add(CredentialRecord(student_id=student.id, credential_name=name,
                                            level=name.split()[-1], confirmation_status="confirmed"))
        db.session.commit()
    client = app.test_client()
    login(client)
    html = client.get("/student/graduation-check").get_data(as_text=True)

    assert 'data-gd-block="certificates" data-result="met"' in html
    assert "這一項達成了" in html


def test_formal_credit_gap_gets_an_ask_step():
    item = lambda result, amount=None: {"result": result, "amount": amount, "missing_terms": []}
    assessment = {"stage": {"ended_terms": [(113, "上")]},
                  "items": {"certificates": item("met"), "required_credits": item("gap", 157),
                            "elective_credits": item("progress", 39), "total_credits": item("gap", 196)}}
    pending = {"transcript": [], "credential": []}
    steps = graduation_board.next_steps(assessment, {}, None, pending, {"terms": []})

    assert [s["action"] for s in steps] == ["問導師補修方式"]
    assert steps[0]["prefill"] == "畢業門檻顯示必修學分還差 157 學分、總學分還差 196 學分，想請問要怎麼補修。"

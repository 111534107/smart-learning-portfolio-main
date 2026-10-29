"""資管科小助手第 1 步「確認與版本」（規格第 10 節）。"""
from datetime import date

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    AdmissionProgram,
    ClassAdvisor,
    CredentialRecord,
    LearningCourseRecord,
    Portfolio,
    StudentProfile,
    User,
)
from app.services.admission_service import import_seed_programs
from app.services.autobiography_service import build_facts
from app.services.journey_service import academic_year_of
from tests.board_helpers import fill_board

# 讓「stu」不論哪一年跑測試都是專三
GRADE3_ADMISSION_YEAR = academic_year_of(date.today()) - 2


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        import_seed_programs()
        for username, role in (("stu", "student"), ("other", "student"), ("teacher", "teacher"),
                               ("stranger", "teacher")):
            user = User(username=username, display_name=username, role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.flush()
        stu = User.query.filter_by(username="stu").one()
        other = User.query.filter_by(username="other").one()
        db.session.add(StudentProfile(user_id=stu.id, student_no="111534100", class_name="資管科三甲",
                                      admission_year=GRADE3_ADMISSION_YEAR))
        db.session.add(StudentProfile(user_id=other.id, student_no="111534200", class_name="資管科三乙",
                                      admission_year=GRADE3_ADMISSION_YEAR))
        teacher = User.query.filter_by(username="teacher").one()
        db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name="資管科三甲", school_year=115))
        db.session.commit()
        fill_board(stu)  # 拼圖要完成才能生成自傳
        yield app


def login(app, username="stu"):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def user_id(app, username):
    with app.app_context():
        return User.query.filter_by(username=username).one().id


def program_id(app, code="208003"):
    with app.app_context():
        return AdmissionProgram.query.filter_by(program_code=code).one().id


def add_portfolio(app, username="stu", title="校園黑客松", status="draft", **extra):
    with app.app_context():
        record = Portfolio(student_id=user_id(app, username), title=title, category="competition",
                           school_year=3, status=status, **extra)
        db.session.add(record)
        db.session.commit()
        return record.id


def facts_text(app, username="stu"):
    with app.app_context():
        student = User.query.filter_by(username=username).one()
        program = db.session.get(AdmissionProgram, program_id(app))
        return [item["text"] for item in build_facts(student, program)["items"]]


# ---------- Task 1：經歷確認＋build_facts 只讀已確認資料 ----------

def test_build_facts_skips_unconfirmed_records(app):
    add_portfolio(app, title="還在寫的草稿", status="draft")
    add_portfolio(app, title="確認過的競賽", status="confirmed")
    add_portfolio(app, title="舊流程送出的", status="submitted")
    with app.app_context():
        sid = user_id(app, "stu")
        db.session.add(LearningCourseRecord(student_id=sid, course_name="程式設計", normalized_course_name="程式設計",
                                            score=90, confirmation_status="confirmed"))
        db.session.add(LearningCourseRecord(student_id=sid, course_name="沒確認的課", normalized_course_name="沒確認的課",
                                            score=80, confirmation_status="pending"))
        db.session.add(CredentialRecord(student_id=sid, credential_name="網頁設計乙級", confirmation_status="confirmed"))
        db.session.add(CredentialRecord(student_id=sid, credential_name="沒確認的證照", confirmation_status="pending"))
        db.session.commit()

    texts = " ".join(facts_text(app))

    assert "確認過的競賽" in texts
    assert "舊流程送出的" in texts
    assert "程式設計" in texts
    assert "網頁設計乙級" in texts
    assert "還在寫的草稿" not in texts
    assert "沒確認的課" not in texts
    assert "沒確認的證照" not in texts


def test_student_confirms_own_record(app):
    record_id = add_portfolio(app)

    response = login(app).post(f"/student/portfolio/{record_id}/confirm")

    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(Portfolio, record_id).status == "confirmed"


def test_student_cannot_confirm_someone_elses_record(app):
    record_id = add_portfolio(app, username="other")

    response = login(app).post(f"/student/portfolio/{record_id}/confirm")

    assert response.status_code in (403, 404)
    with app.app_context():
        assert db.session.get(Portfolio, record_id).status == "draft"


def test_form_save_and_confirm(app):
    client = login(app)
    form = {"title": "資訊週志工", "category": "service", "school_year": "2", "semester": "1"}

    client.post("/student/portfolio", data=form)
    client.post("/student/portfolio", data={**form, "title": "迎新宿營", "confirm": "1"})

    with app.app_context():
        assert Portfolio.query.filter_by(title="資訊週志工").one().status == "draft"
        assert Portfolio.query.filter_by(title="迎新宿營").one().status == "confirmed"


def test_editing_confirmed_record_needs_confirming_again(app):
    record_id = add_portfolio(app, status="confirmed")
    client = login(app)
    form = {"title": "校園黑客松（改）", "category": "competition", "school_year": "3"}

    client.post(f"/student/portfolio/{record_id}/edit", data=form)
    with app.app_context():
        assert db.session.get(Portfolio, record_id).status == "draft"

    client.post(f"/student/portfolio/{record_id}/edit", data={**form, "confirm": "1"})
    with app.app_context():
        assert db.session.get(Portfolio, record_id).status == "confirmed"


def test_portfolio_page_shows_draft_status_and_confirm_button(app):
    record_id = add_portfolio(app)

    html = login(app).get("/student/portfolio").get_data(as_text=True)

    assert 'class="status-chip status-chip--draft"' in html
    assert "草稿" in html
    assert f"/student/portfolio/{record_id}/confirm" in html


# ---------- Task 2：年級限制與目標校系上限 ----------

def set_admission_year(app, year, username="stu"):
    with app.app_context():
        profile = StudentProfile.query.filter_by(user_id=user_id(app, username)).one()
        profile.admission_year = year
        db.session.commit()


def add_programs(app, count, year=None):
    """再建立幾個正式校系（種子資料只有 4 個）。"""
    year = year or academic_year_of(date.today())
    ids = []
    with app.app_context():
        start = AdmissionProgram.query.count()
        for index in range(start, start + count):
            program = AdmissionProgram(program_code=f"9{index:05d}", admission_year=year, school_name=f"測試大學{index}",
                                       department_name="資管系", status="published")
            db.session.add(program)
            db.session.flush()
            ids.append(program.id)
        db.session.commit()
    return ids


def target_count(app):
    from app.models import StudentTarget
    with app.app_context():
        return StudentTarget.query.filter_by(student_id=user_id(app, "stu")).count()


def test_sixth_target_is_refused_in_fifth_year(app):
    with app.app_context():
        profile = StudentProfile.query.filter_by(student_no="111534100").one()
        profile.admission_year = GRADE3_ADMISSION_YEAR - 2
        db.session.commit()
    client = login(app)
    with app.app_context():
        seeded = [p.id for p in AdmissionProgram.query.filter_by(status="published").all()]
    for pid in seeded + add_programs(app, 1):
        client.post("/student/targets", data={"program_id": pid})
    assert target_count(app) == 5

    response = client.post("/student/targets", data={"program_id": add_programs(app, 1)[0]})

    assert target_count(app) == 5
    assert "最多 5 所" in response.get_data(as_text=True)


def test_third_year_can_choose_more_than_five(app):
    client = login(app)
    with app.app_context():
        seeded = [p.id for p in AdmissionProgram.query.filter_by(status="published").all()]
    for pid in seeded + add_programs(app, 3):
        client.post("/student/targets", data={"program_id": pid})

    assert target_count(app) == len(seeded) + 3 > 5


def test_old_year_target_does_not_use_a_slot_and_can_be_removed(app):
    from app.models import StudentTarget
    stu_id = user_id(app, "stu")
    with app.app_context():
        newest = AdmissionProgram.query.filter_by(program_code="208003").one()
        old = AdmissionProgram(program_code="208003", admission_year=newest.admission_year - 1,
                               school_name=newest.school_name, department_name=newest.department_name,
                               status="published")
        db.session.add(old)
        db.session.flush()
        db.session.add(StudentTarget(student_id=stu_id, rule_version_id=old.id))
        db.session.commit()
        old_id = old.id
    client = login(app)

    html = client.get("/student/targets").get_data(as_text=True)
    assert "舊學年度" in html
    assert "隨時可以換" in html  # 三年級不限所數；五年級上限的檢查在 test_sixth_target_is_refused_in_fifth_year

    client.post(f"/student/targets/{old_id}/remove")
    assert target_count(app) == 0


def add_admin(app):
    with app.app_context():
        admin = User(username="admin", display_name="admin", role="admin")
        admin.set_password("pw")
        db.session.add(admin)
        db.session.commit()
    return login(app, "admin")


def test_missing_admission_year_blocks_and_student_cannot_fill_it(app):
    """主持人 2026-10-10 決定：入學學年度由管理者匯入，學生不能自己填（審查 P0-4）。"""
    set_admission_year(app, None)
    client = login(app)
    pid = program_id(app)

    blocked = client.post("/student/targets", data={"program_id": pid})
    assert blocked.status_code == 403
    assert "請聯絡系統管理者" in blocked.get_data(as_text=True)
    assert target_count(app) == 0
    record = client.post("/student/portfolio", data={"title": "志工", "category": "service", "school_year": "1"})
    assert record.status_code == 400
    assert "入學學年度" in record.get_data(as_text=True)

    filled = client.post("/student/profile/admission-year", data={"admission_year": "110"})
    assert filled.status_code in (404, 405)
    with app.app_context():
        assert StudentProfile.query.filter_by(user_id=user_id(app, "stu")).one().admission_year is None


def test_admin_imports_admission_years_and_it_is_logged(app):
    from app.models import AuditLog
    set_admission_year(app, None)
    admin = add_admin(app)
    rows = "\n".join([f"111534100,{GRADE3_ADMISSION_YEAR}", f"111534200 {GRADE3_ADMISSION_YEAR - 1}",
                      "999999999,113", "111534100,abc"])

    response = admin.post("/admin/accounts/admission-years", data={"rows": rows}, follow_redirects=True)

    html = response.get_data(as_text=True)
    with app.app_context():
        profiles = {p.student_no: p.admission_year for p in StudentProfile.query.all()}
        logs = AuditLog.query.filter_by(action="student_profile.admission_year").all()
    assert profiles["111534100"] == GRADE3_ADMISSION_YEAR
    assert profiles["111534200"] == GRADE3_ADMISSION_YEAR - 1
    assert len(logs) == 2
    assert "999999999" in html  # 找不到的學號要列出來
    assert "已更新 2 位" in html
    client = login(app)
    client.post("/student/targets", data={"program_id": program_id(app)})
    assert target_count(app) == 1


def test_only_admin_can_import_admission_years(app):
    set_admission_year(app, None)

    for username in ("stu", "teacher"):
        response = login(app, username).post("/admin/accounts/admission-years",
                                             data={"rows": f"111534100,{GRADE3_ADMISSION_YEAR}"})
        assert response.status_code == 403
    with app.app_context():
        assert StudentProfile.query.filter_by(user_id=user_id(app, "stu")).one().admission_year is None


def test_record_for_a_future_grade_is_refused_and_input_kept(app):
    client = login(app)

    response = client.post("/student/portfolio", data={"title": "未來的比賽", "category": "competition", "school_year": "4"})
    html = response.get_data(as_text=True)
    roc = client.post("/student/portfolio", data={"title": "未來的比賽", "category": "competition",
                                                  "school_year": str(GRADE3_ADMISSION_YEAR + 3)})
    ok = client.post("/student/portfolio", data={"title": "現在的比賽", "category": "competition", "school_year": "3"})

    assert response.status_code == 400
    assert "專三" in html and "未來的比賽" in html
    assert roc.status_code == 400
    assert ok.status_code == 302


def test_course_for_a_future_grade_is_refused(app, tmp_path):
    import json
    from app.models import DocumentExtraction, SourceDocument
    with app.app_context():
        document = SourceDocument(owner_id=user_id(app, "stu"), document_type="transcript", display_name="t.pdf",
                                  file_path=str(tmp_path / "t.pdf"), sha256="c" * 64, status="extracted")
        db.session.add(document)
        db.session.flush()
        db.session.add(DocumentExtraction(source_document_id=document.id, provider="fake", status="extracted",
                                          result_json={"courses": []}))
        db.session.commit()
        document_id = document.id
    client = login(app)

    response = client.post(f"/student/learning-profile/documents/{document_id}/review/confirm", data={
        "courses_json": json.dumps([{"course_name": "專題實作", "school_year": 5, "score": 90}]),
        "credentials_json": "[]",
    })

    assert response.status_code == 400
    assert "專三" in response.get_data(as_text=True)


def test_first_year_student_can_look_but_not_send_or_write(app):
    set_admission_year(app, academic_year_of(date.today()))
    client = login(app)
    pid = program_id(app)
    client.post("/student/targets", data={"program_id": pid})

    gap = client.get(f"/student/targets/{pid}")
    review = client.post(f"/student/targets/{pid}/review")
    generate = client.post("/student/autobiography/generate", data={"program_id": pid, "motivation": "想讀資管"})

    from app.models import LearningProfileOutput, PackageReview
    assert gap.status_code == 200
    assert review.status_code == 403
    assert generate.status_code == 403
    assert "專二" in review.get_data(as_text=True)
    with app.app_context():
        assert PackageReview.query.count() == 0
        assert LearningProfileOutput.query.count() == 0


# ---------- Task 3：送審快照、導師確認與撤回 ----------

def choose_and_send(app, client, pid=None):
    pid = pid or program_id(app)
    client.post("/student/targets", data={"program_id": pid})
    client.post(f"/student/targets/{pid}/review")
    return pid


def latest_review_row(app):
    from app.models import PackageReview
    with app.app_context():
        review = PackageReview.query.order_by(PackageReview.id.desc()).first()
        return {"id": review.id, "status": review.status, "snapshot": review.snapshot_json}


def add_credential(app, name="勞動部網頁設計乙級"):
    with app.app_context():
        db.session.add(CredentialRecord(student_id=user_id(app, "stu"), credential_name=name, level="乙級"))
        db.session.commit()


def test_request_review_saves_a_snapshot(app):
    add_portfolio(app, title="確認過的競賽", status="confirmed")
    add_portfolio(app, title="還在寫的草稿", status="draft")

    choose_and_send(app, login(app))

    snapshot = latest_review_row(app)["snapshot"]
    texts = " ".join(fact["text"] for fact in snapshot["facts"])
    assert "確認過的競賽" in texts
    assert "還在寫的草稿" not in texts
    assert snapshot["program"]["id"] == program_id(app)
    assert "readiness" in snapshot
    assert snapshot["autobiography"] is None


def test_resending_while_pending_updates_the_same_snapshot(app):
    client = login(app)
    choose_and_send(app, client)
    first = latest_review_row(app)
    add_credential(app)

    client.post(f"/student/targets/{program_id(app)}/review")

    second = latest_review_row(app)
    from app.models import PackageReview
    with app.app_context():
        assert PackageReview.query.count() == 1
    assert second["id"] == first["id"]
    assert any("網頁設計乙級" in fact["text"] for fact in second["snapshot"]["facts"])


def test_confirmed_snapshot_does_not_change_when_student_adds_credential(app):
    from app.services.review_snapshot_service import confirmed_facts
    client = login(app)
    pid = choose_and_send(app, client)
    review_id = latest_review_row(app)["id"]
    login(app, "teacher").post(f"/teacher/package-reviews/{review_id}", data={"decision": "confirmed",
                                                                         "taken_at": teacher_form(app, review_id)})
    before = latest_review_row(app)["snapshot"]

    add_credential(app)
    client.post(f"/student/targets/{pid}/review")

    from app.models import PackageReview
    with app.app_context():
        confirmed = db.session.get(PackageReview, review_id)
        assert confirmed.snapshot_json == before
        assert confirmed.status == "confirmed"
        student = User.query.filter_by(username="stu").one()
        program = db.session.get(AdmissionProgram, pid)
        assert not any("網頁設計乙級" in fact["text"] for fact in confirmed_facts(student, program))
        assert PackageReview.query.count() == 2
    teacher_html = login(app, "teacher").get(f"/teacher/students/{user_id(app, 'stu')}").get_data(as_text=True)
    assert "新增" in teacher_html and "勞動部網頁設計乙級" in teacher_html


def test_teacher_confirm_and_withdraw_are_logged(app):
    from app.models import AuditLog
    choose_and_send(app, login(app))
    review_id = latest_review_row(app)["id"]
    teacher = login(app, "teacher")
    teacher.post(f"/teacher/package-reviews/{review_id}", data={"decision": "confirmed", "taken_at": teacher_form(app, review_id)})

    no_reason = teacher.post(f"/teacher/package-reviews/{review_id}/withdraw", data={"reason": " "})
    assert no_reason.status_code == 400
    teacher.post(f"/teacher/package-reviews/{review_id}/withdraw", data={"reason": "按錯了，自傳還沒看完"})

    assert latest_review_row(app)["status"] == "pending"
    with app.app_context():
        actions = [log.action for log in AuditLog.query.filter(AuditLog.action.like("package_review.%")).order_by(AuditLog.id).all()]
        withdraw = AuditLog.query.filter_by(action="package_review.withdraw").one()
    assert actions == ["package_review.request", "package_review.confirm", "package_review.withdraw"]  # 送審也有紀錄（M11）
    assert withdraw.detail_json["reason"] == "按錯了，自傳還沒看完"
    assert withdraw.target_id == review_id


def test_other_class_teacher_cannot_withdraw(app):
    choose_and_send(app, login(app))
    review_id = latest_review_row(app)["id"]
    login(app, "teacher").post(f"/teacher/package-reviews/{review_id}", data={"decision": "confirmed",
                                                                         "taken_at": teacher_form(app, review_id)})

    response = login(app, "stranger").post(f"/teacher/package-reviews/{review_id}/withdraw", data={"reason": "測試"})

    assert response.status_code == 403
    assert latest_review_row(app)["status"] == "confirmed"


def test_teacher_still_sees_review_after_student_cancels_target(app):
    client = login(app)
    pid = choose_and_send(app, client)
    client.post(f"/student/targets/{pid}/remove")

    html = login(app, "teacher").get(f"/teacher/students/{user_id(app, 'stu')}").get_data(as_text=True)

    assert "國立臺北商業大學" in html
    assert "學生已取消這個目標" in html


def test_review_snapshot_migration_upgrades_and_downgrades(tmp_path):
    from sqlalchemy import inspect
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'm.db'}", "TESTING": True})
    runner = app.test_cli_runner()

    assert runner.invoke(args=["db", "upgrade"]).exit_code == 0
    with app.app_context():
        columns = {c["name"] for c in inspect(db.engine).get_columns("package_reviews")}
        assert "snapshot_json" in columns
        assert inspect(db.engine).has_table("ai_daily_usage")
    assert runner.invoke(args=["db", "downgrade", "d5b9a2c7e104"]).exit_code == 0
    with app.app_context():
        db.engine.dispose()
        columns = {c["name"] for c in inspect(db.engine).get_columns("package_reviews")}
        assert "snapshot_json" not in columns
        assert not inspect(db.engine).has_table("ai_daily_usage")


# ---------- Task 4：自傳版本紀錄、導師直接改文字與段落意見 ----------

ANSWERS = {"motivation": "想把需求變成系統。", "proud": "黑客松負責後端。", "challenge": "", "future": "想學資料分析。"}


def write_autobiography(app, client):
    pid = program_id(app)
    client.post("/student/targets", data={"program_id": pid})
    client.post("/student/autobiography/generate", data={"program_id": pid, **ANSWERS})
    return pid


def autobiography_rows(app):
    from app.models import LearningProfileOutput
    with app.app_context():
        return [{"id": o.id, "content": o.content_json}
                for o in LearningProfileOutput.query.filter_by(output_type="autobiography_ai").order_by(LearningProfileOutput.id)]


def save(client, output_id, texts, url=None, comments=None):
    data = {f"paragraph_{i}": text for i, text in enumerate(texts)}
    data.update({f"comment_{i}": text for i, text in enumerate(comments or [])})
    return client.post(url or f"/student/autobiography/{output_id}/save", data=data)


def test_each_save_is_a_new_version_and_old_ones_stay(app):
    set_admission_year(app, GRADE3_ADMISSION_YEAR - 2)  # 專五：自傳到專五才開放生成
    client = login(app)
    write_autobiography(app, client)
    first = autobiography_rows(app)[0]
    count = len(first["content"]["paragraphs"])

    save(client, first["id"], ["第二版"] * count)
    second = autobiography_rows(app)[-1]
    save(client, second["id"], ["第三版"] * count)

    rows = autobiography_rows(app)
    assert len(rows) == 3
    assert rows[0]["content"] == first["content"]
    assert [row["content"]["version"] for row in rows] == [1, 2, 3]
    assert rows[-1]["content"]["editor_role"] == "student"
    assert rows[-1]["content"]["based_on"] == second["id"]
    assert rows[-1]["content"]["paragraphs"][0]["text"] == "第三版"


def test_regenerating_is_also_a_new_version(app):
    set_admission_year(app, GRADE3_ADMISSION_YEAR - 2)  # 專五：自傳到專五才開放生成
    client = login(app)
    pid = write_autobiography(app, client)

    client.post("/student/autobiography/generate", data={"program_id": pid, **ANSWERS})

    rows = autobiography_rows(app)
    assert len(rows) == 2
    assert rows[-1]["content"]["version"] == 2
    assert rows[-1]["content"]["editor_role"] == "ai"


def test_teacher_edits_text_and_leaves_comments(app):
    set_admission_year(app, GRADE3_ADMISSION_YEAR - 2)  # 專五：自傳到專五才開放生成
    student = login(app)
    write_autobiography(app, student)
    first = autobiography_rows(app)[0]
    count = len(first["content"]["paragraphs"])
    url = f"/teacher/students/{user_id(app, 'stu')}/autobiography/{first['id']}/edit"

    page = login(app, "teacher").get(url)
    response = save(login(app, "teacher"), None, ["老師改過的第一段"] + [p["text"] for p in first["content"]["paragraphs"][1:]],
                    url=url, comments=["這段可以多寫你負責的部分"] + [""] * (count - 1))

    assert page.status_code == 200
    assert response.status_code == 302
    latest = autobiography_rows(app)[-1]["content"]
    assert latest["version"] == 2
    assert latest["editor_role"] == "teacher"
    assert latest["paragraphs"][0]["text"] == "老師改過的第一段"
    assert latest["paragraphs"][0]["teacher_comment"] == "這段可以多寫你負責的部分"

    versions_html = student.get(f"/student/autobiography/versions?program_id={program_id(app)}").get_data(as_text=True)
    assert "導師" in versions_html and "teacher" in versions_html
    assert "<ins>" in versions_html
    autobiography_html = student.get(f"/student/autobiography?program_id={program_id(app)}").get_data(as_text=True)
    assert "這段可以多寫你負責的部分" in autobiography_html


def test_other_class_teacher_cannot_edit_autobiography(app):
    set_admission_year(app, GRADE3_ADMISSION_YEAR - 2)  # 專五：自傳到專五才開放生成
    write_autobiography(app, login(app))
    first = autobiography_rows(app)[0]
    url = f"/teacher/students/{user_id(app, 'stu')}/autobiography/{first['id']}/edit"

    assert login(app, "stranger").get(url).status_code == 403
    assert save(login(app, "stranger"), None, ["偷改"], url=url).status_code == 403
    assert len(autobiography_rows(app)) == 1


def test_teacher_page_shows_reviewed_and_current_version(app):
    set_admission_year(app, GRADE3_ADMISSION_YEAR - 2)  # 專五：自傳到專五才開放生成
    client = login(app)
    pid = write_autobiography(app, client)
    client.post(f"/student/targets/{pid}/review")
    first = autobiography_rows(app)[0]
    save(client, first["id"], ["送審後又改"] * len(first["content"]["paragraphs"]))

    html = login(app, "teacher").get(f"/teacher/students/{user_id(app, 'stu')}").get_data(as_text=True)

    assert "自傳依據第 1 版" in html
    assert "目前第 2 版" in html


# ---------- Task 5：學校金鑰每人每天 5 次 ----------

FAKE_PARAGRAPHS = {"paragraphs": [{"title": "學習動機", "text": "我想讀資管。", "sources": []}]}


def enable_school_ai(app, monkeypatch, result=FAKE_PARAGRAPHS):
    from app.services import autobiography_service
    calls = []

    def fake_generate_json(prompt, schema, api_key=None, **kwargs):
        calls.append(api_key)
        if isinstance(result, Exception):
            raise result
        return result

    app.config.update(AI_ENABLED=True, AI_PROVIDER="gemini", AI_API_KEY="school-key-for-test")
    monkeypatch.setattr(autobiography_service, "generate_json", fake_generate_json)
    return calls


def generate(client, pid, **extra):
    return client.post("/student/autobiography/generate", data={"program_id": pid, **ANSWERS, **extra})


def test_school_key_is_limited_to_five_a_day(app, monkeypatch):
    set_admission_year(app, GRADE3_ADMISSION_YEAR - 2)  # 專五：自傳到專五才開放生成
    calls = enable_school_ai(app, monkeypatch)
    client = login(app)
    pid = program_id(app)
    client.post("/student/targets", data={"program_id": pid})

    for _ in range(5):
        assert generate(client, pid).status_code == 302
    sixth = generate(client, pid)

    assert sixth.status_code == 429
    assert "5 次" in sixth.get_data(as_text=True)
    assert "自己的 Gemini 金鑰" in sixth.get_data(as_text=True)
    assert len(calls) == 5
    assert len(autobiography_rows(app)) == 5

    own = generate(client, pid, own_api_key="my-own-key")
    assert own.status_code == 302
    assert calls[-1] == "my-own-key"
    assert len(autobiography_rows(app)) == 6


def test_failed_ai_call_does_not_use_a_turn(app, monkeypatch):
    set_admission_year(app, GRADE3_ADMISSION_YEAR - 2)  # 專五：自傳到專五才開放生成
    from app.services.gemini_client import AIUnavailable
    from app.services.ai_quota_service import remaining
    enable_school_ai(app, monkeypatch, result=AIUnavailable("連不到 Gemini"))
    client = login(app)
    pid = program_id(app)
    client.post("/student/targets", data={"program_id": pid})

    response = generate(client, pid)

    assert response.status_code == 503
    with app.app_context():
        assert remaining(User.query.filter_by(username="stu").one()) == 5


def test_page_shows_remaining_school_turns(app, monkeypatch):
    set_admission_year(app, GRADE3_ADMISSION_YEAR - 2)  # 專五：自傳到專五才開放生成
    enable_school_ai(app, monkeypatch)
    client = login(app)
    pid = program_id(app)
    client.post("/student/targets", data={"program_id": pid})
    generate(client, pid)

    html = client.get(f"/student/autobiography?program_id={pid}&redo=1").get_data(as_text=True)

    assert "今天學校 AI 還能用 4 次" in html


def test_demo_mode_does_not_count(app):
    from app.services.ai_quota_service import remaining
    client = login(app)
    pid = program_id(app)
    client.post("/student/targets", data={"program_id": pid})

    generate(client, pid)

    with app.app_context():
        assert remaining(User.query.filter_by(username="stu").one()) == 5


def test_award_import_counts_toward_school_turns(app, monkeypatch):
    import io
    from app.services import gemini_client
    from app.services.ai_quota_service import consume, remaining
    calls = []
    app.config.update(AI_ENABLED=True, AI_PROVIDER="gemini", AI_API_KEY="school-key-for-test")
    monkeypatch.setattr(gemini_client, "generate_json", lambda *a, **k: calls.append(1) or {"rows": []})
    client = login(app)

    def upload():
        return client.post("/student/award-records", data={"file": (io.BytesIO(b"%PDF-1.4 fake"), "award.pdf")},
                           content_type="multipart/form-data")

    upload()  # AI 沒讀出任何列：退回次數
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        assert remaining(student) == 5
        for _ in range(5):
            consume(student)
        db.session.commit()
    upload()

    assert len(calls) == 1
    from app.models import DocumentExtraction
    with app.app_context():
        latest = DocumentExtraction.query.order_by(DocumentExtraction.id.desc()).first()
        assert any("用完" in w for w in latest.result_json.get("warnings", []))


# ---------- 審查修正（會議 20261009-185407 #48–#59） ----------

def test_editing_submitted_record_needs_confirming_again(app):
    """P0-1：舊流程送出（submitted）的經歷改過內容，要重新確認才會進自傳。"""
    record_id = add_portfolio(app, title="送出過的競賽", status="submitted")

    login(app).post(f"/student/portfolio/{record_id}/edit",
                    data={"title": "送出後偷改的競賽", "category": "competition", "school_year": "3"})

    with app.app_context():
        assert db.session.get(Portfolio, record_id).status == "draft"
    assert not any("送出後偷改的競賽" in text for text in facts_text(app))


def teacher_form(app, review_id):
    """導師頁上這筆送審的表單，取出頁面記住的 taken_at。"""
    import re
    html = login(app, "teacher").get(f"/teacher/students/{user_id(app, 'stu')}").get_data(as_text=True)
    match = re.search(rf'action="/teacher/package-reviews/{review_id}".*?name="taken_at" value="([^"]*)"', html, re.S)
    assert match, "導師頁的確認表單要帶 taken_at"
    return match.group(1)


def test_teacher_cannot_confirm_content_updated_after_page_opened(app):
    """P0-2：導師開頁後學生又更新送審，舊頁面按確認要被擋下，請導師先看新內容。"""
    client = login(app)
    pid = choose_and_send(app, client)
    review_id = latest_review_row(app)["id"]
    seen = teacher_form(app, review_id)
    add_credential(app)
    client.post(f"/student/targets/{pid}/review")  # 學生更新同一筆送審

    response = login(app, "teacher").post(f"/teacher/package-reviews/{review_id}",
                                          data={"decision": "confirmed", "taken_at": seen}, follow_redirects=True)

    assert "學生剛更新了送審內容" in response.get_data(as_text=True)
    assert latest_review_row(app)["status"] == "pending"
    fresh = teacher_form(app, review_id)
    login(app, "teacher").post(f"/teacher/package-reviews/{review_id}", data={"decision": "confirmed", "taken_at": fresh})
    assert latest_review_row(app)["status"] == "confirmed"


def test_teacher_cannot_decide_an_old_or_finished_review(app):
    """P0-2：已經處理過、或已有更新送審的舊紀錄，不能再按確認。"""
    from app.models import PackageReview
    client = login(app)
    pid = choose_and_send(app, client)
    first = latest_review_row(app)["id"]
    teacher = login(app, "teacher")
    teacher.post(f"/teacher/package-reviews/{first}", data={"decision": "needs_revision", "comment": "請補證照",
                                                            "taken_at": teacher_form(app, first)})
    with app.app_context():
        taken = db.session.get(PackageReview, first).snapshot_json["taken_at"]

    again = teacher.post(f"/teacher/package-reviews/{first}", data={"decision": "confirmed", "taken_at": taken},
                         follow_redirects=True)
    assert "已經處理過" in again.get_data(as_text=True)

    client.post(f"/student/targets/{pid}/review")  # 新的一筆送審
    teacher.post(f"/teacher/package-reviews/{first}", data={"decision": "confirmed", "taken_at": taken})
    with app.app_context():
        assert db.session.get(PackageReview, first).status == "needs_revision"


def test_withdraw_is_refused_when_a_newer_review_exists(app):
    """撤回後不能和學生的新送審同時有兩筆等待確認。"""
    from app.models import PackageReview
    client = login(app)
    pid = choose_and_send(app, client)
    first = latest_review_row(app)["id"]
    teacher = login(app, "teacher")
    teacher.post(f"/teacher/package-reviews/{first}", data={"decision": "confirmed", "taken_at": teacher_form(app, first)})
    client.post(f"/student/targets/{pid}/review")

    response = teacher.post(f"/teacher/package-reviews/{first}/withdraw", data={"reason": "按錯了"})

    assert response.status_code == 400
    with app.app_context():
        assert PackageReview.query.filter_by(status="pending").count() == 1
        assert db.session.get(PackageReview, first).status == "confirmed"


def test_saving_an_old_version_is_refused_and_text_is_kept(app):
    set_admission_year(app, GRADE3_ADMISSION_YEAR - 2)  # 專五：自傳到專五才開放生成
    """P0-3：導師開第 1 版後學生存了第 2 版，導師用舊頁面存檔要被擋下，打的字要留著。"""
    student = login(app)
    write_autobiography(app, student)
    first = autobiography_rows(app)[0]
    count = len(first["content"]["paragraphs"])
    url = f"/teacher/students/{user_id(app, 'stu')}/autobiography/{first['id']}/edit"
    save(student, first["id"], ["學生第二版"] * count)

    response = save(login(app, "teacher"), None, ["導師用舊頁面改的字"] * count, url=url)

    html = response.get_data(as_text=True)
    assert response.status_code == 409
    assert "第 2 版" in html and "導師用舊頁面改的字" in html
    rows = autobiography_rows(app)
    assert len(rows) == 2
    assert rows[-1]["content"]["paragraphs"][0]["text"] == "學生第二版"


def test_student_saving_an_old_version_is_refused(app):
    set_admission_year(app, GRADE3_ADMISSION_YEAR - 2)  # 專五：自傳到專五才開放生成
    student = login(app)
    write_autobiography(app, student)
    first = autobiography_rows(app)[0]
    count = len(first["content"]["paragraphs"])
    save(student, first["id"], ["第二版"] * count)

    response = save(student, first["id"], ["舊分頁的字"] * count)

    assert response.status_code == 409
    assert "舊分頁的字" in response.get_data(as_text=True)
    assert len(autobiography_rows(app)) == 2


def test_quota_exceeded_does_not_roll_back_the_callers_work(app):
    """P1：額度用完時不要把呼叫端還沒存的變更一起丟掉。"""
    from app.services.ai_quota_service import QuotaExceeded, consume
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        for _ in range(5):
            consume(student)
        db.session.commit()
        db.session.add(Portfolio(student_id=student.id, title="還沒存的經歷", category="activity"))
        db.session.flush()
        with pytest.raises(QuotaExceeded):
            consume(student)
        db.session.commit()
        assert Portfolio.query.filter_by(title="還沒存的經歷").count() == 1


def test_student_still_sees_versions_after_cancelling_target(app):
    set_admission_year(app, GRADE3_ADMISSION_YEAR - 2)  # 專五：自傳到專五才開放生成
    """主持人 2026-10-10：取消目標校系後，學生仍看得到那個校系的自傳版本紀錄（唯讀）。"""
    client = login(app)
    pid = write_autobiography(app, client)
    client.post(f"/student/targets/{pid}/remove")

    versions = client.get(f"/student/autobiography/versions?program_id={pid}")
    targets = client.get("/student/targets").get_data(as_text=True)
    other = login(app, "other").get(f"/student/autobiography/versions?program_id={pid}")

    assert versions.status_code == 200
    assert "第 1 版" in versions.get_data(as_text=True)
    assert "已取消" in versions.get_data(as_text=True)
    assert f"/student/autobiography/versions?program_id={pid}" in targets
    assert other.status_code in (302, 404) or "第 1 版" not in other.get_data(as_text=True)

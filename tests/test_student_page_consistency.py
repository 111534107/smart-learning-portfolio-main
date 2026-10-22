"""GPT 任務 06：學生端頁面的用語、空狀態與錯誤下一步一致。"""
from datetime import date

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    AdmissionProgram,
    DocumentExtraction,
    SourceDocument,
    StudentProfile,
    StudentTarget,
    User,
)
from app.services.journey_service import academic_year_of


@pytest.fixture()
def consistency_app(tmp_path):
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
        "UPLOAD_FOLDER": str(tmp_path),
    })
    with app.app_context():
        db.create_all()
        student = User(username="student", display_name="測試學生", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.flush()
        db.session.add(StudentProfile(
            user_id=student.id,
            student_no="S001",
            admission_year=academic_year_of(date.today()) - 4,
        ))
        db.session.commit()
    return app


def login(app):
    client = app.test_client()
    client.post("/login", data={"username": "student", "password": "pw"})
    return client


def add_programs(app, count):
    with app.app_context():
        programs = [
            AdmissionProgram(
                program_code=f"90000{index}",
                admission_year=academic_year_of(date.today()),
                school_name="測試科技大學",
                department_name=f"資訊管理系 {index}",
                admission_category="技優甄審",
                status="published",
            )
            for index in range(count)
        ]
        db.session.add_all(programs)
        db.session.commit()
        return [program.id for program in programs]


def add_failed_document(app, tmp_path):
    with app.app_context():
        student = User.query.filter_by(username="student").one()
        document = SourceDocument(
            owner_id=student.id,
            document_type="transcript",
            display_name="舊格式.txt",
            file_path=str(tmp_path / "舊格式.txt"),
            sha256="f" * 64,
            status="analysis_failed",
        )
        db.session.add(document)
        db.session.flush()
        db.session.add(DocumentExtraction(
            source_document_id=document.id,
            provider="fake",
            status="failed",
            result_json={},
        ))
        db.session.commit()
        return document.id


def test_review_failures_and_empty_table_offer_next_actions(consistency_app, tmp_path):
    document_id = add_failed_document(consistency_app, tmp_path)
    html = login(consistency_app).get(
        f"/student/learning-profile/documents/{document_id}/review"
    ).get_data(as_text=True)

    assert "這種檔案無法預覽" in html
    assert 'href="/student/learning-profile/upload?type=transcript"' in html
    assert "重新上傳文件" in html
    assert "這份文件無法自動辨識" in html
    assert 'href="#course-table-title"' in html
    assert "開始手動輸入" in html
    assert "還沒有課程" in html
    assert 'data-add-row="course-table"' in html


def test_portfolio_form_error_offers_a_button_back_to_required_fields(consistency_app):
    response = login(consistency_app).post(
        "/student/portfolio",
        data={"title": "", "category": "activity"},
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 400
    assert "請填寫名稱" in html
    assert 'href="#record-form"' in html
    assert "回到必填欄位" in html


def test_target_empty_and_limit_error_states_offer_next_actions(consistency_app):
    client = login(consistency_app)
    empty_html = client.get("/student/targets").get_data(as_text=True)

    assert "目前還沒有公開的目標校系資料" in empty_html
    assert 'href="/student/dashboard"' in empty_html
    assert "先整理我的資料" in empty_html

    program_ids = add_programs(consistency_app, 6)
    with consistency_app.app_context():
        student = User.query.filter_by(username="student").one()
        db.session.add_all([
            StudentTarget(student_id=student.id, rule_version_id=program_id)
            for program_id in program_ids[:5]
        ])
        db.session.commit()

    response = client.post("/student/targets", data={"program_id": program_ids[5]})
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "目標校系同時最多 5 所" in html
    assert 'href="#target-programs"' in html
    assert "查看已選目標校系" in html


def test_blocked_page_has_one_clear_button_to_the_next_step(consistency_app):
    program_id = add_programs(consistency_app, 1)[0]
    with consistency_app.app_context():
        profile = StudentProfile.query.one()
        profile.admission_year = None
        db.session.commit()

    response = login(consistency_app).post("/student/targets", data={"program_id": program_id})
    html = response.get_data(as_text=True)

    assert response.status_code == 403
    assert "請聯絡系統管理者" in html
    assert 'class="button" href="/student/targets"' in html
    assert "回到目標校系" in html


def test_six_student_pages_use_consistent_terms(consistency_app, tmp_path):
    document_id = add_failed_document(consistency_app, tmp_path)
    client = login(consistency_app)
    pages = [
        client.get("/student/learning-profile/upload").get_data(as_text=True),
        client.get(f"/student/learning-profile/documents/{document_id}/review").get_data(as_text=True),
        client.get("/student/portfolio/new").get_data(as_text=True),
        client.get("/student/targets").get_data(as_text=True),
        client.get("/student/welcome").get_data(as_text=True),
    ]

    assert "確認上傳內容" in pages[1]
    assert "確認並儲存" in pages[1]
    assert "確認並儲存" in pages[2]
    assert "先看目標校系" in pages[4]
    for html in pages:
        assert "未確認" not in html
        assert "目標學校" not in html
        assert "志願校系" not in html
        assert "備審文件" not in html

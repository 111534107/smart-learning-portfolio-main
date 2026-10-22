from datetime import datetime, timezone

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    AdmissionProgram,
    AdmissionRequirementItem,
    LearningCourseRecord,
    LearningProfileOutput,
    PackageReview,
    Portfolio,
    StudentTarget,
    User,
)


@pytest.fixture()
def gap_app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        student = User(username="student", display_name="學生", role="student")
        student.set_password("pw")
        program = AdmissionProgram(
            program_code="TEST-03",
            admission_year=116,
            school_name="測試大學",
            department_name="資訊管理系",
            admission_category="測試入學",
            status="published",
        )
        db.session.add_all([student, program])
        db.session.flush()
        db.session.add(StudentTarget(student_id=student.id, rule_version_id=program.id))
        db.session.commit()
        yield app


def _login(app):
    client = app.test_client()
    client.post("/login", data={"username": "student", "password": "pw"})
    return client


def _ids(app):
    with app.app_context():
        return User.query.filter_by(username="student").one().id, AdmissionProgram.query.filter_by(
            program_code="TEST-03"
        ).one().id


def test_gap_page_without_review_hides_timeline_and_keeps_download_available(gap_app):
    student_id, program_id = _ids(gap_app)
    with gap_app.app_context():
        db.session.add(Portfolio(student_id=student_id, title="還沒確認的作品", category="competition"))
        db.session.commit()

    html = _login(gap_app).get(f"/student/targets/{program_id}").get_data(as_text=True)

    assert html.count("準備度只看你確認過的資料，不是錄取機率") == 1
    assert 'data-review-timeline' not in html
    assert "資料都已確認" in html
    assert "! 還沒" in html
    assert "下載 Word" in html


def test_gap_page_lists_rejected_and_resent_review_versions(gap_app):
    student_id, program_id = _ids(gap_app)
    with gap_app.app_context():
        db.session.add_all([
            PackageReview(
                student_id=student_id,
                rule_version_id=program_id,
                status="confirmed",
                requested_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
            ),
            PackageReview(
                student_id=student_id,
                rule_version_id=program_id,
                status="needs_revision",
                requested_at=datetime(2026, 10, 3, tzinfo=timezone.utc),
            ),
            PackageReview(
                student_id=student_id,
                rule_version_id=program_id,
                status="pending",
                requested_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
            ),
        ])
        db.session.commit()

    html = _login(gap_app).get(f"/student/targets/{program_id}").get_data(as_text=True)

    assert 'data-review-timeline' in html
    assert "第 1 版" in html and "2026-10-01" in html and "已確認" in html
    assert "第 2 版" in html and "2026-10-03" in html and "退回" in html
    assert "第 3 版" in html and "2026-10-05" in html and "待確認" in html
    assert html.count(">最新</span>") == 1


def test_gap_page_shows_all_four_checks_complete(gap_app):
    student_id, program_id = _ids(gap_app)
    with gap_app.app_context():
        db.session.add(AdmissionRequirementItem(
            rule_version_id=program_id,
            source_item_name="歷年成績",
            weight_percent=100,
            mapped_categories="grades",
            mapping_status="confirmed",
        ))
        db.session.add(LearningCourseRecord(
            student_id=student_id,
            course_name="程式設計",
            normalized_course_name="程式設計",
            score=90,
            confirmation_status="confirmed",
        ))
        db.session.add(LearningProfileOutput(
            student_id=student_id,
            output_type="autobiography_ai",
            content_json={"program_id": program_id, "version": 1, "edited": True, "paragraphs": []},
            source_snapshot_json={},
        ))
        db.session.add(PackageReview(
            student_id=student_id,
            rule_version_id=program_id,
            status="confirmed",
            requested_at=datetime(2026, 10, 6, tzinfo=timezone.utc),
        ))
        db.session.commit()

    html = _login(gap_app).get(f"/student/targets/{program_id}").get_data(as_text=True)

    assert html.count("✓ 已完成") == 4
    assert "! 還沒" not in html
    assert "下載 Word" in html


def test_untouched_ai_draft_does_not_count_as_written(gap_app):
    """AI 剛產生、學生沒改過的草稿，不算「自傳已改成自己的話」（會議 20261011-002400 #8）。"""
    student_id, program_id = _ids(gap_app)
    with gap_app.app_context():
        db.session.add(LearningProfileOutput(
            student_id=student_id,
            output_type="autobiography_ai",
            content_json={"program_id": program_id, "version": 1, "edited": False, "paragraphs": []},
            source_snapshot_json={},
        ))
        db.session.commit()

    html = _login(gap_app).get(f"/student/targets/{program_id}").get_data(as_text=True)
    item = html.split("自傳已改成自己的話", 1)[0].rsplit("download-checklist__item", 1)[1]
    assert "! 還沒" in item
    # 「還沒」的項目要帶到這個校系的自傳頁
    assert f"/student/autobiography?program_id={program_id}" in html

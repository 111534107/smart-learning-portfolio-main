import importlib
import importlib.util
from types import SimpleNamespace

from app import create_app
from app.extensions import db
from app.models import (
    CredentialRecord,
    LearningCourseRecord,
    Portfolio,
    PortfolioEvidence,
    SourceDocument,
    User,
)


def _status_functions():
    assert importlib.util.find_spec("app.services.record_status") is not None, (
        "應提供共用的 record_status 服務"
    )
    module = importlib.import_module("app.services.record_status")
    return module.portfolio_state, module.learning_profile_state


def test_portfolio_state_uses_three_consistent_states():
    portfolio_state, _ = _status_functions()

    assert portfolio_state(SimpleNamespace(status="draft", source="student", evidence_items=[])) == "draft"
    assert portfolio_state(SimpleNamespace(status="confirmed", source="student", evidence_items=[])) == "pending-source"
    assert portfolio_state(SimpleNamespace(status="confirmed", source="student", evidence_items=[object()])) == "confirmed"


def test_school_import_is_confirmed_without_student_evidence():
    portfolio_state, _ = _status_functions()

    record = SimpleNamespace(status="confirmed", source="award_record", evidence_items=[])

    assert portfolio_state(record) == "confirmed"


def test_learning_profile_state_accepts_confirmed_record_or_source_document():
    _, learning_profile_state = _status_functions()

    assert learning_profile_state(SimpleNamespace(status="uploaded")) == "draft"
    assert learning_profile_state(SimpleNamespace(status="confirmed")) == "confirmed"
    assert learning_profile_state(SimpleNamespace(
        confirmation_status="draft",
        source_document=SimpleNamespace(status="confirmed"),
    )) == "confirmed"
    assert learning_profile_state(SimpleNamespace(
        confirmation_status="confirmed",
        source_document=None,
    )) == "confirmed"


def _status_app(tmp_path):
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "UPLOAD_FOLDER": str(tmp_path),
    })
    with app.app_context():
        db.create_all()
        student = User(username="status-student", display_name="狀態學生", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.flush()

        draft = Portfolio(
            student_id=student.id,
            title="尚未確認的活動",
            category="activity",
            status="draft",
            source="student",
        )
        missing_source = Portfolio(
            student_id=student.id,
            title="缺少佐證的活動",
            category="activity",
            status="confirmed",
            source="student",
        )
        evidenced = Portfolio(
            student_id=student.id,
            title="已有佐證的活動",
            category="activity",
            status="confirmed",
            source="student",
        )
        db.session.add_all([draft, missing_source, evidenced])
        db.session.flush()
        db.session.add(PortfolioEvidence(
            portfolio_id=evidenced.id,
            evidence_type="url",
            display_name="活動頁面",
            external_url="https://example.invalid/evidence",
        ))

        uploaded = SourceDocument(
            owner_id=student.id,
            document_type="transcript",
            display_name="待確認成績單.pdf",
            file_path=str(tmp_path / "draft.pdf"),
            sha256="a" * 64,
            status="uploaded",
        )
        confirmed = SourceDocument(
            owner_id=student.id,
            document_type="credential",
            display_name="已確認證照.pdf",
            file_path=str(tmp_path / "confirmed.pdf"),
            sha256="b" * 64,
            status="confirmed",
        )
        db.session.add_all([uploaded, confirmed])
        db.session.flush()
        db.session.add(LearningCourseRecord(
            student_id=student.id,
            source_document_id=confirmed.id,
            course_name="程式設計",
            normalized_course_name="程式設計",
            confirmation_status="draft",
        ))
        db.session.add(CredentialRecord(
            student_id=student.id,
            credential_name="資訊證照",
            confirmation_status="confirmed",
        ))
        db.session.commit()
    return app


def _login(client):
    response = client.post("/login", data={"username": "status-student", "password": "pw"})
    assert response.status_code == 302


def test_portfolio_page_renders_all_three_accessible_status_chips(tmp_path):
    client = _status_app(tmp_path).test_client()
    _login(client)

    html = client.get("/student/portfolio").get_data(as_text=True)

    assert html.count('class="status-chip status-chip--draft"') == 1
    assert html.count('class="status-chip status-chip--pending-source"') == 1
    assert html.count('class="status-chip status-chip--confirmed"') == 1
    assert '<span class="status-chip__icon" aria-hidden="true">✓</span><span>已確認</span>' in html
    assert '<span class="status-chip__icon" aria-hidden="true">!</span><span>待補來源</span>' in html
    assert '<span class="status-chip__icon" aria-hidden="true">—</span><span>草稿</span>' in html


def test_learning_profile_page_uses_the_same_status_chips_for_every_record_type(tmp_path):
    client = _status_app(tmp_path).test_client()
    _login(client)

    # 成績單與證照已分成兩頁；兩頁合起來仍是同一套狀態標籤
    html = (client.get("/student/learning-profile").get_data(as_text=True)
            + client.get("/student/learning-profile/credentials").get_data(as_text=True))

    assert html.count('class="status-chip status-chip--confirmed"') == 3
    assert html.count('class="status-chip status-chip--draft"') == 1
    assert "待你確認" not in html
    assert "已上傳" not in html

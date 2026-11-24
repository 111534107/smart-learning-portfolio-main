from pathlib import Path

from app import create_app
from app.extensions import db
from app.models import (
    Portfolio,
    PortfolioEvidence,
    ProjectType,
    RequirementItem,
    RequirementTemplate,
    StudentProfile,
    StudentProjectAssignment,
    User,
)


def portfolio_app(tmp_path):
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
        "UPLOAD_FOLDER": str(tmp_path),
    })
    with app.app_context():
        db.create_all()
        student = User(username="student", display_name="學生", role="student")
        other = User(username="other", display_name="其他", role="student")
        for user in (student, other):
            user.set_password("pw")
            db.session.add(user)
        db.session.flush()
        # 規格 10.5：沒有入學學年度的學生不能新增經歷
        db.session.add(StudentProfile(user_id=student.id, student_no="111534199", admission_year=113))
        db.session.commit()
    return app


def login(client, username="student"):
    client.post("/login", data={"username": username, "password": "pw"})


def test_student_can_create_and_submit_own_portfolio_with_goal_snapshot(tmp_path):
    app = portfolio_app(tmp_path)
    with app.app_context():
        student = User.query.filter_by(username="student").one()
        project_type = ProjectType(code="software", name="資訊軟體開發", school_year=115, is_active=True)
        template = RequirementTemplate(name="期中", version="1", project_type=project_type, is_active=True)
        item = RequirementItem(title="功能展示", description="展示功能", template=template, stage="midterm")
        db.session.add_all([project_type, template, item])
        db.session.flush()
        db.session.add(StudentProjectAssignment(student_id=student.id, template_id=template.id))
        db.session.commit()

    client = app.test_client()
    login(client)
    response = client.post("/student/portfolio", data={"title": "作品一", "category": "activity", "description": "說明"})
    assert response.status_code == 302
    with app.app_context():
        portfolio_id = Portfolio.query.order_by(Portfolio.id.desc()).first().id

    response = client.post(f"/student/portfolio/{portfolio_id}/submit")
    assert response.status_code == 302
    with app.app_context():
        submission = db.session.get(Portfolio, portfolio_id).submissions[0]
        assert submission.status == "submitted"
        assert submission.goal_snapshots[0].title == "功能展示"


def test_student_cannot_edit_other_student_portfolio(tmp_path):
    app = portfolio_app(tmp_path)
    with app.app_context():
        other = User.query.filter_by(username="other").one()
        portfolio = Portfolio(student_id=other.id, title="他人的作品", category="其他")
        db.session.add(portfolio)
        db.session.commit()
        portfolio_id = portfolio.id

    client = app.test_client()
    login(client)
    assert client.get(f"/student/portfolio/{portfolio_id}/edit").status_code == 403


def test_private_evidence_download_checks_owner(tmp_path):
    app = portfolio_app(tmp_path)
    evidence_path = Path(tmp_path) / "private.txt"
    evidence_path.write_text("private", encoding="utf-8")
    with app.app_context():
        student = User.query.filter_by(username="student").one()
        portfolio = Portfolio(student_id=student.id, title="作品", category="其他")
        db.session.add(portfolio)
        db.session.flush()
        evidence = PortfolioEvidence(portfolio_id=portfolio.id, evidence_type="file", display_name="private.txt", file_path=str(evidence_path))
        db.session.add(evidence)
        db.session.commit()
        evidence_id = evidence.id

    client = app.test_client()
    login(client, "other")
    assert client.get(f"/student/evidence/{evidence_id}").status_code == 403
    client.post("/logout")
    login(client)
    response = client.get(f"/student/evidence/{evidence_id}")
    assert response.status_code == 200
    assert response.data == b"private"

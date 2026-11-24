from app import create_app
from app.extensions import db
from app.models import CourseRule, User


def admin_app(tmp_path):
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
        "UPLOAD_FOLDER": str(tmp_path),
    })
    with app.app_context():
        db.create_all()
        admin = User(username="admin", display_name="管理員", role="admin")
        admin.set_password("pw")
        db.session.add(admin)
        db.session.commit()
    return app


def test_admin_can_create_and_deactivate_course_rule(tmp_path):
    app = admin_app(tmp_path)
    client = app.test_client()
    client.post("/login", data={"username": "admin", "password": "pw"})

    response = client.post("/admin/course-rules", data={
        "school_year": "115",
        "course_name": "程式設計",
        "category": "專業課程",
        "requirement_type": "required",
        "credits": "3",
        "ability_domain": "程式智能開發",
    })
    assert response.status_code == 302
    with app.app_context():
        rule = CourseRule.query.one()
        assert rule.normalized_course_name == "程式設計"
        rule_id = rule.id

    response = client.post(f"/admin/course-rules/{rule_id}/toggle-active")
    assert response.status_code == 302
    with app.app_context():
        assert CourseRule.query.one().is_active is False

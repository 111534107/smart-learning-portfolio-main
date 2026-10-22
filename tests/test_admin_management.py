from app import create_app
from app.extensions import db
from app.models import ProjectType, RequirementItem, RequirementTemplate, User


def admin_app():
    app = create_app(
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
        }
    )
    with app.app_context():
        db.create_all()
        admin = User(username="manage-admin", display_name="Manage Admin", role="admin")
        student = User(username="manage-student", display_name="Manage Student", role="student")
        for user in (admin, student):
            user.set_password("test-password")
            db.session.add(user)
        db.session.commit()
    return app


def login(client, username):
    return client.post(
        "/login",
        data={"username": username, "password": "test-password"},
    )


def test_admin_can_disable_another_account_but_not_their_own_account():
    app = admin_app()
    client = app.test_client()
    login(client, "manage-admin")
    assert client.get("/admin/accounts").status_code == 200
    with app.app_context():
        admin_id = User.query.filter_by(username="manage-admin").one().id
        student_id = User.query.filter_by(username="manage-student").one().id

    disabled = client.post(f"/admin/accounts/{student_id}/toggle-active")

    assert disabled.status_code == 302
    with app.app_context():
        assert not db.session.get(User, student_id).is_active
    self_disable = client.post(f"/admin/accounts/{admin_id}/toggle-active")
    assert self_disable.status_code == 400
    with app.app_context():
        assert db.session.get(User, admin_id).is_active


def test_admin_can_build_a_project_type_template_and_requirement_item():
    app = admin_app()
    client = app.test_client()
    login(client, "manage-admin")
    assert client.get("/admin/project-types").status_code == 200

    project_response = client.post(
        "/admin/project-types",
        data={"code": "software", "name": "Software Project", "school_year": "115"},
    )

    assert project_response.status_code == 302
    with app.app_context():
        project_type = ProjectType.query.filter_by(code="software").one()
        project_type_id = project_type.id
        assert project_type.is_active
    toggle_project_response = client.post(f"/admin/project-types/{project_type_id}/toggle-active")
    assert toggle_project_response.status_code == 302
    with app.app_context():
        assert not db.session.get(ProjectType, project_type_id).is_active
    template_response = client.post(
        f"/admin/project-types/{project_type_id}/templates",
        data={"name": "Midterm evidence", "version": "1"},
    )
    assert template_response.status_code == 302
    with app.app_context():
        template = RequirementTemplate.query.filter_by(project_type_id=project_type_id).one()
        template_id = template.id
        assert template.is_active
    item_response = client.post(
        f"/admin/templates/{template_id}/items",
        data={"title": "Data model", "description": "Include ERD", "stage": "midterm", "sort_order": "10"},
    )
    assert item_response.status_code == 302
    with app.app_context():
        item = RequirementItem.query.filter_by(template_id=template_id).one()
        assert item.title == "Data model"
        assert item.is_required
        assert item.sort_order == 10
    optional_item_response = client.post(
        f"/admin/templates/{template_id}/items",
        data={"title": "Optional presentation", "stage": "review_1", "sort_order": "20", "is_required": "off"},
    )
    assert optional_item_response.status_code == 302
    with app.app_context():
        assert not RequirementItem.query.filter_by(title="Optional presentation").one().is_required


def test_non_admin_cannot_open_account_or_rule_management():
    client = admin_app().test_client()
    login(client, "manage-student")

    assert client.get("/admin/accounts").status_code == 403
    assert client.get("/admin/project-types").status_code == 403

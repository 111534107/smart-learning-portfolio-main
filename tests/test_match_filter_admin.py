from app import create_app
from app.extensions import db
from app.models import MatchFilterOption, User


def make_app(tmp_path):
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
        "UPLOAD_FOLDER": str(tmp_path),
    })
    with app.app_context():
        db.create_all()
        for username, role in (("admin", "admin"), ("stu", "student")):
            user = User(username=username, display_name=username, role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.commit()
    return app


def login(app, username):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def test_match_filter_admin_only(tmp_path):
    app = make_app(tmp_path)
    client = login(app, "stu")
    assert client.get("/admin/match-filters").status_code == 403
    response = client.post("/admin/match-filters", data={
        "category": "department", "label": "資訊管理系", "value": "資管",
    })
    assert response.status_code == 403
    assert client.post("/admin/match-filters/1/toggle-active").status_code == 403
    with app.app_context():
        assert MatchFilterOption.query.count() == 0


def test_match_filter_create_and_toggle(tmp_path):
    app = make_app(tmp_path)
    client = login(app, "admin")
    response = client.post("/admin/match-filters", data={
        "category": "department", "label": "資訊管理系", "value": "資管", "sort_order": "2",
    })
    assert response.status_code == 302
    with app.app_context():
        option = MatchFilterOption.query.one()
        assert option.sort_order == 2
        assert option.is_active is True
        option_id = option.id

    page = client.get("/admin/match-filters").get_data(as_text=True)
    assert "資訊管理系" in page and "科系" in page and "停用" in page

    assert client.post(f"/admin/match-filters/{option_id}/toggle-active").status_code == 302
    with app.app_context():
        assert MatchFilterOption.query.one().is_active is False
    assert "啟用" in client.get("/admin/match-filters").get_data(as_text=True)
    assert client.post("/admin/match-filters/9999/toggle-active").status_code == 404


def test_match_filter_rejects_duplicate_and_bad_input(tmp_path):
    app = make_app(tmp_path)
    client = login(app, "admin")
    data = {"category": "region", "label": "北部", "value": "north"}
    assert client.post("/admin/match-filters", data=data).status_code == 302
    assert client.post("/admin/match-filters", data={**data, "label": "北"}).status_code == 400
    assert client.post("/admin/match-filters", data={**data, "category": "bogus", "value": "x"}).status_code == 400
    assert client.post("/admin/match-filters", data={**data, "value": ""}).status_code == 400
    assert client.post("/admin/match-filters", data={**data, "value": "y", "sort_order": "abc"}).status_code == 400
    with app.app_context():
        assert MatchFilterOption.query.count() == 1


def test_match_filter_eligible_value_must_be_known_code(tmp_path):
    app = make_app(tmp_path)
    client = login(app, "admin")
    bad = {"category": "eligible", "label": "隨便", "value": "maybe"}
    assert client.post("/admin/match-filters", data=bad).status_code == 400
    assert client.post("/admin/match-filters", data={**bad, "value": "needs_check", "label": "需確認"}).status_code == 302
    with app.app_context():
        assert MatchFilterOption.query.one().value == "needs_check"


def test_match_filter_rejects_over_length(tmp_path):
    app = make_app(tmp_path)
    client = login(app, "admin")
    data = {"category": "department", "label": "資管", "value": "資管"}
    assert client.post("/admin/match-filters", data={**data, "label": "長" * 101}).status_code == 400
    assert client.post("/admin/match-filters", data={**data, "value": "長" * 101}).status_code == 400
    with app.app_context():
        assert MatchFilterOption.query.count() == 0


def _add_option(app):
    with app.app_context():
        option = MatchFilterOption(category="department", label="資管", value="資管", sort_order=1)
        db.session.add(option)
        db.session.commit()
        return option.id


def test_match_filter_edit_updates_label_and_sort_only(tmp_path):
    app = make_app(tmp_path)
    option_id = _add_option(app)
    client = login(app, "admin")
    response = client.post(f"/admin/match-filters/{option_id}/edit", data={
        "label": "資訊管理系", "sort_order": "5", "value": "hack", "category": "level",
    })
    assert response.status_code == 302
    with app.app_context():
        option = db.session.get(MatchFilterOption, option_id)
        assert (option.label, option.sort_order, option.value, option.category) == ("資訊管理系", 5, "資管", "department")
    assert client.post(f"/admin/match-filters/{option_id}/edit", data={"label": "", "sort_order": "1"}).status_code == 400
    assert client.post(f"/admin/match-filters/{option_id}/edit", data={"label": "長" * 101, "sort_order": "1"}).status_code == 400
    assert client.post(f"/admin/match-filters/{option_id}/edit", data={"label": "x", "sort_order": "abc"}).status_code == 400


def test_match_filter_edit_requires_admin(tmp_path):
    app = make_app(tmp_path)
    option_id = _add_option(app)
    client = login(app, "stu")
    assert client.post(f"/admin/match-filters/{option_id}/edit", data={"label": "x", "sort_order": "1"}).status_code == 403
    with app.app_context():
        assert db.session.get(MatchFilterOption, option_id).label == "資管"


def test_match_filter_edit_unknown_id_404(tmp_path):
    app = make_app(tmp_path)
    client = login(app, "admin")
    assert client.post("/admin/match-filters/9999/edit", data={"label": "x", "sort_order": "1"}).status_code == 404

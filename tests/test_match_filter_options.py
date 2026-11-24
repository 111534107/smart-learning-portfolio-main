from app import create_app
from app.extensions import db
from app.models import MatchFilterOption


def make_app(tmp_path):
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
        "UPLOAD_FOLDER": str(tmp_path),
    })
    with app.app_context():
        db.create_all()
    return app


def test_inactive_options_hidden(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db.session.add_all([
            MatchFilterOption(category="department", label="資管系", value="資管", sort_order=1, is_active=True),
            MatchFilterOption(category="department", label="資工系", value="資工", sort_order=2, is_active=False),
        ])
        db.session.commit()

        labels = [option.label for option in MatchFilterOption.active_options("department")]

        assert labels == ["資管系"]


def test_options_ordered_by_sort_order_then_id(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db.session.add_all([
            MatchFilterOption(category="region", label="南部", value="south", sort_order=2),
            MatchFilterOption(category="region", label="北部", value="north", sort_order=1),
            MatchFilterOption(category="level", label="四技", value="tech", sort_order=1),
        ])
        db.session.commit()

        assert [o.label for o in MatchFilterOption.active_options("region")] == ["北部", "南部"]


def test_unknown_category_rejected():
    import pytest

    with pytest.raises(ValueError):
        MatchFilterOption(category="unknown", label="x", value="x")

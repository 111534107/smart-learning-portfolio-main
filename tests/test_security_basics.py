import pytest

from scripts.init_db import create_admin_user
from app import create_app
from app.extensions import db


def test_admin_creation_requires_explicit_password(monkeypatch):
    monkeypatch.delenv("ADMIN_DEFAULT_PASSWORD", raising=False)
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        with pytest.raises(RuntimeError, match="ADMIN_DEFAULT_PASSWORD"):
            create_admin_user()

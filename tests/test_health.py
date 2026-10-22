from app import create_app
from app.extensions import db


def health_app():
    app = create_app(
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
        }
    )
    with app.app_context():
        db.create_all()
    return app


def test_health_reports_application_and_database_ready():
    response = health_app().test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"database": "ok", "status": "ok"}

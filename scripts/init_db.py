import os
import sys

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.extensions import db
from app.models import User


def create_admin_user():
    admin = User.query.filter_by(username="admin").first()
    if admin:
        return "admin user already exists"

    default_password = os.getenv("ADMIN_DEFAULT_PASSWORD")
    if not default_password:
        raise RuntimeError("ADMIN_DEFAULT_PASSWORD must be set before creating an admin user")
    admin = User(
        username="admin",
        display_name="系統管理者",
        role="admin",
        email="admin@example.com",
    )
    admin.set_password(default_password)
    db.session.add(admin)
    db.session.commit()
    return "created admin user: admin (password supplied through ADMIN_DEFAULT_PASSWORD)"


def main():
    app = create_app()
    with app.app_context():
        db.create_all()
        result = create_admin_user()
        print("database tables created")
        print(result)


if __name__ == "__main__":
    main()

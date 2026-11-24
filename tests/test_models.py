from app import create_app
from app.extensions import db
from app.models import Portfolio, User


def test_user_password_hashing():
    user = User(username="s001", display_name="學生 S001", role="student")
    user.set_password("secret")

    assert user.password_hash != "secret"
    assert user.check_password("secret")
    assert not user.check_password("wrong")


def test_portfolio_model_can_be_created_in_memory():
    app = create_app(
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "TESTING": True,
        }
    )

    with app.app_context():
        db.create_all()
        user = User(username="s002", display_name="學生 S002", role="student")
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()

        portfolio = Portfolio(
            student_id=user.id,
            title="Flask 專題",
            category="課程作品",
            description="測試用學習歷程",
        )
        db.session.add(portfolio)
        db.session.commit()

        assert Portfolio.query.count() == 1
        assert Portfolio.query.first().student.username == "s002"

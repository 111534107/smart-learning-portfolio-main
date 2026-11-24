from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def test_makeup_season_migration_preserves_existing_course_rows(tmp_path):
    database_path = tmp_path / "makeup-season.db"
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
        "TESTING": True,
    })
    runner = app.test_cli_runner()
    with app.app_context():
        db.session.execute(text(
            "CREATE TABLE learning_course_records (id INTEGER PRIMARY KEY, course_name VARCHAR(150) NOT NULL)"
        ))
        db.session.execute(text(
            "INSERT INTO learning_course_records (id, course_name) VALUES (1, '既有課程')"
        ))
        db.session.commit()

    assert runner.invoke(args=["db", "stamp", "b7e1a0c4d9f2"]).exit_code == 0
    result = runner.invoke(args=["db", "upgrade"])
    assert result.exit_code == 0, result.output
    with app.app_context():
        columns = {column["name"] for column in inspect(db.engine).get_columns("learning_course_records")}
        assert "makeup_season" in columns
        row = db.session.execute(text(
            "SELECT course_name, makeup_season FROM learning_course_records"
        )).one()
        assert row == ("既有課程", None)

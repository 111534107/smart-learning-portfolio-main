from app import create_app
from app.extensions import db
from sqlalchemy import inspect


def test_flask_migrate_commands_are_registered_on_the_application():
    app = create_app(
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "TESTING": True,
        }
    )

    result = app.test_cli_runner().invoke(args=["db", "--help"])

    assert result.exit_code == 0
    assert "upgrade" in result.output


def test_teacher_feedback_migration_creates_the_required_table(tmp_path):
    database_path = tmp_path / "migration-check.db"
    app = create_app(
        {
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            "TESTING": True,
        }
    )

    result = app.test_cli_runner().invoke(args=["db", "upgrade"])

    assert result.exit_code == 0
    with app.app_context():
        columns = {column["name"] for column in inspect(db.engine).get_columns("teacher_review_feedback")}
    assert {"id", "submission_id", "teacher_id", "comment", "created_at"} <= columns


def test_teacher_feedback_migration_downgrade_removes_the_table(tmp_path):
    database_path = tmp_path / "migration-downgrade-check.db"
    app = create_app(
        {
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            "TESTING": True,
        }
    )
    runner = app.test_cli_runner()

    assert runner.invoke(args=["db", "upgrade"]).exit_code == 0
    assert runner.invoke(args=["db", "downgrade", "base"]).exit_code == 0
    with app.app_context():
        assert not inspect(db.engine).has_table("teacher_review_feedback")


def test_admission_main_line_migration_upgrades_and_downgrades(tmp_path):
    database_path = tmp_path / "admission-migration.db"
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}", "TESTING": True})
    runner = app.test_cli_runner()

    assert runner.invoke(args=["db", "upgrade"]).exit_code == 0
    with app.app_context():
        tables = set(inspect(db.engine).get_table_names())
    assert {"admission_rule_versions", "admission_rule_items", "student_targets",
            "class_advisors", "package_reviews"} <= tables

    assert runner.invoke(args=["db", "downgrade", "fc61707846c7"]).exit_code == 0
    with app.app_context():
        db.engine.dispose()
        tables = set(inspect(db.engine).get_table_names())
    assert "package_reviews" not in tables


def test_transfer_credit_migration_creates_and_removes_its_table(tmp_path):
    database_path = tmp_path / "transfer-credit-migration.db"
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}", "TESTING": True})
    runner = app.test_cli_runner()

    assert runner.invoke(args=["db", "upgrade"]).exit_code == 0
    with app.app_context():
        columns = {column["name"] for column in inspect(db.engine).get_columns("transfer_credit_records")}
    assert {"student_id", "status", "submitted_on", "missing_documents", "note",
            "teacher_confirmed", "teacher_id", "teacher_confirmed_at"} <= columns

    assert runner.invoke(args=["db", "downgrade", "fc61707846c7"]).exit_code == 0
    with app.app_context():
        db.engine.dispose()
        assert not inspect(db.engine).has_table("transfer_credit_records")


def test_portfolio_source_migration_adds_and_removes_columns(tmp_path):
    database_path = tmp_path / "portfolio-source.db"
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}", "TESTING": True})
    runner = app.test_cli_runner()
    with app.app_context(), db.engine.begin() as conn:
        # 模擬正式資料庫裡早已存在、但還沒有 source 欄位的 users、portfolios 表
        conn.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        conn.exec_driver_sql(
            "CREATE TABLE portfolios (id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL, title VARCHAR(150) NOT NULL,"
            " category VARCHAR(50) NOT NULL, description TEXT, course_name VARCHAR(100), school_year INTEGER,"
            " semester INTEGER, status VARCHAR(20) NOT NULL, submitted_at DATETIME, created_at DATETIME NOT NULL,"
            " updated_at DATETIME NOT NULL)")

    assert runner.invoke(args=["db", "upgrade"]).exit_code == 0
    with app.app_context():
        db.engine.dispose()
        columns = {column["name"] for column in inspect(db.engine).get_columns("portfolios")}
    assert {"source", "source_document_id"} <= columns
    with app.app_context():
        assert inspect(db.engine).has_table("award_certificates")

    assert runner.invoke(args=["db", "downgrade", "b7d2e9a41c35"]).exit_code == 0
    with app.app_context():
        db.engine.dispose()
        columns = {column["name"] for column in inspect(db.engine).get_columns("portfolios")}
    assert "source" not in columns


def test_soft_delete_migration_upgrades_downgrades_and_upgrades_again(tmp_path):
    """M10：deleted_at 欄位從零升級、降級、再升級都正常（只在 SQLite 測；MySQL 要先備份再執行）。"""
    fresh = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'fresh.db'}", "TESTING": True})
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'old.db'}", "TESTING": True})
    runner = app.test_cli_runner()

    def columns(table):
        with app.app_context():
            db.engine.dispose()
            return {column["name"] for column in inspect(db.engine).get_columns(table)}

    # 從零：基本表還沒建時要能跳過，降到 base 再升回來也不會錯
    fresh_runner = fresh.test_cli_runner()
    assert fresh_runner.invoke(args=["db", "upgrade"]).exit_code == 0
    assert fresh_runner.invoke(args=["db", "downgrade", "base"]).exit_code == 0
    assert fresh_runner.invoke(args=["db", "upgrade"]).exit_code == 0

    # 舊資料庫：表已存在但還沒有 deleted_at（模擬上一版的正式資料庫）
    with app.app_context():
        db.create_all()
        with db.engine.begin() as connection:
            for table in ("portfolio_evidence", "portfolios"):
                connection.exec_driver_sql(f"ALTER TABLE {table} DROP COLUMN deleted_at")
    assert runner.invoke(args=["db", "stamp", "c4e2b7a91d05"]).exit_code == 0

    assert runner.invoke(args=["db", "upgrade"]).exit_code == 0
    assert "deleted_at" in columns("portfolios") and "deleted_at" in columns("portfolio_evidence")
    assert runner.invoke(args=["db", "downgrade", "c4e2b7a91d05"]).exit_code == 0
    assert "deleted_at" not in columns("portfolios") and "deleted_at" not in columns("portfolio_evidence")
    assert runner.invoke(args=["db", "upgrade"]).exit_code == 0
    assert "deleted_at" in columns("portfolios") and "deleted_at" in columns("portfolio_evidence")

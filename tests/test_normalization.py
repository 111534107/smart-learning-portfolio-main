"""資料庫正規化（2026-11-13）：多值欄位拆成獨立資料表、可推得的重複欄位拿掉；遷移要把既有資料搬過去，降版要組回來。"""
from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db
from app.models import AdmissionRequirementItem, Portfolio, User


def _app(tmp_path, name="n.db"):
    return create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / name}", "TESTING": True})


def test_migration_moves_multi_value_columns_into_rows_and_back(tmp_path):
    app = _app(tmp_path)
    runner = app.test_cli_runner()
    result = runner.invoke(args=["db", "upgrade", "b20261112z01"])
    assert result.exit_code == 0, result.output
    with app.app_context():
        with db.engine.begin() as conn:
            # 舊的遷移鏈不建 users、portfolios（正式環境由 init_db 建）；這裡照舊版欄位建，模擬已上線的資料庫
            conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(80))"))
            conn.execute(text("CREATE TABLE portfolios (id INTEGER PRIMARY KEY, student_id INTEGER REFERENCES users(id), "
                              "title VARCHAR(150), category VARCHAR(50), domain_tags VARCHAR(200))"))
            conn.execute(text("INSERT INTO users (id, username) VALUES (1, 's')"))
            conn.execute(text("INSERT INTO admission_rule_versions (id, program_code, admission_year, school_name, department_name, "
                              "admission_category, status, data_origin, created_at) VALUES (1, 'P1', 116, '測試大學', '資管系', '甄選', 'published', 'seed', '2026-01-01')"))
            conn.execute(text("INSERT INTO admission_rule_items (id, rule_version_id, source_item_name, weight_percent, mapped_categories, "
                              "mapping_status, is_required, sort_order) VALUES (1, 1, '專業成果', 30, 'competition,credential,competition', 'confirmed', 1, 0)"))
            conn.execute(text("INSERT INTO portfolios (id, student_id, title, category, domain_tags) "
                              "VALUES (1, 1, '黑客松', 'competition', '系統開發、醫療資訊')"))

    result = runner.invoke(args=["db", "upgrade"])
    assert result.exit_code == 0, result.output
    with app.app_context():
        columns = lambda table: {c["name"] for c in inspect(db.engine).get_columns(table)}
        assert "mapped_categories" not in columns("admission_rule_items")
        assert "domain_tags" not in columns("portfolios")
        assert "student_id" not in columns("award_certificates")
        assert "case_id" not in columns("notifications")
        assert db.session.get(AdmissionRequirementItem, 1).category_keys == ["competition", "credential"]
        with db.engine.connect() as conn:
            tags = conn.execute(text("SELECT tag FROM portfolio_domain_tags ORDER BY sort_order")).scalars().all()
        assert tags == ["系統開發", "醫療資訊"]

    assert runner.invoke(args=["db", "downgrade", "b20261112z01"]).exit_code == 0
    with app.app_context():
        with db.engine.connect() as conn:
            assert conn.execute(text("SELECT mapped_categories FROM admission_rule_items")).scalar() == "competition,credential"
            assert conn.execute(text("SELECT domain_tags FROM portfolios")).scalar() == "系統開發、醫療資訊"


def test_multi_value_attributes_read_and_write_as_rows(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        user = User(username="s", display_name="s", role="student")
        user.set_password("pw")
        db.session.add(user)
        db.session.flush()
        record = Portfolio(student_id=user.id, title="t", category="activity", domain_tags="系統開發, 資料分析、系統開發")
        db.session.add(record)
        db.session.commit()
        assert [row.tag for row in record.domain_tag_rows] == ["系統開發", "資料分析"]
        record.domain_tags = ""
        db.session.commit()
        assert record.domain_tags is None
        assert db.session.execute(text("SELECT COUNT(*) FROM portfolio_domain_tags")).scalar() == 0


def test_derived_columns_still_work_in_queries(tmp_path):
    """拿掉的 student_id、case_id 仍可在查詢裡用（轉成子查詢），舊程式的 filter_by 不會默默查不到。"""
    from app.models import AwardCertificate, GraduationCase, GraduationCaseEvent, Notification

    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        user = User(username="s", display_name="s", role="student")
        user.set_password("pw")
        db.session.add(user)
        db.session.flush()
        record = Portfolio(student_id=user.id, title="t", category="service")
        cert = AwardCertificate(portfolio=record, title="服務證明", body="b", issuer="資管科")
        case = GraduationCase(student_id=user.id, case_type="gap", item="證照", status="open")
        db.session.add_all([record, cert, case])
        db.session.flush()
        event = GraduationCaseEvent(case_id=case.id, event_type="created")
        db.session.add(event)
        db.session.flush()
        db.session.add(Notification(recipient_id=user.id, event_id=event.id, message="m"))
        db.session.commit()

        assert AwardCertificate.query.filter_by(student_id=user.id).one().student_id == user.id
        assert Notification.query.filter_by(case_id=case.id).one().case_id == case.id

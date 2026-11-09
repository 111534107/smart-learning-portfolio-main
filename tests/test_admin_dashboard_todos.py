"""管理員首頁「今天要處理什麼」：數字卡只算已存在的資料，每張卡連到處理頁（全部為合成資料）。"""
from datetime import datetime, timedelta, timezone

from app import create_app
from app.extensions import db
from app.models import (
    AdmissionEligibilityRule,
    AdmissionProgram,
    AdmissionRequirementItem,
    AdmissionScheduleEvent,
    AgentTask,
    ClassAdvisor,
    DocumentExtraction,
    PublicSource,
    PublicSourceChange,
    PublicSourceSnapshot,
    SourceDocument,
    StudentProfile,
    User,
)


def todo_app(**extra):
    config = {"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "WTF_CSRF_ENABLED": False}
    config.update(extra)
    app = create_app(config)
    with app.app_context():
        db.create_all()
        admin = User(username="todo-admin", display_name="合成管理員", role="admin")
        teacher = User(username="todo-teacher", display_name="合成導師", role="teacher")
        student = User(username="todo-student", display_name="合成學生", role="student")
        other = User(username="todo-student2", display_name="合成學生二", role="student")
        for user in (admin, teacher, student, other):
            user.set_password("pw")
            db.session.add(user)
        db.session.flush()
        db.session.add_all([
            StudentProfile(user_id=student.id, student_no="S900001", class_name="資管五甲"),
            StudentProfile(user_id=other.id, student_no="S900002", class_name="資管五乙"),
            ClassAdvisor(teacher_id=teacher.id, class_name="資管五甲", school_year=115),
        ])
        candidate = AdmissionProgram(program_code="X001", admission_year=116, school_name="合成科大",
                                     department_name="資訊管理系", status="candidate")
        published = AdmissionProgram(program_code="X002", admission_year=115, school_name="合成科大",
                                     department_name="資訊工程系", status="published")
        db.session.add_all([candidate, published])
        db.session.flush()
        db.session.add_all([
            AdmissionRequirementItem(rule_version_id=published.id, source_item_name="證照", weight_percent=30,
                                     mapping_status="pending"),
            AdmissionRequirementItem(rule_version_id=published.id, source_item_name="自傳", weight_percent=20,
                                     mapping_status="confirmed"),
            AdmissionEligibilityRule(rule_version_id=published.id, condition_type="graduation", operator="eq",
                                     description="五專畢業", mapping_status="pending"),
        ])
        ok_source = PublicSource(name="正常簡章", url="https://example.test/ok.pdf", source_type="url")
        bad_source = PublicSource(name="失效簡章", url="https://example.test/gone.pdf", source_type="url")
        db.session.add_all([ok_source, bad_source])
        db.session.flush()
        snap = PublicSourceSnapshot(source_id=ok_source.id, content_hash="a" * 64)
        db.session.add(snap)
        db.session.flush()
        db.session.add_all([
            PublicSourceChange(snapshot_id=snap.id, change_type="first", diff_json={"size": 1}, status="candidate"),
            AgentTask(task_type="admission_source_check", requester_id=admin.id, target_type="public_source",
                      target_id=bad_source.id, status="succeeded"),
            AgentTask(task_type="admission_source_check", requester_id=admin.id, target_type="public_source",
                      target_id=bad_source.id, status="failed", error_message="抓取失敗：404"),
            AgentTask(task_type="admission_source_check", requester_id=admin.id, target_type="public_source",
                      target_id=ok_source.id, status="failed"),
            AgentTask(task_type="admission_source_check", requester_id=admin.id, target_type="public_source",
                      target_id=ok_source.id, status="succeeded"),
        ])
        for name in ("網路報名", "放榜"):
            db.session.add(AdmissionScheduleEvent(channel="skill", admission_year=116, name=name,
                                                  start_at=datetime(2027, 3, 1), status="candidate"))
        recent = SourceDocument(owner_id=student.id, document_type="transcript", display_name="a.pdf",
                                file_path="x/a.pdf", sha256="b" * 64)
        old = SourceDocument(owner_id=student.id, document_type="transcript", display_name="b.pdf",
                             file_path="x/b.pdf", sha256="c" * 64)
        db.session.add_all([recent, old])
        db.session.flush()
        long_ago = datetime.now(timezone.utc) - timedelta(days=30)
        db.session.add_all([
            DocumentExtraction(source_document_id=recent.id, provider="local", status="failed"),
            DocumentExtraction(source_document_id=old.id, provider="local", status="failed",
                               created_at=long_ago, updated_at=long_ago),
        ])
        db.session.commit()
    return app


def admin_page(app):
    client = app.test_client()
    client.post("/login", data={"username": "todo-admin", "password": "pw"})
    return client, client.get("/admin/dashboard").get_data(as_text=True)


def test_admin_todo_counts_come_from_existing_data():
    app = todo_app()
    with app.test_request_context():
        from app.services.admin_todos import admin_todos
        counts = {todo["key"]: todo["count"] for todo in admin_todos()}
    assert counts == {
        "candidate-programs": 1,
        "candidate-schedules": 1,       # 同一管道同一學年度算一組
        "pending-changes": 1,
        "failed-sources": 1,            # 只看最近一次檢查
        "pending-mapping": 2,           # 評分項目 1＋報考資格 1
        "curriculum": 0,                # 11-09 修業科目表代理：這份資料沒有候選版本
        "classes-without-advisor": 1,   # 資管五乙
        "ocr-failures": 1,              # 30 天前的不算
    }


def test_admin_dashboard_cards_link_to_handling_pages():
    client, page = admin_page(todo_app())
    assert 'data-admin-todos' in page
    assert "今天有 7 類事情要處理" in page
    for href in ("/admin/programs", "/admin/agent#candidate-schedules", "/admin/agent#source-changes",
                 "/admin/agent#public-sources", "/admin/classes", "/admin/ocr"):
        assert f'href="{href}"' in page
        assert client.get(href.split("#")[0]).status_code == 200
    assert "雲端儲存未連線" not in page


def test_agent_page_marks_failed_source_red():
    client, _ = admin_page(todo_app())
    page = client.get("/admin/agent").get_data(as_text=True)
    assert page.count("上次檢查失敗，網址可能失效") == 1
    assert 'id="candidate-schedules"' in page and 'id="source-changes"' in page and 'id="public-sources"' in page


def test_drive_disconnected_shows_storage_card():
    _, page = admin_page(todo_app(STORAGE_BACKEND="google_drive"))
    assert "雲端儲存未連線" in page and 'href="/admin/storage"' in page


def test_empty_system_says_nothing_to_do():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        admin = User(username="solo-admin", display_name="合成管理員", role="admin")
        admin.set_password("pw")
        db.session.add(admin)
        db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": "solo-admin", "password": "pw"})
    page = client.get("/admin/dashboard").get_data(as_text=True)
    assert "目前沒有待處理的事項" in page and "0 類待處理" in page

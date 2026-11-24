"""備審工作台導覽模型：固定四個階段、狀態跟資料一致、下一步不指向已完成的階段。（僅為測試資料）"""
from app.extensions import db
from app.models import AdmissionProgram, Portfolio, StudentTarget, User
from app.services import workbench_nav
from tests.test_autobiography import ANSWERS, app, choose_target, login, program  # noqa: F401


def _ctx(app):
    with app.test_request_context():
        student = User.query.filter_by(username="stu").one()
        prog = AdmissionProgram.query.filter_by(program_code="208003").one()
        return workbench_nav.stages(student, prog), workbench_nav.schools(student, prog.id)


def test_stages_are_always_four_in_fixed_order(app):
    client = login(app)
    choose_target(app, client)
    stages, _ = _ctx(app)
    assert [s["key"] for s in stages] == ["gap", "bio", "preview", "send"]
    assert [s["label"] for s in stages] == ["① 備齊資料", "② 寫自傳", "③ 預覽 A4", "④ 送審與下載"]
    assert all(s["url"].startswith("/student/") for s in stages)


def test_bio_stage_state_follows_draft(app):
    client = login(app)
    choose_target(app, client)
    stages, _ = _ctx(app)
    assert stages[1]["state"] == "todo"
    client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})
    stages, _ = _ctx(app)
    assert stages[1]["state"] == "doing"
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        db.session.add(Portfolio(student_id=student.id, title="草稿後新增的競賽", category="competition",
                                 school_year=4, status="confirmed", description="佳作"))
        db.session.commit()
    stages, _ = _ctx(app)
    assert stages[1]["state"] == "update"


def test_send_stage_done_only_when_review_confirmed(app):
    client = login(app)
    choose_target(app, client)
    stages, _ = _ctx(app)
    assert stages[3]["state"] in ("todo", "doing")
    assert stages[3]["state"] != "done"


def test_schools_marks_current_and_orders_by_selection(app):
    client = login(app)
    choose_target(app, client)
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        other = AdmissionProgram.query.filter(AdmissionProgram.program_code != "208003").first()
        db.session.add(StudentTarget(student_id=student.id, rule_version_id=other.id))
        db.session.commit()
    _, schools = _ctx(app)
    assert len(schools) == 2 and schools[0]["current"] and not schools[1]["current"]
    assert all({"program_id", "name", "current", "url"} <= set(s) for s in schools)


def test_next_stage_skips_done_and_returns_none_at_end():
    stages = [{"key": "gap", "state": "done"}, {"key": "bio", "state": "doing"},
              {"key": "preview", "state": "todo"}, {"key": "send", "state": "todo"}]
    assert workbench_nav.next_stage(stages, "gap")["key"] == "bio"
    assert workbench_nav.next_stage(stages, "bio")["key"] == "preview"
    assert workbench_nav.next_stage(stages, "send") is None

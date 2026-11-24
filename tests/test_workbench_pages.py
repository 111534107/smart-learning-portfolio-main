"""備審工作台外框：四個階段頁都有同一個外框、標出目前階段；批次入口只在 2 所以上；沒有目標導去選校。（僅為測試資料）"""
from app.extensions import db
from app.models import AdmissionProgram, StudentTarget, User
from tests.test_autobiography import ANSWERS, app, choose_target, login, program  # noqa: F401


def test_each_stage_page_renders_shell_with_active_stage(app):
    client = login(app)
    choose_target(app, client)
    pid = program(app)
    client.post("/student/autobiography/generate", data={"program_id": pid, **ANSWERS})
    for url, stage in ((f"/student/targets/{pid}", "gap"), (f"/student/autobiography?program_id={pid}", "bio"),
                       (f"/student/portfolio-view/{pid}", "preview")):
        page = client.get(url).get_data(as_text=True)
        assert "data-workbench" in page and f'data-stage="{stage}"' in page, url
        assert page.count('aria-label="備審階段"') == 1


def test_batch_entry_only_with_two_or_more_targets(app):
    client = login(app)
    choose_target(app, client)
    pid = program(app)
    assert "data-workbench-batch" not in client.get(f"/student/targets/{pid}").get_data(as_text=True)
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        other = AdmissionProgram.query.filter(AdmissionProgram.program_code != "208003").first()
        db.session.add(StudentTarget(student_id=student.id, rule_version_id=other.id))
        db.session.commit()
    assert "data-workbench-batch" in client.get(f"/student/targets/{pid}").get_data(as_text=True)


def test_workbench_entry_redirects(app):
    client = login(app)
    response = client.get("/student/workbench")
    assert response.status_code == 302 and "/student/targets" in response.headers["Location"]
    choose_target(app, client)
    response = client.get("/student/workbench")
    assert response.status_code == 302 and f"/student/targets/{program(app)}" in response.headers["Location"]


def test_next_step_button_points_forward(app):
    client = login(app)
    choose_target(app, client)
    pid = program(app)
    client.post("/student/autobiography/generate", data={"program_id": pid, **ANSWERS})
    page = client.get(f"/student/autobiography?program_id={pid}").get_data(as_text=True)
    assert "data-workbench-next" in page and "下一步：③ 預覽 A4" in page


def test_resume_entry_lives_under_my_data_not_target_flow(app):
    client = login(app)
    choose_target(app, client)
    assert "data-resume-entry" in client.get("/student/learning-profile").get_data(as_text=True)
    gap = client.get(f"/student/targets/{program(app)}").get_data(as_text=True)
    assert "/student/internship-resume" not in gap

"""批次產生自傳：逐校系依序產生、可查進度、別人看不到、失敗可重試。（僅為測試資料）"""
from app.extensions import db
from app.models import AdmissionProgram, LearningProfileOutput, StudentTarget, User
from app.services import autobiography_batch
from tests.test_autobiography import ANSWERS, app, choose_target, login, program  # noqa: F401


def _generate_first(client, app):
    pid = program(app)
    response = client.post("/student/autobiography/generate", data={"program_id": pid, **ANSWERS})
    assert response.status_code == 302
    return pid


def test_batch_page_without_targets_goes_to_target_list(app):
    client = login(app)
    response = client.get("/student/autobiography/batch")
    assert response.status_code == 302 and "/student/targets" in response.headers["Location"]


def test_batch_generates_every_target_and_reports_status(app):
    client = login(app)
    choose_target(app, client)
    pid = _generate_first(client, app)
    page = client.get("/student/autobiography/batch")
    assert page.status_code == 200
    start = client.post("/student/autobiography/batch/start")
    assert start.status_code == 200
    job_id = start.get_json()["job_id"]
    status = client.get(f"/student/autobiography/batch/{job_id}/status").get_json()
    assert status["status"] == "done"
    assert [item["program_id"] for item in status["items"]] == [pid]
    assert status["items"][0]["status"] == "done"
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        drafts = LearningProfileOutput.query.filter_by(student_id=student.id).all()
        assert len(drafts) >= 2  # 原本一份，批次又存了新的一版（舊版保留）


def test_batch_fails_politely_when_student_has_not_answered(app):
    client = login(app)
    choose_target(app, client)  # 沒回答過任何題目
    job_id = client.post("/student/autobiography/batch/start").get_json()["job_id"]
    status = client.get(f"/student/autobiography/batch/{job_id}/status").get_json()
    assert status["status"] == "failed"
    assert status["items"][0]["status"] == "failed" and "自己的話" in status["items"][0]["message"]
    retry = client.post("/student/autobiography/batch/retry", data={"job_id": job_id, "program_id": status["items"][0]["program_id"]})
    assert retry.status_code == 200  # 失敗的可以重試（這次仍然沒回答，所以會再失敗）


def test_other_student_cannot_see_the_job(app):
    client = login(app)
    choose_target(app, client)
    _generate_first(client, app)
    job_id = client.post("/student/autobiography/batch/start").get_json()["job_id"]
    other = login(app, "other")
    assert other.get(f"/student/autobiography/batch/{job_id}/status").status_code == 404
    assert other.post("/student/autobiography/batch/retry", data={"job_id": job_id, "program_id": 1}).status_code == 400


def test_retry_rejects_items_that_did_not_fail(app):
    client = login(app)
    choose_target(app, client)
    pid = _generate_first(client, app)
    job_id = client.post("/student/autobiography/batch/start").get_json()["job_id"]
    assert client.post("/student/autobiography/batch/retry", data={"job_id": job_id, "program_id": pid}).status_code == 400

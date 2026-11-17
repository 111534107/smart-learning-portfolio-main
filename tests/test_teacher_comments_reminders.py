"""2026-11-18 併入組員 111534107 提交 46531f2 的教師端 5 項功能（依新版架構改寫）。

1. 送審版本確認：導師看送審時的自傳；送審後自傳有新版不能確認，要請學生重新送審。
2. 自傳段落註解：同段多則、學生和導師回覆、已處理／待處理、舊版意見保留、不能刪。
3. 教師編輯頁：拿掉「給學生的意見」欄，註解在各段下方，有未儲存提醒。
4. 備審準備提醒：導師改好提醒內容送站內通知，學生點通知到該校系備審頁。
5. 班級目標統計：各目標準備度與待補類別、各校系人數（同校多科系學校只算一次）。
以下皆為測試資料。
"""

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    AdmissionProgram,
    AdmissionRequirementItem,
    AuditLog,
    AutobiographyComment,
    ClassAdvisor,
    LearningProfileOutput,
    Notification,
    PackageReview,
    StudentProfile,
    StudentTarget,
    User,
)
from app.services import autobiography_service

PARAGRAPHS = [
    {"title": "學習動機", "text": "我想讀資管（測試資料）。", "sources": []},
    {"title": "未來規劃", "text": "我想做系統分析（測試資料）。", "sources": []},
]


@pytest.fixture
def setup():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "MIN_REVIEW_GRADE": 1})
    with app.app_context():
        db.create_all()
        users = [User(username=name, display_name=label, role=role) for name, label, role in [
            ("stu", "測試學生甲", "student"), ("stu2", "測試學生乙", "student"), ("stu3", "測試學生丙", "student"),
            ("teacher", "測試導師", "teacher"), ("other", "別班導師", "teacher"),
        ]]
        for user in users:
            user.set_password("pw")
        db.session.add_all(users)
        db.session.flush()
        stu, stu2, stu3, teacher, other = users
        db.session.add_all([
            StudentProfile(user_id=stu.id, student_no="DEMO-1", class_name="測試甲班", admission_year=110),
            StudentProfile(user_id=stu2.id, student_no="DEMO-2", class_name="測試甲班", admission_year=110),
            StudentProfile(user_id=stu3.id, student_no="DEMO-3", class_name="測試乙班", admission_year=110),
            ClassAdvisor(teacher_id=teacher.id, class_name="測試甲班", school_year=115),
            ClassAdvisor(teacher_id=other.id, class_name="測試乙班", school_year=115),
        ])
        programs = {}
        for key, school, dept in [("im", "測試科技大學", "資訊管理系"), ("cs", "測試科技大學", "資訊工程系"),
                                  ("other_school", "示範大學", "資訊管理系")]:
            program = AdmissionProgram(program_code=key.upper(), admission_year=115, school_name=school,
                                       department_name=dept, status="published")
            item = AdmissionRequirementItem(source_item_name="證照與競賽", weight_percent=100,
                                            mapping_status="confirmed", sort_order=0)
            item.mapped_categories = "credential,competition"
            program.items = [item]
            db.session.add(program)
            db.session.flush()
            programs[key] = program.id
        db.session.add_all([
            StudentTarget(student_id=stu.id, rule_version_id=programs["im"]),
            StudentTarget(student_id=stu.id, rule_version_id=programs["cs"]),
            StudentTarget(student_id=stu.id, rule_version_id=programs["other_school"]),
            StudentTarget(student_id=stu2.id, rule_version_id=programs["im"]),
        ])
        output = LearningProfileOutput(student_id=stu.id, output_type=autobiography_service.OUTPUT_TYPE, content_json={
            "program_id": programs["im"], "paragraphs": PARAGRAPHS, "version": 1, "editor_role": "ai",
            "provider": "demo", "facts": [], "answers": {},
        }, source_snapshot_json={})
        db.session.add(output)
        db.session.commit()
        ids = {u.username: u.id for u in users}
        ids.update(programs)
        ids["output"] = output.id
    return app, ids


def client_for(app, username):
    client = app.test_client()
    staff = username in {"teacher", "other"}
    client.post("/staff/login" if staff else "/login", data={"username": username, "password": "pw"})
    return client


def latest_output_id(app, ids):
    with app.app_context():
        return (LearningProfileOutput.query.filter_by(student_id=ids["stu"])
                .order_by(LearningProfileOutput.id.desc()).first().id)


def student_saves(app, ids, student, texts):
    output_id = latest_output_id(app, ids)
    data = {f"paragraph_{i}": text for i, text in enumerate(texts)}
    assert student.post(f"/student/autobiography/{output_id}/save", data=data).status_code == 302
    return latest_output_id(app, ids)


# ---------- 1. 送審版本確認 ----------

def test_teacher_sees_submitted_autobiography_and_cannot_confirm_after_new_version(setup):
    app, ids = setup
    student, teacher = client_for(app, "stu"), client_for(app, "teacher")
    student.post(f"/student/targets/{ids['im']}/review")
    student_saves(app, ids, student, ["送審後才改的第一段（測試資料）", PARAGRAPHS[1]["text"]])

    html = teacher.get(f"/teacher/students/{ids['stu']}").get_data(as_text=True)
    assert "送審時的自傳（第 1 版）" in html and PARAGRAPHS[0]["text"] in html
    assert "data-autobiography-changed" in html and "目前第 2 版" in html
    gap_html = student.get(f"/student/targets/{ids['im']}").get_data(as_text=True)
    assert "data-resend-hint" in gap_html

    with app.app_context():
        review = PackageReview.query.one()
        review_id, taken_at = review.id, review.snapshot_json["taken_at"]
    blocked = teacher.post(f"/teacher/package-reviews/{review_id}",
                           data={"decision": "confirmed", "taken_at": taken_at})
    assert "notice=autobiography_changed" in blocked.location
    with app.app_context():
        assert db.session.get(PackageReview, review_id).status == "pending"
    # 仍可請學生修改
    teacher.post(f"/teacher/package-reviews/{review_id}",
                 data={"decision": "needs_revision", "comment": "請重新送審", "taken_at": taken_at})
    with app.app_context():
        assert db.session.get(PackageReview, review_id).status == "needs_revision"

    # 學生重新送審後可以確認，也還能撤回
    student.post(f"/student/targets/{ids['im']}/review")
    with app.app_context():
        review = PackageReview.query.order_by(PackageReview.id.desc()).first()
        new_id, taken_at = review.id, review.snapshot_json["taken_at"]
        assert review.snapshot_json["autobiography"]["version"] == 2
    assert "data-resend-hint" not in student.get(f"/student/targets/{ids['im']}").get_data(as_text=True)
    teacher.post(f"/teacher/package-reviews/{new_id}", data={"decision": "confirmed", "taken_at": taken_at})
    with app.app_context():
        assert db.session.get(PackageReview, new_id).status == "confirmed"
    teacher.post(f"/teacher/package-reviews/{new_id}/withdraw", data={"reason": "按錯了（測試）"})
    with app.app_context():
        assert db.session.get(PackageReview, new_id).status == "pending"


def test_unchanged_autobiography_can_still_be_confirmed(setup):
    app, ids = setup
    student, teacher = client_for(app, "stu"), client_for(app, "teacher")
    student.post(f"/student/targets/{ids['im']}/review")
    assert "data-autobiography-changed" not in teacher.get(f"/teacher/students/{ids['stu']}").get_data(as_text=True)
    with app.app_context():
        review = PackageReview.query.one()
        review_id, taken_at = review.id, review.snapshot_json["taken_at"]
    teacher.post(f"/teacher/package-reviews/{review_id}", data={"decision": "confirmed", "taken_at": taken_at})
    with app.app_context():
        assert db.session.get(PackageReview, review_id).status == "confirmed"


# ---------- 2. 自傳段落註解 ----------

def test_multiple_comments_replies_and_resolve_flow(setup):
    app, ids = setup
    student, teacher = client_for(app, "stu"), client_for(app, "teacher")
    url = f"/teacher/students/{ids['stu']}/autobiography/{ids['output']}/comments"
    for text in ("第一則：多寫你負責的部分", "第二則：可以補一個例子"):
        response = teacher.post(url, data={"paragraph": 0, "text": text})
        assert response.status_code == 302 and "#paragraph-0" in response.location
    with app.app_context():
        comments = AutobiographyComment.query.order_by(AutobiographyComment.id).all()
        assert [c.paragraph for c in comments] == [0, 0]
        first_id = comments[0].id
        notes = Notification.query.filter_by(recipient_id=ids["stu"]).all()
        assert len(notes) == 2 and all(f"program_id={ids['im']}" in n.link and "#paragraph-0" in n.link for n in notes)
        assert "學習動機" in notes[0].message

    page = student.get(f"/student/autobiography?program_id={ids['im']}").get_data(as_text=True)
    assert "第一則：多寫你負責的部分" in page and "第二則：可以補一個例子" in page
    assert "2 則，2 則待處理" in page and 'form="cform-' in page

    reply = student.post(f"/student/autobiography-comments/{first_id}/reply", data={"text": "好的，我補上（測試）"})
    assert reply.status_code == 302
    with app.app_context():
        note = Notification.query.filter_by(recipient_id=ids["teacher"]).one()
        assert "回覆了你在自傳留下的註解" in note.message
        assert note.link.startswith(f"/teacher/students/{ids['stu']}/autobiography/program/{ids['im']}")
        teacher_link = note.link
    opened = teacher.get(teacher_link)
    assert opened.status_code == 302 and "/edit" in opened.location
    assert "好的，我補上（測試）" in teacher.get(opened.location).get_data(as_text=True)

    student.post(f"/student/autobiography-comments/{first_id}/resolve")
    with app.app_context():
        comment = db.session.get(AutobiographyComment, first_id)
        assert comment.resolved_at is not None and comment.resolved_by_id == ids["stu"]
    teacher.post(f"/teacher/autobiography-comments/{first_id}/reopen")
    teacher.post(f"/teacher/autobiography-comments/{first_id}/reply", data={"text": "老師再補一句（測試）"})
    with app.app_context():
        comment = db.session.get(AutobiographyComment, first_id)
        assert comment.resolved_at is None
        assert AutobiographyComment.query.filter_by(parent_id=first_id).count() == 2
        actions = {log.action for log in AuditLog.query.all()}
        assert {"autobiography.comment", "autobiography.comment_reply", "autobiography.comment_resolve",
                "autobiography.comment_reopen"} <= actions
        # 操作紀錄不放註解原文
        assert not any("多寫你負責" in str(log.detail_json) for log in AuditLog.query.all())


def test_comment_permissions_and_validation(setup):
    app, ids = setup
    teacher = client_for(app, "teacher")
    url = f"/teacher/students/{ids['stu']}/autobiography/{ids['output']}/comments"
    assert client_for(app, "other").post(url, data={"paragraph": 0, "text": "別班"}).status_code == 403
    assert teacher.post(url, data={"paragraph": 0, "text": "  "}).status_code == 400
    assert teacher.post(url, data={"paragraph": 9, "text": "沒有這段"}).status_code == 400
    assert teacher.post(url, data={"paragraph": 0, "text": "字" * 2001}).status_code == 400
    teacher.post(url, data={"paragraph": 1, "text": "正常註解"})
    with app.app_context():
        comment_id = AutobiographyComment.query.one().id
    assert client_for(app, "stu2").post(f"/student/autobiography-comments/{comment_id}/reply",
                                        data={"text": "不是我的"}).status_code == 403
    assert client_for(app, "other").post(f"/teacher/autobiography-comments/{comment_id}/resolve").status_code == 403
    # 不提供刪除
    assert teacher.post(f"/teacher/autobiography-comments/{comment_id}/delete").status_code == 404
    assert client_for(app, "stu").post(f"/student/autobiography-comments/{comment_id}/delete").status_code == 404
    with app.app_context():
        assert AutobiographyComment.query.count() == 1


def test_old_version_comments_are_kept_with_original_text(setup):
    app, ids = setup
    student, teacher = client_for(app, "stu"), client_for(app, "teacher")
    teacher.post(f"/teacher/students/{ids['stu']}/autobiography/{ids['output']}/comments",
                 data={"paragraph": 0, "text": "第一版的意見"})
    new_id = student_saves(app, ids, student, ["改寫後的第一段（測試資料）", PARAGRAPHS[1]["text"]])
    assert new_id != ids["output"]
    edit = teacher.get(f"/teacher/students/{ids['stu']}/autobiography/{new_id}/edit").get_data(as_text=True)
    assert "第一版的意見" in edit and "寫於第 1 版" in edit
    assert "留註解時這一段是" in edit and PARAGRAPHS[0]["text"] in edit
    page = student.get(f"/student/autobiography?program_id={ids['im']}").get_data(as_text=True)
    assert "第一版的意見" in page and "寫於第 1 版" in page


# ---------- 3. 教師編輯頁 ----------

def test_edit_page_has_comments_under_paragraphs_and_no_old_comment_field(setup):
    app, ids = setup
    teacher = client_for(app, "teacher")
    html = teacher.get(f"/teacher/students/{ids['stu']}/autobiography/{ids['output']}/edit").get_data(as_text=True)
    assert "給學生的意見" not in html and 'name="comment_0"' not in html
    assert 'id="paragraph-0"' in html and 'form="cform-new-0"' in html and 'id="cform-new-1"' in html
    assert "data-draft-form" in html and "autobiography-comments.js" in html
    # 表單不能巢狀：註解表單都在儲存表單後面
    assert html.index('id="cform-new-0"') > html.index("儲存成新的一版")


def test_teacher_save_keeps_old_comment_and_notifies_student(setup):
    app, ids = setup
    with app.app_context():
        output = db.session.get(LearningProfileOutput, ids["output"])
        content = dict(output.content_json)
        content["paragraphs"] = [dict(PARAGRAPHS[0], teacher_comment="舊的段落意見"), PARAGRAPHS[1]]
        output.content_json = content
        db.session.commit()
    teacher = client_for(app, "teacher")
    response = teacher.post(f"/teacher/students/{ids['stu']}/autobiography/{ids['output']}/edit",
                            data={"paragraph_0": "導師改過的第一段", "paragraph_1": PARAGRAPHS[1]["text"]})
    assert response.status_code == 302
    with app.app_context():
        latest = LearningProfileOutput.query.order_by(LearningProfileOutput.id.desc()).first()
        assert latest.content_json["paragraphs"][0]["teacher_comment"] == "舊的段落意見"
        assert latest.content_json["editor_role"] == "teacher"
        note = Notification.query.filter_by(recipient_id=ids["stu"]).one()
        assert f"v={latest.id}" in note.link and "修改了你的自傳" in note.message


def test_teacher_can_see_version_history_only_for_own_class(setup):
    app, ids = setup
    student = client_for(app, "stu")
    student_saves(app, ids, student, ["學生修改後的新內容（測試）", PARAGRAPHS[1]["text"]])
    url = f"/teacher/students/{ids['stu']}/autobiography/versions/{ids['im']}"
    html = client_for(app, "teacher").get(url).get_data(as_text=True)
    assert "學生修改後的新內容" in html and "<ins>" in html and "返回學生資料" in html
    assert client_for(app, "other").get(url).status_code == 403
    assert student.get(url).status_code == 403


# ---------- 4. 備審準備提醒 ----------

def test_teacher_reminder_prefilled_editable_and_links_to_target(setup):
    app, ids = setup
    teacher, student = client_for(app, "teacher"), client_for(app, "stu")
    html = teacher.get(f"/teacher/students/{ids['stu']}").get_data(as_text=True)
    assert "提醒學生準備這個校系" in html and "建議優先準備：" in html and "證照" in html

    url = f"/teacher/students/{ids['stu']}/targets/{ids['im']}/remind"
    response = teacher.post(url, data={"message": "下週前請補證照影本（測試）"})
    assert response.status_code == 302 and f"reminded={ids['im']}" in response.location
    assert "提醒已送出" in teacher.get(response.location).get_data(as_text=True)
    with app.app_context():
        note = Notification.query.filter_by(recipient_id=ids["stu"]).one()
        assert note.message == "測試導師老師提醒：下週前請補證照影本（測試）"
        assert note.link == f"/student/targets/{ids['im']}"
        note_id = note.id
        assert AuditLog.query.filter_by(action="target.teacher_reminder").count() == 1
    opened = student.get(f"/notifications/{note_id}/open", follow_redirects=True)
    assert opened.status_code == 200

    assert teacher.post(url, data={"message": ""}).status_code == 400
    assert teacher.post(url, data={"message": "字" * 181}).status_code == 400
    assert client_for(app, "other").post(url, data={"message": "別班"}).status_code == 403
    assert teacher.post(f"/teacher/students/{ids['stu2']}/targets/{ids['cs']}/remind",
                        data={"message": "沒選這個校系"}).status_code == 404


# ---------- 5. 班級進度與目標統計 ----------

def test_dashboard_shows_readiness_and_school_counts_once_per_student(setup):
    app, ids = setup
    html = client_for(app, "teacher").get("/teacher/dashboard").get_data(as_text=True)
    assert "data-target-progress" in html and "待補：證照、競賽" in html.replace("證照與", "")\
        or "待補：" in html
    assert "不是錄取機率" in html and "不等於報名" in html
    assert "data-target-statistics" in html
    section = html[html.index("data-target-statistics"):]
    # 測試科技大學：學生甲選兩個科系，學生乙選一個 → 學校 2 人，不是 3 人
    row = section[section.index("測試科技大學"):section.index("</tr>", section.index("測試科技大學"))]
    assert "2 人" in row and "資訊管理系（2）" in row and "資訊工程系（1）" in row
    row = section[section.index("示範大學"):section.index("</tr>", section.index("示範大學"))]
    assert "1 人" in row
    # 別班學生不列入
    assert "測試學生丙" not in html

"""二技公告（UC-25）：管理員發布 → 學生、導師、科辦收到未讀 → 導師提醒四、五年級學生 → 科辦看寄送備審截止。

截止日一律由招生資料 Agent 核准的日程帶出（11-09 使用者：不要人工輸入）。全部用合成假資料。
"""
from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.models import Announcement


# ---- Task 1：資料表 ----

def test_migration_creates_announcement_tables(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'm.db'}", "TESTING": True})
    runner = app.test_cli_runner()
    assert runner.invoke(args=["db", "upgrade"]).exit_code == 0
    with app.app_context():
        inspector = inspect(db.engine)
        assert {"announcements", "announcement_reads"} <= set(inspector.get_table_names())
        uniques = {item["name"] for item in inspector.get_unique_constraints("announcement_reads")}
        assert "uq_announcement_read" in uniques


def test_audience_roles_parses_csv():
    assert Announcement(audience="student,staff").audience_roles == {"student", "staff"}


# ---- 共用合成資料 ----
from datetime import date, datetime  # noqa: E402

import pytest  # noqa: E402

from app.models import (AdmissionScheduleEvent, AnnouncementRead, AuditLog, AwardCertificate, ClassAdvisor,  # noqa: E402
                        Notification, StudentProfile, User)
from app.services import announcement_service as svc  # noqa: E402

TODAY = date(2026, 11, 10)  # 115 學年度：111 入學 = 五年級、112 = 四年級、113 = 三年級
SEND_REVIEW = "向甄審校院繳費並寄送備審資料"


def _app(tmp_path, *, send_review=True, send_review_end=True):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        users = {}
        for username, name, role in [("admin", "系統管理員", "admin"), ("s5", "王五年", "student"),
                                     ("s4", "李四年", "student"), ("s3", "張三年", "student"),
                                     ("x5", "別班五年", "student"), ("t1", "陳導師", "teacher"),
                                     ("t0", "沒帶班老師", "teacher"), ("staff", "林科助", "staff")]:
            user = User(username=username, display_name=name, role=role)
            user.set_password("pw")
            db.session.add(user)
            users[username] = user
        db.session.flush()
        for username, no, class_name, year in [("s5", "111534901", "資管科五甲", 111), ("s4", "112534902", "資管科四甲", 112),
                                               ("s3", "113534903", "資管科三甲", 113), ("x5", "111534904", "資管科五乙", 111)]:
            db.session.add(StudentProfile(user_id=users[username].id, student_no=no, class_name=class_name,
                                          admission_year=year))
        for class_name in ("資管科五甲", "資管科四甲", "資管科三甲"):
            db.session.add(ClassAdvisor(teacher_id=users["t1"].id, class_name=class_name, school_year=115))
        rows = [("簡章網路下載", datetime(2026, 11, 20), None),
                ("報名資格審查：上網登錄並寄出審查資料", datetime(2027, 4, 9, 10), datetime(2027, 4, 13, 17))]
        if send_review:
            rows.append((SEND_REVIEW, datetime(2027, 4, 20), datetime(2027, 4, 24, 23, 59) if send_review_end else None))
        for name, start, end in rows:
            db.session.add(AdmissionScheduleEvent(channel="skill_review", admission_year=116, name=name, start_at=start,
                                                  end_at=end, status="published", data_origin="agent",
                                                  source_url="https://example.test/116enterdate.pdf"))
        db.session.commit()
    return app


def _user(username):
    return User.query.filter_by(username=username).one()


def _published(app):
    """建立並發布一則 116 學年度二技公告，回傳 id。"""
    with app.app_context():
        announcement = svc.draft_from_schedule("skill_review", 116, _user("admin"))
        svc.publish(announcement, _user("admin"))
        return announcement.id


# ---- Task 2：服務 ----

def test_draft_from_schedule_prefills_dates(tmp_path):
    app = _app(tmp_path)
    with app.app_context():
        draft = svc.draft_from_schedule("skill_review", 116, _user("admin"))
        assert "116 學年度二技技優甄審" in draft.title
        assert "寄送備審" in draft.body and "4/20–4/24" in draft.body
        assert draft.status == "draft"
        svc.draft_from_schedule("skill_review", 116, _user("admin"))
        assert Announcement.query.filter_by(status="draft").count() == 1


def test_publish_notifies_audience_and_logs(tmp_path):
    app = _app(tmp_path)
    with app.app_context():
        draft = svc.draft_from_schedule("skill_review", 116, _user("admin"))
        sent = svc.publish(draft, _user("admin"))
        assert sent == 7  # 4 位學生＋2 位老師＋1 位科辦
        assert Notification.query.filter_by(recipient_id=_user("admin").id).count() == 0
        assert Notification.query.filter_by(recipient_id=_user("s5").id).one().link == f"/announcements/{draft.id}"
        assert AuditLog.query.filter_by(action="announcement.publish").count() == 1


def test_publish_twice_does_not_duplicate_notifications(tmp_path):
    app = _app(tmp_path)
    announcement_id = _published(app)
    with app.app_context():
        with pytest.raises(ValueError):
            svc.publish(db.session.get(Announcement, announcement_id), _user("admin"))
        assert Notification.query.count() == 7


def test_visible_and_unread_flow(tmp_path):
    app = _app(tmp_path)
    announcement_id = _published(app)
    with app.app_context():
        student = _user("s5")
        announcement = db.session.get(Announcement, announcement_id)
        assert svc.visible_for(student) == [announcement]
        assert svc.unread_ids(student, [announcement]) == {announcement_id}
        svc.mark_read(announcement, student)
        svc.mark_read(announcement, student)  # 重複打開不出錯
        assert svc.unread_ids(student, [announcement]) == set()
        assert AnnouncementRead.query.count() == 1
        assert Notification.query.filter_by(recipient_id=student.id).one().read_at is not None
        assert svc.visible_for(_user("admin")) == []


def test_withdraw_hides_and_logs(tmp_path):
    app = _app(tmp_path)
    announcement_id = _published(app)
    with app.app_context():
        svc.withdraw(db.session.get(Announcement, announcement_id), _user("admin"))
        announcement = db.session.get(Announcement, announcement_id)
        assert announcement.status == "withdrawn" and announcement.withdrawn_by == _user("admin").id
        assert svc.visible_for(_user("s5")) == []
        assert AuditLog.query.filter_by(action="announcement.withdraw").count() == 1


def test_send_review_deadline_label(tmp_path):
    app = _app(tmp_path)
    _published(app)
    with app.app_context():
        deadline = svc.send_review_deadline(TODAY)
        assert deadline["label"] == "4/24"
        assert deadline["deadline"] == datetime(2027, 4, 24, 23, 59)
        assert svc.send_review_deadline(date(2027, 4, 25)) is None


def test_deadline_says_not_stated_when_missing(tmp_path):
    app = _app(tmp_path, send_review=False)
    _published(app)
    with app.app_context():
        deadline = svc.send_review_deadline(TODAY)
        assert deadline["label"] == "簡章未載明"
        assert deadline["deadline"] is None


def test_deadline_uses_start_when_no_end(tmp_path):
    app = _app(tmp_path, send_review_end=False)
    _published(app)
    with app.app_context():
        assert svc.send_review_deadline(TODAY)["label"] == "4/20"


def test_deadline_ignores_manual_announcement(tmp_path):
    app = _app(tmp_path)
    with app.app_context():
        manual = svc.create_manual("科上說明會", "週三中午在 E301", {"student"}, _user("admin"))
        svc.publish(manual, _user("admin"))
        assert svc.send_review_deadline(TODAY) is None
        assert svc.key_dates(manual) == []


def test_teacher_targets_only_grade_4_and_5(tmp_path):
    app = _app(tmp_path)
    with app.app_context():
        rows = svc.teacher_targets(_user("t1"), TODAY)
        assert {row["student"].username for row in rows} == {"s5", "s4"}
        assert {row["grade"] for row in rows} == {4, 5}
        assert all(row["target_count"] == 0 for row in rows)
        assert svc.teacher_targets(_user("t0"), TODAY) == []


def test_remind_students_notifies_and_logs(tmp_path):
    app = _app(tmp_path)
    announcement_id = _published(app)
    with app.app_context():
        announcement = db.session.get(Announcement, announcement_id)
        assert svc.remind_students(announcement, _user("t1"), TODAY) == 2
        for username in ("s5", "s4"):
            assert any("陳導師老師提醒你" in note.message
                       for note in Notification.query.filter_by(recipient_id=_user(username).id))
        assert not any("提醒你" in note.message for note in Notification.query.filter_by(recipient_id=_user("s3").id))
        log = AuditLog.query.filter_by(action="announcement.remind").one()
        assert sorted(log.detail_json["student_ids"]) == sorted([_user("s5").id, _user("s4").id])
        with pytest.raises(ValueError):
            svc.remind_students(announcement, _user("t0"), TODAY)


# ---- Task 3：學生、導師、科辦的公告清單與內容頁 ----

def _client(app, username):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def test_index_shows_unread_badge(tmp_path):
    app = _app(tmp_path)
    announcement_id = _published(app)
    for username in ("s5", "t1", "staff"):
        client = _client(app, username)
        page = client.get("/announcements").get_data(as_text=True)
        assert "116 學年度二技技優甄審招生日程公告" in page
        assert "data-unread" in page and "未讀" in page
        assert client.get(f"/announcements/{announcement_id}").status_code == 200
        assert "data-unread" not in client.get("/announcements").get_data(as_text=True)


def test_detail_highlights_send_review(tmp_path):
    app = _app(tmp_path)
    announcement_id = _published(app)
    page = _client(app, "s5").get(f"/announcements/{announcement_id}").get_data(as_text=True)
    assert "data-send-review" in page and "4/20–4/24" in page


def test_student_cannot_open_draft_or_withdrawn(tmp_path):
    app = _app(tmp_path)
    announcement_id = _published(app)
    with app.app_context():
        draft = svc.create_manual("草稿公告", "內容", {"student"}, _user("admin"))
        draft_id = draft.id
    client = _client(app, "s5")
    assert client.get(f"/announcements/{draft_id}").status_code == 404
    with app.app_context():
        svc.withdraw(db.session.get(Announcement, announcement_id), _user("admin"))
    assert client.get(f"/announcements/{announcement_id}").status_code == 404
    assert client.get("/announcements/99999").status_code == 404


def test_admin_cannot_open_reader_pages(tmp_path):
    app = _app(tmp_path)
    assert _client(app, "admin").get("/announcements").status_code != 200


# ---- Task 4：導師一鍵提醒 ----

def test_teacher_sees_own_grade_4_5_students(tmp_path):
    app = _app(tmp_path)
    announcement_id = _published(app)
    page = _client(app, "t1").get(f"/announcements/{announcement_id}").get_data(as_text=True)
    assert "王五年" in page and "李四年" in page
    assert "張三年" not in page and "別班五年" not in page
    assert "提醒這些學生" in page


def test_teacher_remind_creates_notifications(tmp_path):
    app = _app(tmp_path)
    announcement_id = _published(app)
    response = _client(app, "t1").post(f"/announcements/{announcement_id}/remind")
    assert response.status_code == 302
    page = _client(app, "s5").get("/notifications").get_data(as_text=True)
    assert "陳導師老師提醒你看二技公告" in page


def test_teacher_without_class_cannot_remind(tmp_path):
    app = _app(tmp_path)
    announcement_id = _published(app)
    client = _client(app, "t0")
    page = client.get(f"/announcements/{announcement_id}").get_data(as_text=True)
    assert "目前沒有您帶的四、五年級學生" in page
    assert "提醒這些學生" not in page
    with app.app_context():
        before = Notification.query.count()
    assert client.post(f"/announcements/{announcement_id}/remind").status_code == 400
    with app.app_context():
        assert Notification.query.count() == before


def test_student_cannot_remind(tmp_path):
    app = _app(tmp_path)
    announcement_id = _published(app)
    with app.app_context():
        before = Notification.query.count()
    response = _client(app, "s5").post(f"/announcements/{announcement_id}/remind")
    assert response.status_code in (302, 403, 404) and "/announcements" not in response.headers.get("Location", "")
    with app.app_context():
        assert Notification.query.count() == before


# ---- Task 5：管理員擬稿、發布、下架、手動新增 ----

def _candidate_schedule(app, year=117):
    with app.app_context():
        for name, start, end in [("網路報名", datetime(2028, 4, 20, 10), datetime(2028, 4, 23, 17)),
                                 (SEND_REVIEW, datetime(2028, 4, 20), datetime(2028, 4, 24, 23, 59))]:
            db.session.add(AdmissionScheduleEvent(channel="skill_review", admission_year=year, name=name, start_at=start,
                                                  end_at=end, status="candidate", data_origin="agent"))
        db.session.commit()


def test_approving_schedule_opens_prefilled_draft(tmp_path):
    app = _app(tmp_path)
    _candidate_schedule(app)
    client = _client(app, "admin")
    response = client.post("/admin/agent/schedule/skill_review/117/approve")
    assert response.status_code == 302
    with app.app_context():
        draft = Announcement.query.filter_by(admission_year=117, status="draft").one()
    from urllib.parse import urlparse
    assert urlparse(response.headers["Location"]).path == f"/admin/announcements/{draft.id}/edit"
    page = client.get(f"/admin/announcements/{draft.id}/edit").get_data(as_text=True)
    assert "寄送備審" in page and "117 學年度二技技優甄審招生日程公告" in page


def test_admin_edits_and_publishes(tmp_path):
    app = _app(tmp_path)
    with app.app_context():
        draft_id = svc.draft_from_schedule("skill_review", 116, _user("admin")).id
    client = _client(app, "admin")
    response = client.post(f"/admin/announcements/{draft_id}/edit",
                           data={"title": "116 二技技優甄審簡章已公告", "body": "請五年級同學準備備審資料",
                                 "audience": ["student", "teacher", "staff"], "action": "publish"})
    assert response.status_code == 302
    with app.app_context():
        announcement = db.session.get(Announcement, draft_id)
        assert announcement.status == "published" and announcement.title == "116 二技技優甄審簡章已公告"
    assert "116 二技技優甄審簡章已公告" in _client(app, "s5").get("/announcements").get_data(as_text=True)


def test_admin_saves_draft_without_publishing(tmp_path):
    app = _app(tmp_path)
    with app.app_context():
        draft_id = svc.draft_from_schedule("skill_review", 116, _user("admin")).id
    _client(app, "admin").post(f"/admin/announcements/{draft_id}/edit",
                               data={"title": "改過的標題", "body": "內容", "audience": ["student"], "action": "save"})
    with app.app_context():
        announcement = db.session.get(Announcement, draft_id)
        assert announcement.status == "draft" and announcement.title == "改過的標題"
        assert announcement.audience_roles == {"student"}
        assert Notification.query.count() == 0


def test_edit_form_has_no_date_inputs(tmp_path):
    app = _app(tmp_path)
    with app.app_context():
        draft_id = svc.draft_from_schedule("skill_review", 116, _user("admin")).id
    client = _client(app, "admin")
    for url in (f"/admin/announcements/{draft_id}/edit", "/admin/announcements/new"):
        page = client.get(url).get_data(as_text=True)
        assert 'type="date"' not in page and 'type="datetime-local"' not in page


def test_admin_creates_manual_announcement(tmp_path):
    app = _app(tmp_path)
    response = _client(app, "admin").post("/admin/announcements/new",
                                          data={"title": "二技說明會", "body": "週三中午 E301", "audience": ["student"]})
    assert response.status_code == 302
    with app.app_context():
        announcement = Announcement.query.filter_by(title="二技說明會").one()
        assert announcement.status == "draft" and announcement.channel is None


def test_admin_withdraw_and_no_delete(tmp_path):
    app = _app(tmp_path)
    announcement_id = _published(app)
    client = _client(app, "admin")
    page = client.get("/admin/announcements").get_data(as_text=True)
    assert "下架</button>" in page
    assert "刪除</button>" not in page and "/delete" not in page
    assert client.post(f"/admin/announcements/{announcement_id}/withdraw").status_code == 302
    with app.app_context():
        assert db.session.get(Announcement, announcement_id).status == "withdrawn"
    assert "已下架" in client.get("/admin/announcements").get_data(as_text=True)


def test_non_admin_cannot_manage(tmp_path):
    app = _app(tmp_path)
    for username in ("s5", "staff", "t1"):
        assert _client(app, username).get("/admin/announcements").status_code != 200


# ---- Task 6：首頁最新公告與科辦寄送備審截止卡 ----

def _pending_certificate(app):
    from app.models import Portfolio
    with app.app_context():
        record = Portfolio(student_id=_user("s5").id, title="資訊週志工", category="service")
        db.session.add(record)
        db.session.flush()
        db.session.add(AwardCertificate(portfolio_id=record.id, status="pending",
                                        title="服務證明", body="合成內文", issuer="資管科"))
        db.session.commit()


def _freeze_today(monkeypatch, day):
    monkeypatch.setattr(svc, "_today", lambda: day)


def test_staff_home_shows_deadline_card(tmp_path, monkeypatch):
    _freeze_today(monkeypatch, TODAY)
    app = _app(tmp_path)
    _pending_certificate(app)
    _published(app)
    page = _client(app, "staff").get("/staff/dashboard").get_data(as_text=True)
    assert "data-admission-deadline" in page
    assert "二技截止前未核准的電子獎狀" in page and "寄送備審 4/24 截止" in page
    import re
    card = re.search(r"<a[^>]*data-admission-deadline[^>]*>", page).group(0)
    assert 'href="/staff/certificates"' in card


def test_staff_home_card_hidden_after_deadline(tmp_path, monkeypatch):
    _freeze_today(monkeypatch, date(2027, 4, 25))
    app = _app(tmp_path)
    _published(app)
    assert "data-admission-deadline" not in _client(app, "staff").get("/staff/dashboard").get_data(as_text=True)


def test_staff_home_card_hidden_without_announcement(tmp_path, monkeypatch):
    _freeze_today(monkeypatch, TODAY)
    app = _app(tmp_path)
    assert "data-admission-deadline" not in _client(app, "staff").get("/staff/dashboard").get_data(as_text=True)


def test_staff_home_not_stated(tmp_path, monkeypatch):
    _freeze_today(monkeypatch, TODAY)
    app = _app(tmp_path, send_review=False)
    _published(app)
    page = _client(app, "staff").get("/staff/dashboard").get_data(as_text=True)
    assert "data-admission-deadline" in page and "截止日：簡章未載明" in page


def test_homes_show_latest_announcement(tmp_path):
    app = _app(tmp_path)
    _published(app)
    for username, url in (("s5", "/dashboard/student"), ("t1", "/dashboard/teacher"), ("staff", "/dashboard/staff")):
        client = _client(app, username)
        response = client.get(url, follow_redirects=True)
        page = response.get_data(as_text=True)
        assert "data-latest-announcement" in page, username
        assert "116 學年度二技技優甄審招生日程公告" in page and "未讀" in page


# ---- 11-10 小修 ----

def test_approve_redirect_keeps_approved_message(tmp_path):
    app = _app(tmp_path)
    _candidate_schedule(app)
    page = _client(app, "admin").post("/admin/agent/schedule/skill_review/117/approve",
                                      follow_redirects=True).get_data(as_text=True)
    assert "117 學年度：已核准，招生時程頁改用這一組日程（2 項）" in page
    assert "公告草稿已擬好" in page


def test_staff_home_reads_announcements_once(tmp_path, monkeypatch):
    app = _app(tmp_path)
    _published(app)
    calls = []
    original = svc.send_review_deadline
    monkeypatch.setattr(svc, "send_review_deadline", lambda today=None: calls.append(1) or original(today))
    page = _client(app, "staff").get("/staff/dashboard").get_data(as_text=True)
    assert "data-admission-deadline" in page and "data-latest-announcement" in page
    assert len(calls) == 1


def test_notifications_page_mentions_admission_notices(tmp_path):
    app = _app(tmp_path)
    page = _client(app, "s5").get("/notifications").get_data(as_text=True)
    assert "畢業缺口案件、電子獎狀與二技公告" in page

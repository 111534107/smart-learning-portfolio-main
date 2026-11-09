"""電子獎狀補完：TA 證明類別、核准／退回寄站內通知、審核頁直接對照獎懲原文與原始檔。

2026-11-09 起科學會證明不由科辦開（訪談：科學會歸類在社團，證明由學務處辦），改成提醒學生到學務處。

全部用合成假資料。
"""
from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.models import (AwardCertificate, Notification, Portfolio, SchoolAwardRecord, SourceDocument, User)
from app.services import certificate_service
from tests.test_award_certificates import cert_app, client_for

PNG_BYTES = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
             b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")


def _add_award_record(app, reason, category, *, title=None, with_file=False, tmp_path=None):
    """模擬學生從獎懲記錄匯入一列：經歷＋逐列原文（＋原始檔）。回傳經歷 id。"""
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        document = None
        if with_file:
            path = tmp_path / "award-record.png"
            path.write_bytes(PNG_BYTES)
            document = SourceDocument(owner_id=student.id, document_type="award_record", display_name="獎懲記錄.png",
                                      file_path=str(path), sha256="0" * 64, status="confirmed")
            db.session.add(document)
            db.session.flush()
        record = Portfolio(student_id=student.id, title=title or reason, category=category, school_year=114, semester=1,
                           description="2025/12/30 嘉獎1次", source="award_record", status="confirmed",
                           source_document_id=document.id if document else None)
        db.session.add(record)
        db.session.flush()
        db.session.add(SchoolAwardRecord(student_id=student.id, portfolio_id=record.id, record_key=f"k{record.id}",
                                         record_type="reward", date="2025/12/30", name="嘉獎", count=1, reason=reason,
                                         source_document_id=document.id if document else None))
        db.session.commit()
        return record.id


def _cert(app):
    with app.app_context():
        return AwardCertificate.query.one()


# ---- 類別 ----

def test_eligible_kinds_follow_award_reason(tmp_path):
    app = cert_app(tmp_path)
    ta_id = _add_award_record(app, "1141學期擔任資料庫系統課程TA認真負責", "activity")
    club_id = _add_award_record(app, "1141學期擔任資訊研習社社長熱心社務", "leadership")
    data_id = _add_award_record(app, "1141學期參加DATA分析工作坊", "activity")
    with app.app_context():
        kinds = {pid: certificate_service.eligible_kinds(db.session.get(Portfolio, pid))
                 for pid in (ta_id, club_id, data_id)}
        service_record = next(p for p in Portfolio.query.all() if "麗山" in p.title)
        # 麗山國中社團：科上派的服務；提到社團也不再能申請社團證明（11-09 改由學務處辦）
        assert certificate_service.eligible_kinds(service_record) == ["service"]
        manual = next(p for p in Portfolio.query.all() if p.title == "資訊週志工")
        assert certificate_service.eligible_kinds(manual) == []
    assert kinds[ta_id] == ["ta"]
    assert kinds[club_id] == []
    assert kinds[data_id] == []  # 「DATA」裡的 ta 不算


def test_student_applies_for_ta_certificate(tmp_path):
    app = cert_app(tmp_path)
    ta_id = _add_award_record(app, "1141學期擔任資料庫系統課程TA認真負責", "activity")

    response = client_for(app, "stu").post(f"/student/portfolio/{ta_id}/certificate", data={"kind": "ta"})

    assert response.status_code == 302
    cert = _cert(app)
    assert cert.kind == "ta" and cert.title == "TA 證明"
    # 11-09 科長訪談：TA 證明寫誰、哪一學期、協助哪一門課，不寫時數
    assert "於 114 學年度第一學期擔任「資料庫系統」課程 TA（教學助理）" in cert.body
    assert "協助課程教學" in cert.body and "小時" not in cert.body


def test_ta_body_names_the_course_for_common_wordings(tmp_path):
    from app.services.certificate_service import ta_course
    assert ta_course("1141學期擔任資料庫系統課程TA認真負責") == "資料庫系統"
    assert ta_course("1141學期擔任程式設計課程助教") == "程式設計"
    assert ta_course("1132學期擔任網頁設計證照輔導班教學助理") == "網頁設計證照輔導班"
    assert ta_course("擔任「軟體設計」TA") == "軟體設計"
    assert ta_course("1141學期協助TA工作") is None  # 看不出課名


def test_ta_body_without_course_keeps_original_reason(tmp_path):
    app = cert_app(tmp_path)
    ta_id = _add_award_record(app, "1141學期協助TA工作熱心", "activity")
    client_for(app, "stu").post(f"/student/portfolio/{ta_id}/certificate", data={"kind": "ta"})
    body = _cert(app).body
    assert "協助TA工作熱心" in body and "協助課程教學" in body and "小時" not in body


def test_kind_defaults_to_first_eligible_and_rejects_others(tmp_path):
    app = cert_app(tmp_path)
    ta_id = _add_award_record(app, "1141學期擔任程式設計課程助教", "activity")
    student = client_for(app, "stu")

    wrong = student.post(f"/student/portfolio/{ta_id}/certificate", data={"kind": "club"})
    default = student.post(f"/student/portfolio/{ta_id}/certificate")

    assert wrong.status_code == 400
    assert default.status_code == 302
    assert _cert(app).kind == "ta"


def test_edited_title_does_not_unlock_kind(tmp_path):
    """可申請的類別看匯入時的獎懲原文，學生改經歷標題加上「TA」也沒用。"""
    app = cert_app(tmp_path)
    record_id = _add_award_record(app, "1141學期參加校慶運動會", "activity", title="校慶運動會 TA")

    response = client_for(app, "stu").post(f"/student/portfolio/{record_id}/certificate", data={"kind": "ta"})

    assert response.status_code == 400


def test_portfolio_page_lets_student_choose_kind(tmp_path):
    app = cert_app(tmp_path)
    with app.app_context():
        service_id = next(p.id for p in Portfolio.query.all() if "麗山" in p.title)
    ta_id = _add_award_record(app, "1141學期擔任資料庫系統課程TA認真負責", "activity")
    student = client_for(app, "stu")

    both = student.get(f"/student/portfolio/{service_id}/edit").get_data(as_text=True)
    only_ta = student.get(f"/student/portfolio/{ta_id}/edit").get_data(as_text=True)

    assert "「服務證明」" in both and 'value="club"' not in both
    assert "「TA 證明」" in only_ta and 'name="kind" value="ta"' in only_ta


def test_club_record_reminds_student_to_go_to_student_affairs(tmp_path):
    # 2026-11-09 訪談：科學會歸類在社團，證明是學務處的表格，指導老師蓋章後交回學務處蓋章，科辦不開
    app = cert_app(tmp_path)
    club_id = _add_award_record(app, "1141學期擔任資訊研習社社長熱心社務", "leadership")
    student = client_for(app, "stu")

    page = student.get(f"/student/portfolio/{club_id}/edit").get_data(as_text=True)
    applied = student.post(f"/student/portfolio/{club_id}/certificate", data={"kind": "club"})

    assert "學務處" in page and "指導老師蓋章" in page
    assert "申請電子獎狀" not in page and 'name="kind"' not in page
    assert applied.status_code == 400
    with app.app_context():
        assert AwardCertificate.query.count() == 0


def test_student_association_officer_gets_reminder_but_class_officer_does_not(tmp_path):
    app = cert_app(tmp_path)
    association_id = _add_award_record(app, "1141學期擔任資管科科學會活動長認真負責", "leadership")
    class_id = _add_award_record(app, "1141學期擔任班級幹部服務熱心", "leadership")
    student = client_for(app, "stu")

    association = student.get(f"/student/portfolio/{association_id}/edit").get_data(as_text=True)
    class_officer = student.get(f"/student/portfolio/{class_id}/edit").get_data(as_text=True)

    assert "科學會歸類在社團" in association and "學務處" in association
    assert "學務處" not in class_officer  # 訪談只講到科學會與社團，班級幹部沒有說，不亂提醒


def test_service_record_mentioning_club_shows_both_service_and_reminder(tmp_path):
    app = cert_app(tmp_path)
    with app.app_context():
        service_id = next(p.id for p in Portfolio.query.all() if "麗山" in p.title)

    page = client_for(app, "stu").get(f"/student/portfolio/{service_id}/edit").get_data(as_text=True)

    assert "申請電子獎狀" in page and "學務處" in page


def test_manual_record_without_club_words_has_no_reminder(tmp_path):
    app = cert_app(tmp_path)
    with app.app_context():
        manual_id = next(p.id for p in Portfolio.query.all() if p.title == "資訊週志工")

    page = client_for(app, "stu").get(f"/student/portfolio/{manual_id}/edit").get_data(as_text=True)

    assert "學務處" not in page


def test_staff_list_still_shows_old_club_certificates(tmp_path):
    """11-09 以前已申請的科學會證明照樣顯示、照樣能審，資料不刪。"""
    app = cert_app(tmp_path)
    club_id = _add_award_record(app, "1141學期擔任資訊研習社社長熱心社務", "leadership")
    with app.app_context():
        record = db.session.get(Portfolio, club_id)
        db.session.add(AwardCertificate(student_id=record.student_id, portfolio=record, status="pending", kind="club",
                                        title="科學會證明", issuer="資訊管理科", body="（舊申請）"))
        db.session.commit()

    html = client_for(app, "staff").get("/staff/certificates").get_data(as_text=True)

    assert "科學會證明" in html and "資訊研習社社長" in html


# ---- 通知 ----

def test_approval_notifies_student_with_certificate_link(tmp_path):
    app = cert_app(tmp_path)
    ta_id = _add_award_record(app, "1141學期擔任資料庫系統課程TA認真負責", "activity")
    student = client_for(app, "stu")
    student.post(f"/student/portfolio/{ta_id}/certificate", data={"kind": "ta"})
    cert = _cert(app)

    client_for(app, "staff").post(f"/staff/certificates/{cert.id}", data={
        "action": "approve", "title": cert.title, "issuer": cert.issuer, "body": cert.body})

    with app.app_context():
        note = Notification.query.one()
        assert note.recipient.username == "stu"
        assert note.case_id is None and note.event_id is None
        assert note.link == f"/certificates/{cert.id}"
        assert "核准" in note.message and "TA 證明" in note.message
        note_id = note.id
    page = student.get("/notifications").get_data(as_text=True)
    assert "核准" in page and f"/notifications/{note_id}/open" in page and "未讀" in page
    opened = student.get(f"/notifications/{note_id}/open")
    assert opened.status_code == 302 and opened.headers["Location"].endswith(f"/certificates/{cert.id}")
    with app.app_context():
        assert db.session.get(Notification, note_id).read_at is not None
    assert student.get(f"/certificates/{cert.id}").status_code == 200


def test_return_notifies_student_with_edit_link(tmp_path):
    app = cert_app(tmp_path)
    with app.app_context():
        record_id = next(p.id for p in Portfolio.query.all() if "麗山" in p.title)
    client_for(app, "stu").post(f"/student/portfolio/{record_id}/certificate")
    cert = _cert(app)

    client_for(app, "staff").post(f"/staff/certificates/{cert.id}", data={
        "action": "return", "return_reason": "日期和獎懲記錄對不上", "body": cert.body})

    with app.app_context():
        note = Notification.query.one()
        assert "退回" in note.message and "日期和獎懲記錄對不上" in note.message
        assert note.link == f"/student/portfolio/{record_id}/edit"


def test_return_without_reason_sends_no_notification(tmp_path):
    app = cert_app(tmp_path)
    with app.app_context():
        record_id = next(p.id for p in Portfolio.query.all() if "麗山" in p.title)
    client_for(app, "stu").post(f"/student/portfolio/{record_id}/certificate")
    cert = _cert(app)

    client_for(app, "staff").post(f"/staff/certificates/{cert.id}", data={"action": "return", "return_reason": ""})

    with app.app_context():
        assert Notification.query.count() == 0


def test_other_user_cannot_open_notification_and_links_stay_on_site(tmp_path):
    app = cert_app(tmp_path)
    with app.app_context():
        stu = User.query.filter_by(username="stu").one()
        outside = Notification(recipient_id=stu.id, message="測試外站", link="//evil.example/x")
        inside = Notification(recipient_id=stu.id, message="測試站內", link="/student/portfolio")
        db.session.add_all([outside, inside])
        db.session.commit()
        outside_id, inside_id = outside.id, inside.id

    assert client_for(app, "other").get(f"/notifications/{inside_id}/open").status_code == 404
    student = client_for(app, "stu")
    assert student.get(f"/notifications/{outside_id}/open").headers["Location"].endswith("/notifications")
    assert student.get(f"/notifications/{inside_id}/open").headers["Location"].endswith("/student/portfolio")


# ---- 審核頁對照獎懲 ----

def test_review_page_shows_award_reason_and_source_preview(tmp_path):
    app = cert_app(tmp_path)
    ta_id = _add_award_record(app, "1141學期擔任資料庫系統課程TA認真負責", "activity",
                              title="資料庫 TA", with_file=True, tmp_path=tmp_path)
    client_for(app, "stu").post(f"/student/portfolio/{ta_id}/certificate", data={"kind": "ta"})
    cert = _cert(app)
    staff = client_for(app, "staff")

    html = staff.get(f"/staff/certificates/{cert.id}").get_data(as_text=True)

    assert "1141學期擔任資料庫系統課程TA認真負責" in html
    assert "2025/12/30" in html and "嘉獎" in html
    assert "學生後來改過經歷標題" in html
    assert f'<img class="cert-source__preview" src="/staff/certificates/{cert.id}/source"' in html
    source = staff.get(f"/staff/certificates/{cert.id}/source")
    assert source.status_code == 200 and source.mimetype == "image/png"


def test_review_page_without_award_row_or_file_still_renders(tmp_path):
    app = cert_app(tmp_path)
    with app.app_context():
        record_id = next(p.id for p in Portfolio.query.all() if "麗山" in p.title)
    client_for(app, "stu").post(f"/student/portfolio/{record_id}/certificate")
    cert = _cert(app)

    html = client_for(app, "staff").get(f"/staff/certificates/{cert.id}").get_data(as_text=True)

    assert "對照學校獎懲記錄" in html and "沒有留下逐列原文" in html and "沒有原始檔" in html


# ---- 資料表遷移 ----

def test_migration_adds_kind_and_relaxes_notification_case(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'cert.db'}", "TESTING": True})
    runner = app.test_cli_runner()

    result = runner.invoke(args=["db", "upgrade"])
    assert result.exit_code == 0, result.output
    with app.app_context():
        inspector = inspect(db.engine)
        notes = {c["name"]: c["nullable"] for c in inspector.get_columns("notifications")}
        cert_columns = {c["name"] for c in inspector.get_columns("award_certificates")}
    assert notes["case_id"] and notes["event_id"] and "link" in notes
    assert "kind" in cert_columns
    assert runner.invoke(args=["db", "downgrade", "b20261105c01"]).exit_code == 0
    with app.app_context():
        notes = {c["name"]: c["nullable"] for c in inspect(db.engine).get_columns("notifications")}
    assert not notes["case_id"] and "link" not in notes

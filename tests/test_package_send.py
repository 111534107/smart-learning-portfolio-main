"""備審一鍵打包、綁定備用信箱、寄到信箱、雲端每位學生一個資料夾（使用者 2026-11-13）。

Google 與 SMTP 一律用假物件，不連線。以下姓名、學號、信箱、校系皆僅為測試資料。
"""
from datetime import date
import io
import zipfile

import pytest

from app import create_app
from app.extensions import db
from app.models import (AdmissionProgram, AdmissionRequirementItem, AuditLog, CredentialRecord, LearningCourseRecord,
                        Portfolio, PortfolioEvidence, SourceDocument, StudentProfile, StudentTarget, User)
from app.services import autobiography_service, backup_email, email_notify, package_zip, storage_service
from app.services.journey_service import academic_year_of
from tests.test_storage_service import FakeDriveClient, drive_app


class FolderDriveClient(FakeDriveClient):
    """假的雲端硬碟，另外記下子資料夾。"""

    def __init__(self):
        super().__init__()
        self.children = {}

    def ensure_child_folder(self, access_token, parent_id, name, app_properties):
        key = (parent_id, tuple(sorted(app_properties.items())))
        self.calls.append(("ensure_child_folder", parent_id, name))
        if key not in self.children:
            self.children[key] = {"id": f"sub{len(self.children) + 1}", "name": name, "parent": parent_id}
        return self.children[key]["id"]


def _seed(app):
    with app.app_context():
        db.create_all()
        for username, email in (("stu", "stu@school.example.test"), ("other", None)):
            user = User(username=username, display_name=f"測試生{username}", role="student", email=email)
            user.set_password("pw-123456789")
            db.session.add(user)
        db.session.flush()
        stu = User.query.filter_by(username="stu").one()
        db.session.add(StudentProfile(user_id=stu.id, student_no="T-0000009", class_name="資管科五甲",
                                      admission_year=academic_year_of(date.today()) - 4))
        program = AdmissionProgram(program_code="Z", admission_year=116, school_name="測試科大Z",
                                   department_name="資訊管理系", status="published")
        for order, (name, weight, keys) in enumerate([("證照", 50, "credential"), ("競賽成果", 50, "competition")]):
            program.items.append(AdmissionRequirementItem(source_item_name=name, weight_percent=weight,
                                                          mapped_categories=keys, mapping_status="confirmed",
                                                          sort_order=order))
        db.session.add(program)
        db.session.flush()
        db.session.add(StudentTarget(student_id=stu.id, rule_version_id=program.id))

        def document(kind, name, data):
            location = storage_service.save(data, owner_id=stu.id, folder="learning-profile", filename=name)
            row = SourceDocument(owner_id=stu.id, document_type=kind, display_name=name, file_path=location,
                                 sha256="0" * 64, status="confirmed")
            db.session.add(row)
            db.session.flush()
            return row

        transcript = document("transcript", "成績單.pdf", b"%PDF transcript")
        cert_keep = document("credential", "乙級證照.png", b"png-keep")
        cert_drop = document("credential", "丙級證照.png", b"png-drop")
        db.session.add_all([
            LearningCourseRecord(student_id=stu.id, course_name="資料庫管理", normalized_course_name="資料庫管理",
                                 score=90, confirmation_status="confirmed", source_document_id=transcript.id),
            LearningCourseRecord(student_id=stu.id, course_name="不想放的會計學", normalized_course_name="不想放的會計學",
                                 score=55, confirmation_status="confirmed", source_document_id=transcript.id,
                                 excluded_from_package=True),
            CredentialRecord(student_id=stu.id, credential_name="乙級軟體應用", confirmation_status="confirmed",
                             source_document_id=cert_keep.id),
            CredentialRecord(student_id=stu.id, credential_name="不想放的丙級證照", confirmation_status="confirmed",
                             source_document_id=cert_drop.id, excluded_from_package=True),
        ])
        keep = Portfolio(student_id=stu.id, title="校園黑客松", category="competition", status="confirmed")
        drop = Portfolio(student_id=stu.id, title="不想放的校內比賽", category="competition", status="confirmed",
                         excluded_from_package=True)
        db.session.add_all([keep, drop])
        db.session.flush()
        for record, name in ((keep, "黑客松獎狀.jpg"), (drop, "校內比賽獎狀.jpg")):
            location = storage_service.save(b"jpg-" + name.encode(), owner_id=stu.id, folder="", filename=name)
            db.session.add(PortfolioEvidence(portfolio_id=record.id, evidence_type="file", display_name=name,
                                             file_path=location))
        db.session.commit()


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path / "uploads"), "MAIL_RETRY_DELAY": 0,
                      "MAIL_SITE_URL": "https://portfolio.example.test"})
    _seed(app)
    yield app


@pytest.fixture()
def sent(monkeypatch):
    """假 SMTP：記下寄出的信（收件者、主旨、內文、附件）。"""
    box = []
    monkeypatch.setattr(email_notify, "smtp_ready", lambda: True)
    monkeypatch.setattr(email_notify, "_send",
                        lambda to, subject, body, attachments=(): box.append((to, subject, body, list(attachments))))
    return box


def login(app, username="stu"):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw-123456789"})
    return client


def _stu():
    return User.query.filter_by(username="stu").one()


def _pid(app):
    with app.app_context():
        return AdmissionProgram.query.filter_by(program_code="Z").one().id


def _names(data):
    return zipfile.ZipFile(io.BytesIO(data)).namelist()


# ---------- 雲端：每位學生一個資料夾 ----------

def test_drive_files_go_into_one_folder_per_student(tmp_path):
    fake = FolderDriveClient()
    app = drive_app(tmp_path, fake)
    with app.app_context():
        db.create_all()
        user = User(username="stu", display_name="測試生", role="student")
        user.set_password("pw-123456789")
        db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=user.id, student_no="T-0000009", class_name="資管科五甲"))
        db.session.commit()
        first = storage_service.save(b"a", owner_id=user.id, folder="learning-profile", filename="成績單.pdf")
        second = storage_service.save(b"b", owner_id=user.id, folder="", filename="獎狀.jpg")
        third = storage_service.save(b"c", owner_id=user.id, folder="autobiography", filename="自傳.docx")
        again = storage_service.save(b"d", owner_id=user.id, folder="", filename="獎狀2.jpg")

    student_folders = [f for f in fake.children.values() if f["parent"] == "folder-1"]
    assert len(student_folders) == 1 and "T-0000009" in student_folders[0]["name"]
    student_id = student_folders[0]["id"]
    sub = {f["name"]: f["id"] for f in fake.children.values() if f["parent"] == student_id}
    assert set(sub) == {"成績單與證照", "經歷佐證", "自傳"}
    folder_of = {loc: fake.files[loc.split(":", 1)[1].split("/")[0]]["folder"] for loc in (first, second, third, again)}
    assert folder_of[first] == sub["成績單與證照"]
    assert folder_of[second] == folder_of[again] == sub["經歷佐證"]
    assert folder_of[third] == sub["自傳"]
    assert sum(1 for call in fake.calls if call[0] == "ensure_child_folder") == 4  # 資料夾編號會記住，不重複問


# ---------- 一鍵打包 ----------

def test_zip_has_word_autobiography_sources_and_evidence(app):
    with app.app_context():
        program = AdmissionProgram.query.filter_by(program_code="Z").one()
        autobiography_service.generate_draft(_stu(), program, {
            "focus_credential": "為了確認基礎能力考了軟體應用證照。", "focus_competition": "我參加校內黑客松，負責簡報。"})
        data, manifest = package_zip.build_zip(_stu(), program)

    names = _names(data.getvalue())
    assert any(name.endswith("01_備審資料.docx") for name in names)
    assert any("02_自傳" in name and name.endswith(".docx") for name in names)
    assert any(name.endswith("乙級證照.png") for name in names)
    assert any(name.endswith("校園黑客松/黑客松獎狀.jpg") for name in names)
    assert any(name.endswith("清單.txt") for name in names)
    assert all(name.startswith("備審資料_測試科大Z資訊管理系/") for name in names)
    assert manifest["included"] and "乙級證照.png" in "".join(manifest["included"])


def test_zip_leaves_out_what_the_student_excluded(app):
    with app.app_context():
        program = AdmissionProgram.query.filter_by(program_code="Z").one()
        data, manifest = package_zip.build_zip(_stu(), program)

    names = "\n".join(_names(data.getvalue()))
    assert "丙級證照.png" not in names
    assert "校內比賽獎狀.jpg" not in names
    assert "成績單.pdf" not in names  # 有課程選擇不放，整份原始成績單不放（裡面看得到那一科）
    assert any("成績單.pdf" in line for line in manifest["skipped"])


def _checklist(data):
    archive = zipfile.ZipFile(io.BytesIO(data))
    return archive.read(next(n for n in archive.namelist() if n.endswith("清單.txt"))).decode("utf-8")


def test_checklist_explains_evidence_left_out_by_choice(app):
    """B24 2026-11-16 實測：選「不放」的經歷，佐證檔沒放，但清單完全沒寫，學生以為檔案漏了。"""
    with app.app_context():
        data, manifest = package_zip.build_zip(_stu(), AdmissionProgram.query.filter_by(program_code="Z").one())

    checklist = _checklist(data.getvalue())
    assert any("不想放的校內比賽" in line and "選擇不放" in line for line in manifest["skipped"])
    assert "校內比賽獎狀.jpg" in checklist.split("沒有放入：")[1]
    assert "校內比賽獎狀.jpg" not in checklist.split("沒有放入：")[0]


def test_checklist_reminds_when_autobiography_mentions_excluded_record(app):
    """自傳是學生自己的文字，系統不改；但提到選擇不放的經歷時，清單要提醒學生自己決定要不要改。"""
    with app.app_context():
        program = AdmissionProgram.query.filter_by(program_code="Z").one()
        autobiography_service.generate_draft(_stu(), program, {
            "focus_credential": "為了確認基礎能力考了軟體應用證照。",
            "focus_competition": "我參加不想放的校內比賽，也參加校園黑客松。"})
        data, manifest = package_zip.build_zip(_stu(), program)

    checklist = _checklist(data.getvalue())
    assert any("不想放的校內比賽" in note for note in manifest["notes"])
    assert "請注意：" in checklist and "不想放的校內比賽" in checklist.split("請注意：")[1]
    assert not any("校園黑客松" in note for note in manifest["notes"])  # 有放的經歷不用提醒


def test_checklist_does_not_remind_for_a_kept_record_with_a_longer_name(app):
    """2026-11-16 實測：排除的「資料庫應用」被當成提到，其實自傳寫的是有放的「資料庫應用乙級」。"""
    with app.app_context():
        stu = _stu()
        db.session.add_all([
            CredentialRecord(student_id=stu.id, credential_name="資料庫應用乙級", confirmation_status="confirmed"),
            CredentialRecord(student_id=stu.id, credential_name="資料庫應用", confirmation_status="confirmed",
                             excluded_from_package=True)])
        db.session.commit()
        program = AdmissionProgram.query.filter_by(program_code="Z").one()
        autobiography_service.generate_draft(_stu(), program, {
            "focus_credential": "我考到資料庫應用乙級。", "focus_competition": "我參加校園黑客松，負責簡報。"})
        _, manifest = package_zip.build_zip(_stu(), program)

    assert not any("資料庫應用" in note for note in manifest["notes"])


def test_checklist_has_no_reminder_when_autobiography_is_clean(app):
    with app.app_context():
        program = AdmissionProgram.query.filter_by(program_code="Z").one()
        autobiography_service.generate_draft(_stu(), program, {
            "focus_credential": "為了確認基礎能力考了軟體應用證照。", "focus_competition": "我參加校園黑客松，負責簡報。"})
        data, manifest = package_zip.build_zip(_stu(), program)

    assert manifest["notes"] == []
    assert "請注意：" not in _checklist(data.getvalue())


def test_zip_without_autobiography_still_builds(app):
    with app.app_context():
        data, _ = package_zip.build_zip(_stu(), AdmissionProgram.query.filter_by(program_code="Z").one())

    assert not any("02_自傳" in name for name in _names(data.getvalue()))


def test_student_downloads_zip_and_it_is_logged(app):
    response = login(app).get(f"/student/targets/{_pid(app)}/package.zip")

    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    assert any(name.endswith("01_備審資料.docx") for name in _names(response.data))
    with app.app_context():
        assert AuditLog.query.filter_by(action="package.zip_download").count() == 1


def test_other_student_cannot_download_my_zip(app):
    assert login(app, "other").get(f"/student/targets/{_pid(app)}/package.zip").status_code == 404


# ---------- 綁定備用信箱 ----------

def test_binding_sends_verification_and_only_verified_address_counts(app, sent):
    client = login(app)

    response = client.post("/account/backup-email", data={"backup_email": "me@personal.example.test"})

    assert response.status_code == 302
    assert sent and sent[0][0] == "me@personal.example.test"
    with app.app_context():
        user = _stu()
        assert user.backup_email == "me@personal.example.test" and user.backup_email_verified_at is None
        assert [r["key"] for r in backup_email.recipients(user)] == ["school"]
        token = backup_email.make_token(user)
    assert token in sent[0][2]  # 驗證連結在信裡

    assert client.get(f"/account/backup-email/verify/{token}").status_code == 302
    with app.app_context():
        user = _stu()
        assert user.backup_email_verified_at is not None
        assert [r["key"] for r in backup_email.recipients(user)] == ["school", "backup"]


def test_bad_address_and_stale_token_are_refused(app, sent):
    client = login(app)

    assert client.post("/account/backup-email", data={"backup_email": "not-an-email"}).status_code == 400
    client.post("/account/backup-email", data={"backup_email": "old@personal.example.test"})
    with app.app_context():
        old_token = backup_email.make_token(_stu())
    client.post("/account/backup-email", data={"backup_email": "new@personal.example.test"})

    assert client.get(f"/account/backup-email/verify/{old_token}").status_code == 400  # 換過信箱，舊連結失效
    assert client.get("/account/backup-email/verify/garbage").status_code == 400
    with app.app_context():
        assert _stu().backup_email_verified_at is None


def test_token_of_another_student_is_refused(app, sent):
    login(app).post("/account/backup-email", data={"backup_email": "me@personal.example.test"})
    with app.app_context():
        token = backup_email.make_token(_stu())

    assert login(app, "other").get(f"/account/backup-email/verify/{token}").status_code == 400


def test_student_removes_backup_email(app, sent):
    client = login(app)
    client.post("/account/backup-email", data={"backup_email": "me@personal.example.test"})

    client.post("/account/backup-email/remove")

    with app.app_context():
        assert _stu().backup_email is None


def test_account_page_shows_backup_email_section(app):
    page = login(app).get("/account/password").get_data(as_text=True)

    assert "備用信箱" in page and 'name="backup_email"' in page


# ---------- 寄到信箱 ----------

def test_package_is_mailed_to_school_address_as_attachment(app, sent):
    response = login(app).post(f"/student/targets/{_pid(app)}/package/send", data={"to": "school"})

    assert response.status_code == 302 and "mailed=sent" in response.headers["Location"]
    to, subject, body, attachments = sent[0]
    assert to == "stu@school.example.test"
    assert len(attachments) == 1 and attachments[0][0].endswith(".zip")
    assert any(name.endswith("01_備審資料.docx") for name in _names(attachments[0][1]))
    assert "55" not in body and "資料庫管理" not in body  # 信件內文不寫成績
    with app.app_context():
        log = AuditLog.query.filter_by(action="package.mail").one()
        assert "stu@school.example.test" not in str(log.detail_json)  # 操作紀錄不記信箱


def test_unverified_backup_address_cannot_receive(app, sent):
    client = login(app)
    client.post("/account/backup-email", data={"backup_email": "me@personal.example.test"})
    sent.clear()

    response = client.post(f"/student/targets/{_pid(app)}/package/send", data={"to": "backup"})

    assert response.status_code == 400
    assert sent == []


def test_gap_page_says_backup_address_is_waiting_for_confirmation(app):
    """B24 2026-11-16 實測：備用信箱已填、還沒確認時，原本寫「也還沒綁定備用信箱」，學生會以為沒填成功。"""
    with app.app_context():
        user = User.query.filter_by(username="other").one()
        user.backup_email = "wait@personal.example.test"
        db.session.add(StudentTarget(student_id=user.id, rule_version_id=AdmissionProgram.query.first().id))
        db.session.commit()
    text = login(app, "other").get(f"/student/targets/{_pid(app)}").get_data(as_text=True)

    assert "也還沒綁定備用信箱" not in text
    assert "wait@personal.example.test" in text and "等待確認" in text


def test_gap_page_warns_before_mailing_when_there_is_no_mail_account(app):
    """沒有寄信帳號時，按「打包寄給我」之前就說清楚不會真的寄出（不是按了才知道）。"""
    text = login(app).get(f"/student/targets/{_pid(app)}").get_data(as_text=True)

    assert "打包寄給我" in text
    assert "目前還沒有設定寄信帳號" in text


def test_gap_page_has_no_mail_warning_when_mail_is_ready(app, sent):
    text = login(app).get(f"/student/targets/{_pid(app)}").get_data(as_text=True)

    assert "目前還沒有設定寄信帳號" not in text


def test_verified_backup_address_receives(app, sent):
    client = login(app)
    client.post("/account/backup-email", data={"backup_email": "me@personal.example.test"})
    with app.app_context():
        token = backup_email.make_token(_stu())
    client.get(f"/account/backup-email/verify/{token}")
    sent.clear()

    client.post(f"/student/targets/{_pid(app)}/package/send", data={"to": "backup"})

    assert sent[0][0] == "me@personal.example.test"


def test_large_package_mails_a_login_link_instead(app, sent):
    app.config["MAIL_MAX_ATTACHMENT_MB"] = 0

    response = login(app).post(f"/student/targets/{_pid(app)}/package/send", data={"to": "school"})

    assert "mailed=link" in response.headers["Location"]
    _, _, body, attachments = sent[0]
    assert attachments == []
    assert f"https://portfolio.example.test/student/targets/{_pid(app)}/package.zip" in body


def test_without_smtp_nothing_is_sent_and_student_is_told(app):
    client = login(app)

    response = client.post(f"/student/targets/{_pid(app)}/package/send", data={"to": "school"})
    page = client.get(response.headers["Location"]).get_data(as_text=True)

    assert "mailed=logged" in response.headers["Location"]
    assert "沒有寄出" in page


def test_mailing_is_limited_per_day(app, sent):
    client = login(app)
    for _ in range(5):
        assert client.post(f"/student/targets/{_pid(app)}/package/send", data={"to": "school"}).status_code == 302

    assert client.post(f"/student/targets/{_pid(app)}/package/send", data={"to": "school"}).status_code == 429
    assert len(sent) == 5


def test_gap_page_has_zip_and_mail_controls(app):
    page = login(app).get(f"/student/targets/{_pid(app)}").get_data(as_text=True)

    assert f"/student/targets/{_pid(app)}/package.zip" in page
    assert f"/student/targets/{_pid(app)}/package/send" in page
    assert "學校信箱" in page and "/account/password#backup-email" in page


def test_demo_site_without_smtp_shows_confirm_link_on_the_page(tmp_path):
    """展示站（有 Demo 快速登入）沒有寄信帳號：頁面直接給確認連結，流程才走得完（2026-11-15 瀏覽器驗收發現）。"""
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path / "uploads"),
                      "DEMO_ACCOUNTS": [{"role": "student", "username": "stu", "password": "x", "label": "學生"}]})
    _seed(app)
    client = login(app)

    response = client.post("/account/backup-email", data={"backup_email": "me@personal.example.test"})
    page = client.get(response.headers["Location"]).get_data(as_text=True)

    assert "/account/backup-email/verify/" in page and "請通知管理員" not in page
    link = page.split('href="/account/backup-email/verify/')[1].split('"')[0]
    assert client.get(f"/account/backup-email/verify/{link}").status_code == 302
    with app.app_context():
        assert _stu().backup_email_verified_at is not None


def test_real_site_without_smtp_does_not_show_confirm_link(app):
    client = login(app)

    response = client.post("/account/backup-email", data={"backup_email": "me@personal.example.test"})
    page = client.get(response.headers["Location"]).get_data(as_text=True)

    assert "/account/backup-email/verify/" not in page and "請通知管理員" in page


# ---------- B30（2026-11-16）：信裡連結是完整網址、沒有寄信帳號時管理員代為確認 ----------

def _app_without_site_url(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path / "uploads"), "MAIL_RETRY_DELAY": 0, "MAIL_SITE_URL": ""})
    _seed(app)
    return app


def test_verify_link_is_absolute_without_mail_site_url(tmp_path, sent):
    app = _app_without_site_url(tmp_path)

    login(app).post("/account/backup-email", data={"backup_email": "me@personal.example.test"})

    assert "http://localhost/account/backup-email/verify/" in sent[0][2]


def test_verify_link_uses_https_behind_tunnel(tmp_path, sent):
    app = _app_without_site_url(tmp_path)

    login(app).post("/account/backup-email", data={"backup_email": "me@personal.example.test"},
                    headers={"X-Forwarded-Proto": "https"})

    assert "https://localhost/account/backup-email/verify/" in sent[0][2]


def _add_admin(app):
    with app.app_context():
        admin = User(username="adm", display_name="測試管理員", role="admin")
        admin.set_password("pw-123456789")
        db.session.add(admin)
        db.session.commit()


def test_admin_confirms_backup_email_when_no_mail_account(app):
    _add_admin(app)
    student = login(app)
    student.post("/account/backup-email", data={"backup_email": "me@personal.example.test"})
    assert "等管理員核對後確認" in student.get("/account/password").get_data(as_text=True)
    admin = login(app, "adm")
    page = admin.get("/admin/accounts").get_data(as_text=True)
    assert "等待確認的備用信箱（1）" in page and "me@personal.example.test" in page and "沒有設定寄信帳號" in page
    with app.app_context():
        stu_id = _stu().id

    response = admin.post(f"/admin/accounts/{stu_id}/backup-email/confirm",
                          data={"address": "me@personal.example.test"})

    assert response.status_code == 302
    with app.app_context():
        user = _stu()
        assert user.backup_email_verified_at is not None
        assert [r["key"] for r in backup_email.recipients(user)] == ["school", "backup"]
        log = AuditLog.query.filter_by(action="user.backup_email_admin_verify").one()
        assert log.target_id == stu_id and "personal" not in str(log.detail_json)  # 操作紀錄不記信箱
    assert "已確認" in admin.get("/admin/accounts").get_data(as_text=True)


def test_admin_cannot_confirm_an_address_the_student_already_changed(app):
    _add_admin(app)
    student = login(app)
    student.post("/account/backup-email", data={"backup_email": "old@personal.example.test"})
    student.post("/account/backup-email", data={"backup_email": "new@personal.example.test"})
    with app.app_context():
        stu_id = _stu().id

    login(app, "adm").post(f"/admin/accounts/{stu_id}/backup-email/confirm",
                           data={"address": "old@personal.example.test"})

    with app.app_context():
        assert _stu().backup_email_verified_at is None


def test_student_cannot_use_admin_confirm(app):
    student = login(app)
    student.post("/account/backup-email", data={"backup_email": "me@personal.example.test"})
    with app.app_context():
        stu_id = _stu().id

    response = student.post(f"/admin/accounts/{stu_id}/backup-email/confirm",
                            data={"address": "me@personal.example.test"})

    assert response.status_code in (302, 403)
    with app.app_context():
        assert _stu().backup_email_verified_at is None

"""表單下載區頁面：科辦上架、改版、下架；學生與老師只看到、只下載得到開放給自己且上架中的最新版。"""
import io

from app import create_app
from app.extensions import db
from app.models import AuditLog, ClassAdvisor, FormCategory, FormItem, FormItemVersion, StudentProfile, User

PDF_V1 = b"%PDF-1.4\n% version one\n"
PDF_V2 = b"%PDF-1.4\n% version two\n"


def forms_app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        for username, role in [("stu", "student"), ("tea", "teacher"), ("staff", "staff")]:
            user = User(username=username, display_name=f"合成{username}", role=role,
                        job_title="主任" if role == "staff" else None)
            user.set_password("pw")
            db.session.add(user)
        db.session.flush()
        stu = User.query.filter_by(username="stu").one()
        tea = User.query.filter_by(username="tea").one()
        db.session.add(StudentProfile(user_id=stu.id, student_no="DEMO-0001", class_name="資管科測試班", admission_year=111))
        db.session.add(ClassAdvisor(teacher_id=tea.id, class_name="資管科測試班", school_year=115))
        db.session.add(FormCategory(name="常用表格", sort_order=1))
        db.session.commit()
    return app


def login(app, username):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def category_id(app):
    with app.app_context():
        return FormCategory.query.filter_by(name="常用表格").one().id


def publish(app, client, title="公假申請單", students=True, teachers=True, data=PDF_V1, filename="公假單.pdf"):
    form = {"category_id": str(category_id(app)), "title": title, "description": "合成說明",
            "file": (io.BytesIO(data), filename)}
    if students:
        form["open_to_students"] = "1"
    if teachers:
        form["open_to_teachers"] = "1"
    return client.post("/staff/forms", data=form, content_type="multipart/form-data")


def item_id(app, title="公假申請單"):
    with app.app_context():
        return FormItem.query.filter_by(title=title).one().id


def test_teacher_only_form_hidden_and_403_for_student(tmp_path):
    app = forms_app(tmp_path)
    staff = login(app, "staff")
    assert publish(app, staff, title="訪視紀錄表", students=False).status_code == 302
    form_id = item_id(app, "訪視紀錄表")

    teacher, student = login(app, "tea"), login(app, "stu")
    assert "訪視紀錄表" in teacher.get("/forms").get_data(as_text=True)
    download = teacher.get(f"/forms/{form_id}/download")
    assert download.status_code == 200 and download.data == PDF_V1
    assert "attachment" in download.headers["Content-Disposition"]

    assert "訪視紀錄表" not in student.get("/forms").get_data(as_text=True)
    assert student.get(f"/forms/{form_id}/download").status_code == 403
    assert student.get("/forms/9999/download").status_code == 404


def test_new_version_download_returns_new_content_old_kept(tmp_path):
    app = forms_app(tmp_path)
    staff = login(app, "staff")
    publish(app, staff)
    form_id = item_id(app)

    response = staff.post(f"/staff/forms/{form_id}/versions", content_type="multipart/form-data",
                          data={"note": "改簽名欄", "file": (io.BytesIO(PDF_V2), "公假單-第二版.pdf")})
    assert response.status_code == 302

    student = login(app, "stu")
    assert student.get(f"/forms/{form_id}/download").data == PDF_V2
    with app.app_context():
        versions = FormItemVersion.query.filter_by(item_id=form_id).order_by(FormItemVersion.version_no).all()
        assert [v.version_no for v in versions] == [1, 2]
        old_id = versions[0].id
    detail = staff.get(f"/staff/forms/{form_id}").get_data(as_text=True)
    assert "第 2 版" in detail and "第 1 版" in detail and "改簽名欄" in detail
    assert staff.get(f"/staff/forms/versions/{old_id}/download").data == PDF_V1
    # 舊版下載只給科辦
    assert student.get(f"/staff/forms/versions/{old_id}/download").status_code == 403


def test_unpublish_hides_and_blocks_then_republish(tmp_path):
    app = forms_app(tmp_path)
    staff = login(app, "staff")
    publish(app, staff)
    form_id = item_id(app)
    student = login(app, "stu")

    assert staff.post(f"/staff/forms/{form_id}/publish", data={"action": "unpublish"}).status_code == 302
    assert "公假申請單" not in student.get("/forms").get_data(as_text=True)
    assert student.get(f"/forms/{form_id}/download").status_code == 403
    assert "已下架" in staff.get("/staff/forms").get_data(as_text=True)
    assert staff.get(f"/forms/{form_id}/download").status_code == 200  # 科辦仍可取檔

    staff.post(f"/staff/forms/{form_id}/publish", data={"action": "republish"})
    assert student.get(f"/forms/{form_id}/download").status_code == 200


def test_inactive_category_blocks_download(tmp_path):
    app = forms_app(tmp_path)
    staff = login(app, "staff")
    publish(app, staff)
    form_id = item_id(app)
    cid = category_id(app)

    staff.post(f"/staff/forms/categories/{cid}", data={"name": "常用表格", "sort_order": "1"})  # 沒勾啟用＝停用
    student = login(app, "stu")
    assert "公假申請單" not in student.get("/forms").get_data(as_text=True)
    assert student.get(f"/forms/{form_id}/download").status_code == 403


def test_staff_manages_categories(tmp_path):
    app = forms_app(tmp_path)
    staff = login(app, "staff")
    assert staff.post("/staff/forms/categories", data={"name": "實習", "sort_order": "5"}).status_code == 302
    assert staff.post("/staff/forms/categories", data={"name": "實習"}).status_code == 400  # 重複
    assert staff.post("/staff/forms/categories", data={"name": "  "}).status_code == 400
    with app.app_context():
        category = FormCategory.query.filter_by(name="實習").one()
        assert category.sort_order == 5 and category.is_active
        cid = category.id
    staff.post(f"/staff/forms/categories/{cid}", data={"name": "校外實習", "sort_order": "2", "is_active": "1"})
    with app.app_context():
        category = db.session.get(FormCategory, cid)
        assert category.name == "校外實習" and category.sort_order == 2 and category.is_active


def test_staff_edits_item_details(tmp_path):
    app = forms_app(tmp_path)
    staff = login(app, "staff")
    publish(app, staff)
    form_id = item_id(app)

    staff.post(f"/staff/forms/{form_id}", data={"category_id": str(category_id(app)), "title": "公假單（新）",
                                               "description": "改說明", "open_to_teachers": "1"})
    with app.app_context():
        item = db.session.get(FormItem, form_id)
        assert item.title == "公假單（新）" and not item.open_to_students and item.open_to_teachers
        assert len(item.versions) == 1  # 改資料不會動到檔案
    assert login(app, "stu").get(f"/forms/{form_id}/download").status_code == 403
    # 開放對象全不勾不行
    response = staff.post(f"/staff/forms/{form_id}", data={"category_id": str(category_id(app)), "title": "x"})
    assert response.status_code == 400


def test_student_and_teacher_cannot_use_staff_pages(tmp_path):
    app = forms_app(tmp_path)
    publish(app, login(app, "staff"))
    form_id = item_id(app)
    for username in ("stu", "tea"):
        client = login(app, username)
        assert client.get("/staff/forms").status_code == 403
        assert client.get(f"/staff/forms/{form_id}").status_code == 403
        assert publish(app, client, title="偷上架").status_code == 403
        assert client.post(f"/staff/forms/{form_id}/publish", data={"action": "unpublish"}).status_code == 403
        assert client.post(f"/staff/forms/{form_id}/versions", content_type="multipart/form-data",
                           data={"file": (io.BytesIO(PDF_V2), "x.pdf")}).status_code == 403
    assert app.test_client().get("/forms").status_code in (302, 401)
    with app.app_context():
        assert FormItem.query.count() == 1 and FormItemVersion.query.count() == 1


def test_create_requires_audience_and_valid_file(tmp_path):
    app = forms_app(tmp_path)
    staff = login(app, "staff")
    no_audience = publish(app, staff, students=False, teachers=False)
    assert no_audience.status_code == 400 and "開放對象" in no_audience.get_data(as_text=True)
    bad_type = publish(app, staff, filename="run.exe")
    assert bad_type.status_code == 400 and "格式" in bad_type.get_data(as_text=True)
    fake_pdf = publish(app, staff, data=b"not a pdf")
    assert fake_pdf.status_code == 400 and "不符" in fake_pdf.get_data(as_text=True)
    no_title = staff.post("/staff/forms", content_type="multipart/form-data",
                          data={"category_id": str(category_id(app)), "title": "", "open_to_students": "1",
                                "file": (io.BytesIO(PDF_V1), "a.pdf")})
    assert no_title.status_code == 400
    bad_version = staff.post("/staff/forms/1/versions", content_type="multipart/form-data",
                             data={"file": (io.BytesIO(b"x"), "a.pdf")})
    assert bad_version.status_code == 404  # 還沒有任何表單
    with app.app_context():
        assert FormItem.query.count() == 0 and FormItemVersion.query.count() == 0


def test_bad_new_version_is_rejected_and_old_version_stays(tmp_path):
    app = forms_app(tmp_path)
    staff = login(app, "staff")
    publish(app, staff)
    form_id = item_id(app)
    response = staff.post(f"/staff/forms/{form_id}/versions", content_type="multipart/form-data",
                          data={"file": (io.BytesIO(b"oops"), "v2.pdf")})
    assert response.status_code == 400
    assert login(app, "stu").get(f"/forms/{form_id}/download").data == PDF_V1


def test_actions_write_audit_logs(tmp_path):
    app = forms_app(tmp_path)
    staff = login(app, "staff")
    staff.post("/staff/forms/categories", data={"name": "實習"})
    publish(app, staff)
    form_id = item_id(app)
    staff.post(f"/staff/forms/{form_id}/versions", content_type="multipart/form-data",
               data={"file": (io.BytesIO(PDF_V2), "v2.pdf")})
    staff.post(f"/staff/forms/{form_id}/publish", data={"action": "unpublish"})
    staff.post(f"/staff/forms/{form_id}/publish", data={"action": "republish"})
    with app.app_context():
        actions = [log.action for log in AuditLog.query.order_by(AuditLog.id)]
    for action in ("form_category.create", "form.publish", "form.new_version", "form.unpublish", "form.republish"):
        assert action in actions


def test_nav_entries(tmp_path):
    app = forms_app(tmp_path)
    assert "表單下載區" in login(app, "staff").get("/staff/dashboard").get_data(as_text=True)
    assert "表單下載" in login(app, "tea").get("/teacher/dashboard").get_data(as_text=True)
    student_page = login(app, "stu").get("/student/dashboard").get_data(as_text=True)
    assert 'href="/forms"' in student_page


def test_forms_page_search_and_empty_state(tmp_path):
    app = forms_app(tmp_path)
    student = login(app, "stu")
    assert "目前沒有" in student.get("/forms").get_data(as_text=True)
    publish(app, login(app, "staff"))
    page = student.get("/forms").get_data(as_text=True)
    assert "常用表格" in page and "公假申請單" in page
    assert "公假申請單" not in student.get("/forms?q=實習").get_data(as_text=True)

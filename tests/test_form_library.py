"""表單下載區（UC-28／F-53）的資料與規則：上傳檢查、改版、誰能下載、資料庫遷移、示範資料。"""
import pytest
from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.models import FormCategory, FormItem, FormItemVersion, User
from app.services import form_library_service as forms
from app.services import storage_service

PDF = b"%PDF-1.4\n%synthetic\n"
DOCX = b"PK\x03\x04synthetic-zip"
DOC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1synthetic-ole"


def make_app(tmp_path, **config):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path), **config})
    with app.app_context():
        db.create_all()
        for username, role in [("stu", "student"), ("tea", "teacher"), ("staff", "staff")]:
            user = User(username=username, display_name=username, role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.commit()
    return app


def user(username):
    return User.query.filter_by(username=username).one()


def make_item(students=True, teachers=True, published=True, active=True, data=PDF):
    category = FormCategory(name=f"分類{FormCategory.query.count() + 1}", sort_order=1, is_active=active)
    db.session.add(category)
    db.session.flush()
    item = FormItem(category=category, title="請假單", description="", open_to_students=students,
                    open_to_teachers=teachers, is_published=published, created_by_id=user("staff").id)
    db.session.add(item)
    db.session.flush()
    forms.add_version(item, "請假單.pdf", data, user("staff"))
    db.session.commit()
    return item


@pytest.mark.parametrize("filename,data", [
    ("tool.exe", PDF),          # 副檔名不在白名單
    ("notes.txt", b"hello"),    # 科辦表單不收 txt
    ("fake.pdf", b"hello"),     # 副檔名是 PDF，內容不是
    ("fake.docx", PDF),         # docx 應該是 ZIP
    ("fake.xls", DOCX),         # xls 應該是 OLE
    ("empty.pdf", b""),         # 空檔
    ("../evil.pdf", PDF),       # 路徑
])
def test_check_upload_rejects_bad_files(tmp_path, filename, data):
    app = make_app(tmp_path)
    with app.app_context(), pytest.raises(forms.UploadRejected):
        forms.check_upload(filename, data)


def test_check_upload_rejects_oversized_file(tmp_path):
    app = make_app(tmp_path, FORM_MAX_BYTES=100)
    with app.app_context(), pytest.raises(forms.UploadRejected) as error:
        forms.check_upload("big.pdf", PDF + b"0" * 200)
    assert "MB" in str(error.value) or "太大" in str(error.value)


@pytest.mark.parametrize("filename,data", [("表單 A.pdf", PDF), ("b.docx", DOCX), ("c.doc", DOC),
                                           ("d.xlsx", DOCX), ("e.odt", DOCX), ("f.ods", DOCX), ("g.xls", DOC)])
def test_check_upload_accepts_allowed_files(tmp_path, filename, data):
    app = make_app(tmp_path)
    with app.app_context():
        safe = forms.check_upload(filename, data)
    assert safe.rsplit(".", 1)[-1] == filename.rsplit(".", 1)[-1]
    assert "/" not in safe and " " not in safe


def test_add_version_increments_and_keeps_old_file(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        item = make_item(data=PDF + b"v1")
        second = forms.add_version(item, "請假單-新版.pdf", PDF + b"v2", user("staff"), note="改日期欄位")
        db.session.commit()

        versions = FormItemVersion.query.filter_by(item_id=item.id).order_by(FormItemVersion.version_no).all()
        assert [v.version_no for v in versions] == [1, 2]
        assert item.latest_version.id == second.id
        assert second.note == "改日期欄位"
        assert second.original_filename == "請假單-新版.pdf"
        assert second.file_size == len(PDF + b"v2") and len(second.file_sha256) == 64
        assert storage_service.read_bytes(versions[0].file_path) == PDF + b"v1"
        assert storage_service.read_bytes(versions[1].file_path) == PDF + b"v2"


def test_can_download_rules(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        both = make_item()
        teacher_only = make_item(students=False)
        student_only = make_item(teachers=False)
        unpublished = make_item(published=False)
        inactive = make_item(active=False)
        stu, tea, staff = user("stu"), user("tea"), user("staff")

        assert forms.can_download(stu, both) and forms.can_download(tea, both)
        assert not forms.can_download(stu, teacher_only) and forms.can_download(tea, teacher_only)
        assert forms.can_download(stu, student_only) and not forms.can_download(tea, student_only)
        for item in (unpublished, inactive):
            assert not forms.can_download(stu, item) and not forms.can_download(tea, item)
        for item in (both, teacher_only, student_only, unpublished, inactive):
            assert forms.can_download(staff, item)
        assert not forms.can_download(None, both)

        student_view = [i.id for _, items in forms.visible_items(stu) for i in items]
        assert sorted(student_view) == sorted([both.id, student_only.id])
        teacher_view = [i.id for _, items in forms.visible_items(tea) for i in items]
        assert sorted(teacher_view) == sorted([both.id, teacher_only.id])


def test_visible_items_keyword_search(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        item = make_item()
        item.description = "實習期間請假用"
        db.session.commit()
        assert forms.visible_items(user("stu"), "實習")
        assert forms.visible_items(user("stu"), "請假單")
        assert forms.visible_items(user("stu"), "畢業") == []


def test_migration_creates_and_drops_form_tables(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'm.db'}", "TESTING": True})
    runner = app.test_cli_runner()
    assert runner.invoke(args=["db", "upgrade"]).exit_code == 0
    with app.app_context():
        tables = set(inspect(db.engine).get_table_names())
        assert {"form_categories", "form_items", "form_item_versions"} <= tables
        columns = {c["name"] for c in inspect(db.engine).get_columns("form_item_versions")}
        assert {"item_id", "version_no", "file_path", "original_filename", "file_sha256"} <= columns
    assert runner.invoke(args=["db", "downgrade", "b20261105c01"]).exit_code == 0
    with app.app_context():
        assert not inspect(db.engine).has_table("form_items")


def test_seed_demo_forms_is_synthetic(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        forms.seed_demo_forms(user("staff"))
        db.session.commit()
        names = {c.name for c in FormCategory.query.all()}
        assert {"實習", "專題", "常用表格", "相關法規"} <= names
        items = FormItem.query.all()
        assert len(items) >= 6
        assert any(len(i.versions) >= 2 for i in items)                       # 展示改版
        assert any(i.open_to_teachers and not i.open_to_students for i in items)
        assert any(not i.is_published for i in items)
        for item in items:
            data = storage_service.read_bytes(item.latest_version.file_path)
            assert data.startswith(b"%PDF") and b"Synthetic demo" in data

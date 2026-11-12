"""科辦批量開立電子獎狀（2026-11-12 指導老師）：科上辦活動時貼上或上傳名單，先看預覽與錯誤列，
確認後一次建立多張。核准、驗證碼、通知、操作紀錄都和單張開立相同。名單全部是合成資料，僅為測試資料。"""
import io
from datetime import date

from app.extensions import db
from app.models import AuditLog, AwardCertificate, Notification, Portfolio
from app.services import certificate_batch_service as batch
from tests.test_award_certificates import cert_app, client_for

ROWS = ("學號,活動名稱,獎項或服務內容,日期\n"
        "111534105,資管科資訊週程式競賽,榮獲第一名,2026-10-20\n"
        "111534107,資管科資訊週程式競賽,擔任工作人員,2026/10/20\n")
URL = "/staff/certificates/batch"


def post(app, rows=ROWS, action="preview", username="staff", **extra):
    return client_for(app, username).post(URL, data={"rows": rows, "action": action, **extra})


def test_parse_accepts_commas_tabs_header_and_roc_dates(tmp_path):
    app = cert_app(tmp_path)
    with app.app_context():
        rows = batch.parse_rows("學號\t活動名稱\t獎項或服務內容\t日期\n"
                                "111534105\t迎新活動\t擔任關主\t115/9/5\n"
                                "\n"
                                "111534107，迎新活動，擔任關主，2026-09-05\n")
    assert [row.line_no for row in rows] == [2, 4]
    assert all(row.ok for row in rows)
    assert rows[0].day == date(2026, 9, 5) and rows[1].day == date(2026, 9, 5)
    assert rows[0].student.display_name == "王小明" and rows[1].activity == "迎新活動"


def test_parse_reports_error_rows(tmp_path):
    app = cert_app(tmp_path)
    with app.app_context():
        rows = batch.parse_rows(
            "111534105,資訊週,榮獲第一名,2026-10-20\n"
            "999999999,資訊週,榮獲第一名,2026-10-20\n"      # 查無學號
            "111534105,資訊週,榮獲第一名,2026-10-20\n"      # 和第 1 列重複
            "111534107,資訊週,,2026-10-20\n"                # 缺獎項
            "111534107,資訊週,佳作\n"                       # 缺日期欄
            "111534107,資訊週,佳作,十月二十日\n"            # 日期看不懂
            "111534107,資訊週,佳作,2099-01-01\n")           # 未來的日期
    assert [row.ok for row in rows] == [True, False, False, False, False, False, False]
    errors = [row.error for row in rows]
    assert "查無學號" in errors[1]
    assert "重複" in errors[2] and "第 1 列" in errors[2]
    assert "獎項或服務內容" in errors[3]
    assert "日期" in errors[4] and "日期" in errors[5] and "日期" in errors[6]


def test_parse_flags_certificate_already_issued(tmp_path):
    app = cert_app(tmp_path)
    post(app, action="confirm")
    with app.app_context():
        rows = batch.parse_rows(ROWS)
    assert [row.ok for row in rows] == [False, False]
    assert "已經開過" in rows[0].error


def test_parse_rejects_too_many_rows(tmp_path):
    app = cert_app(tmp_path)
    text = "\n".join(f"111534105,活動{n},參與,2026-10-20" for n in range(batch.MAX_ROWS + 1))
    assert post(app, rows=text).status_code == 400
    with app.app_context():
        assert AwardCertificate.query.count() == 0


def test_page_has_entry_and_form(tmp_path):
    app = cert_app(tmp_path)
    staff = client_for(app, "staff")
    assert f'href="{URL}"' in staff.get("/staff/certificates").get_data(as_text=True)
    page = staff.get(URL).get_data(as_text=True)
    assert 'name="rows"' in page and 'name="file"' in page and "學號,活動名稱,獎項或服務內容,日期" in page


def test_preview_shows_rows_and_errors_without_creating(tmp_path):
    app = cert_app(tmp_path)
    response = post(app, rows=ROWS + "999999999,資訊週,佳作,2026-10-20\n")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "王小明" in page and "林小美" in page and "查無學號" in page
    assert "可以建立 2 張" in page and "1 列有問題" in page
    assert 'value="confirm"' in page
    with app.app_context():
        assert AwardCertificate.query.count() == 0
        assert AuditLog.query.filter(AuditLog.action.like("certificate.%")).count() == 0


def test_preview_without_valid_rows_has_no_confirm_button(tmp_path):
    app = cert_app(tmp_path)
    page = post(app, rows="999999999,資訊週,佳作,2026-10-20").get_data(as_text=True)
    assert 'value="confirm"' not in page
    assert post(app, rows="   ").status_code == 400


def test_confirm_creates_approved_certificates_like_single_issue(tmp_path):
    app = cert_app(tmp_path)
    response = post(app, rows=ROWS + "999999999,資訊週,佳作,2026-10-20\n", action="confirm")
    page = response.get_data(as_text=True)
    assert response.status_code == 200 and "已建立 2 張" in page and "查無學號" in page
    with app.app_context():
        certs = AwardCertificate.query.order_by(AwardCertificate.id).all()
        assert len(certs) == 2
        first = certs[0]
        assert all(c.status == "approved" and c.issued_on == date.today() and c.reviewed_by.username == "staff"
                   for c in certs)
        assert len({c.verify_code for c in certs}) == 2 and all(len(c.verify_code) == 8 for c in certs)
        assert first.kind == "activity" and first.title == "活動證明" and first.issuer == "資訊管理科"
        assert "王小明" in first.body and "111534105" in first.body
        assert "民國 115 年 10 月 20 日" in first.body
        assert "資管科資訊週程式競賽" in first.body and "榮獲第一名" in first.body
        record = first.portfolio
        assert record.source == "department_certificate" and record.category == "activity"
        assert record.status == "confirmed" and record.semester == 1
        assert record.school_year == 5  # 111 入學，115 學年度是專五
        assert Notification.query.count() == 2
        assert AuditLog.query.filter_by(action="certificate.issue").count() == 2
        summary = AuditLog.query.filter_by(action="certificate.batch_issue").one()
        assert summary.detail_json == {"count": 2, "skipped": 1}
        assert f"/certificates/{first.id}" in page
        assert f"ids={certs[0].id},{certs[1].id}" in page  # 整批列印的連結


def test_confirm_can_use_custom_title(tmp_path):
    app = cert_app(tmp_path)
    post(app, action="confirm", title="獎狀")
    with app.app_context():
        assert {c.title for c in AwardCertificate.query.all()} == {"獎狀"}


def test_confirm_twice_does_not_duplicate(tmp_path):
    app = cert_app(tmp_path)
    post(app, action="confirm")
    again = post(app, action="confirm")
    assert again.status_code == 400
    with app.app_context():
        assert AwardCertificate.query.count() == 2 and Portfolio.query.filter_by(source="department_certificate").count() == 2


def test_upload_csv_file(tmp_path):
    app = cert_app(tmp_path)
    for encoding in ("utf-8-sig", "big5"):
        data = {"action": "preview", "rows": "", "file": (io.BytesIO(ROWS.encode(encoding)), "名單.csv")}
        response = client_for(app, "staff").post(URL, data=data, content_type="multipart/form-data")
        page = response.get_data(as_text=True)
        assert response.status_code == 200 and "可以建立 2 張" in page and "資管科資訊週程式競賽" in page
    bad = {"action": "preview", "rows": "", "file": (io.BytesIO(b"\xff\xfe\x00\x81" * 10), "名單.xlsx")}
    assert client_for(app, "staff").post(URL, data=bad, content_type="multipart/form-data").status_code == 400


def test_only_staff_can_batch_issue(tmp_path):
    app = cert_app(tmp_path)
    for username in ("stu", "t1"):
        assert client_for(app, username).get(URL).status_code == 403
        assert post(app, action="confirm", username=username).status_code == 403
    assert app.test_client().post(URL, data={"rows": ROWS, "action": "confirm"}).status_code in (302, 401, 403)
    with app.app_context():
        assert AwardCertificate.query.count() == 0


def test_batch_print_page_lists_all_certificates(tmp_path):
    app = cert_app(tmp_path)
    post(app, action="confirm")
    with app.app_context():
        ids = [c.id for c in AwardCertificate.query.order_by(AwardCertificate.id).all()]
        codes = [c.verify_code for c in AwardCertificate.query.all()]
    url = f"/staff/certificates/print?ids={ids[0]},{ids[1]}"
    page = client_for(app, "staff").get(url).get_data(as_text=True)
    assert all(code in page for code in codes) and page.count('class="sheet"') == 2
    assert client_for(app, "stu").get(url).status_code == 403
    assert client_for(app, "staff").get("/staff/certificates/print?ids=abc").status_code == 404


def test_single_certificate_page_still_works(tmp_path):
    app = cert_app(tmp_path)
    post(app, action="confirm")
    with app.app_context():
        cert = AwardCertificate.query.filter_by(student_id=AwardCertificate.query.first().student_id).first()
        cert_id, code = cert.id, cert.verify_code
    page = client_for(app, "stu").get(f"/certificates/{cert_id}").get_data(as_text=True)
    assert code in page and page.count('class="sheet"') == 1

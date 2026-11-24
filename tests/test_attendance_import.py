import io

from app.models import Portfolio, SourceDocument
from tests.test_student_records import login, records_app


URL = "/student/attendance-records"
PASTE = "學年度\t學期\t曠課\t事假\t病假\n114\t1\t2\t0\t3"


def test_attendance_import_reviews_then_saves_only_totals(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    assert URL in client.get("/student/portfolio").get_data(as_text=True)

    preview = client.post(URL, data={"pasted_table": PASTE})
    assert preview.status_code == 200
    assert 'name="病假" value="3"' in preview.get_data(as_text=True)
    assert "114 學年度" not in client.get(URL).get_data(as_text=True)

    data = {"school_year": "114", "semester": "1", "曠課": "2", "事假": "0", "病假": "3"}
    assert client.post(URL + "/confirm", data=data).status_code == 302
    data["病假"] = "4"
    assert client.post(URL + "/confirm", data=data).status_code == 302
    html = client.get(URL).get_data(as_text=True)
    assert html.count("<summary>114 學年度・第 1 學期</summary>") == 1
    with app.app_context():
        from app.models import AttendanceSummary
        assert AttendanceSummary.query.one().totals == {"曠課": 2, "事假": 0, "病假": 4}
        assert Portfolio.query.count() == 0
        assert SourceDocument.query.count() == 0


def test_pdf_import_and_invalid_file(tmp_path, monkeypatch):
    from app.services import attendance_import

    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    bad_pdf = {"file": (io.BytesIO(b"%PDF-invalid"), "damaged.pdf")}
    assert client.post(URL, data=bad_pdf).status_code == 400

    monkeypatch.setattr(attendance_import, "pdf_text", lambda data: PASTE)
    pdf = {"file": (io.BytesIO(b"%PDF-example"), "demo.pdf")}
    response = client.post(URL, data=pdf)
    assert response.status_code == 200
    assert 'name="曠課" value="2"' in response.get_data(as_text=True)
    assert not list(tmp_path.iterdir())


def test_import_does_not_guess_or_accept_non_student(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    assert client.get(URL).status_code == 401
    login(client)
    assert client.post(URL, data={"pasted_table": "逐日明細\n115/1/5 病假 2"}).status_code == 400
    assert client.post(URL + "/confirm", data={"school_year": "114", "semester": "3", "病假": "2"}).status_code == 400


def test_only_student_and_their_class_advisor_can_view_totals(tmp_path):
    from app.extensions import db
    from app.models import AttendanceSummary, AuditLog, ClassAdvisor, User

    app = records_app(tmp_path)
    client = app.test_client()
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        student.student_profile.class_name = "測試班"
        advisor, outsider, staff = [User(username=name, display_name=name, role=role, password_hash="unused")
                                   for name, role in (("advisor", "teacher"), ("outsider", "teacher"), ("office", "staff"))]
        db.session.add_all([advisor, outsider, staff])
        db.session.flush()
        db.session.add(ClassAdvisor(teacher_id=advisor.id, class_name="測試班", school_year=114))
        db.session.add(AttendanceSummary(student_id=student.id, school_year=114, semester=2, totals={"曠課": 4}))
        db.session.commit()
        student_id, advisor_id, outsider_id, staff_id = student.id, advisor.id, outsider.id, staff.id

    path = f"/teacher/students/{student_id}/attendance-records"
    for person_id in (student_id, outsider_id, staff_id):
        with client.session_transaction() as session:
            session.clear()
            session["user_id"] = person_id
        assert client.get(path).status_code == 403
    with client.session_transaction() as session:
        session.clear()
        session["user_id"] = advisor_id
    response = client.get(path)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "一般缺曠合計" in html and "實習、調補課及其他請假" in html
    assert "<td>" + "4" in "".join(html.split())
    assert response.headers["Cache-Control"] == "no-store"
    with app.app_context():
        event = AuditLog.query.filter_by(action="attendance.view").one()
        assert event.user_id == advisor_id and event.detail_json is None


SCHOOL_TABLE = "項目\t曠課\t遲到\t事假\t病假\t生理假\t心理假\t公假\t喪假\t產假\t婚假\t疫苗假"
SCHOOL_PASTE = (
    "學年期\t1141\t至\t1141\n"
    "該生本學期應上課1/3總時數為 90 節，至今缺課總時數為 7 節\n"
    f"{SCHOOL_TABLE}\n合計\t2\t0\t1\t\t0\t0\t0\t0\t0\t0\t0\n"
    "該生實習、調補課及其他請假：\n"
    f"{SCHOOL_TABLE}\n合計\t0\t0\t0\t4\t0\t0\t0\t0\t0\t0\t0"
)


def test_school_layout_keeps_the_two_tables_separate(tmp_path):
    from app.models import AttendanceSummary

    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    response = client.post(URL, data={"pasted_table": SCHOOL_PASTE})
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    for field, value in (("school_year", "114"), ("事假", "1"), ("病假", ""),
                         ("exception_病假", "4"), ("應上課 1/3 總時數", "90"), ("至今缺課總時數", "7")):
        assert f'name="{field}"' in html and f'name="{field}" value="{value}"' in html
    assert html.index("至今缺課總時數") < html.index("一般缺曠合計") < html.index("實習、調補課及其他請假")
    for data in ({"exception_病假": "4", "應上課 1/3 總時數": "90"},
                 {"病假": "0", "遲到": "1"}):
        response = client.post(URL + "/confirm", data={"school_year": "114", "semester": "1", **data})
        assert response.status_code == 302
    with app.app_context():
        assert AttendanceSummary.query.one().totals == {
            "exception_totals": {"病假": 4}, "應上課 1/3 總時數": 90, "病假": 0, "遲到": 1,
        }


def test_school_term_must_be_supplied_and_ranges_rejected_for_both_sources(tmp_path, monkeypatch):
    from app.services import attendance_import

    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    response = client.post(URL, data={"pasted_table": f"{SCHOOL_TABLE}\n合計\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0"})
    assert response.status_code == 200
    assert 'name="school_year" value=""' in response.get_data(as_text=True)
    across_terms = SCHOOL_PASTE.replace("至\t1141", "至\t1142")
    assert client.post(URL, data={"pasted_table": across_terms}).status_code == 400
    monkeypatch.setattr(attendance_import, "pdf_text", lambda data: across_terms)
    assert client.post(URL, data={"file": (io.BytesIO(b"%PDF-demo"), "demo.pdf")}).status_code == 400


def test_saved_attendance_queries_an_interior_term_or_range(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    for year, semester in ((112, 1), (113, 1), (113, 2), (114, 1)):
        assert client.post(URL + "/confirm", data={"school_year": str(year), "semester": str(semester), "曠課": "1"}).status_code == 302

    def labels(start, end):
        html = client.get(URL, query_string={"from_term": start, "to_term": end}).get_data(as_text=True)
        return [label for label in ("112 學年度・第 1 學期", "113 學年度・第 1 學期",
                                   "113 學年度・第 2 學期", "114 學年度・第 1 學期")
                if f"<summary>{label}</summary>" in html]

    assert labels("1131", "1132") == ["113 學年度・第 1 學期", "113 學年度・第 2 學期"]
    assert labels("1132", "1132") == ["113 學年度・第 2 學期"]
    assert labels("", "1131") == ["112 學年度・第 1 學期", "113 學年度・第 1 學期"]
    assert client.get(URL + "?from_term=1141&to_term=1132").status_code == 400


def test_daily_preview_preserves_periods_but_confirm_saves_totals_only(tmp_path):
    from app.models import AttendanceSummary

    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    details = "日期\t朝會\t一\t二\t三\n114/10/03\t朝會未到\t\t病假\t遲到"
    response = client.post(URL, data={"pasted_table": details + "\n" + SCHOOL_PASTE})
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "一學期內，若請假超過全學期上課總時數三分之一者，予以勒令休學辦理。" in html
    assert html.index("逐日缺曠明細") < html.index("一般缺曠合計")
    assert "<td>朝會未到</td><td></td><td>病假</td><td>遲到</td>" in html
    assert response.headers["Cache-Control"] == "no-store"
    assert "部分節次顯示原表假別" not in html
    assert 'name="遲到"' in html

    assert client.post(URL + "/confirm", data={"school_year": "114", "semester": "1", "病假": "1"}).status_code == 302
    assert "114/10/03" not in client.get(URL).get_data(as_text=True)
    with app.app_context():
        assert AttendanceSummary.query.one().totals == {"病假": 1}
        assert SourceDocument.query.count() == 0


def test_school_date_grid_can_be_previewed_without_saving_cross_term_totals(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    details = "日期\t朝會\t一\t二\n114/10/03\t\t\t病假"
    source = details + "\n" + SCHOOL_PASTE.replace("至\t1141", "至\t1142")
    response = client.post(URL, data={"pasted_table": source})
    html = response.get_data(as_text=True)
    assert response.status_code == 200 and "114/10/03" in html
    assert "/student/attendance-records/confirm" not in html
    assert "請在學校選擇單一學期" in html


def test_daily_preview_keeps_unknown_labels_and_warns_when_columns_do_not_match(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    source = (
        "日期\t朝會\t一\t二\n"
        "114/10/03\t朝會未到\t測試用假別\t病假\n"
        "114/10/04\t朝會未到\t\t病假\t遲到\n"
    ) + SCHOOL_PASTE
    response = client.post(URL, data={"pasted_table": source})
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "<td>朝會未到</td><td>測試用假別</td><td>病假</td>" in html
    assert "原表假別" in html
    assert "114/10/04" in html and "節次位置待核對" in html
    assert "/student/attendance-records/confirm" in html


def test_daily_calendar_validation_flags_invalid_date_and_disables_confirm(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    text = "日期\t朝會\t一\t二\n114/02/30\t\t病假\t\n113/02/29\t\t\t遲到\n項目\t病假\n合計\t1"

    response = client.post(URL, data={"pasted_table": text})
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "114/02/30" in html and "日期無效" in html
    assert "113/02/29" in html and "<td></td><td></td><td>遲到</td>" in html
    assert "/student/attendance-records/confirm" not in html


def test_multi_year_detail_without_source_term_can_only_be_previewed(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    text = "日期\t朝會\t一\t二\n113/09/04\t\t\t病假\n115/03/03\t\t遲到\t\n項目\t病假\t遲到\n合計\t1\t1"

    response = client.post(URL, data={"pasted_table": text})
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "113/09/04" in html and "115/03/03" in html
    assert "明細日期相隔至少一年" in html
    assert "/student/attendance-records/confirm" not in html

def test_attendance_preview_guides_review_and_confirmation(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    page = client.post(URL, data={'pasted_table': PASTE}).get_data(as_text=True)
    assert 'data-tour="核對學年期與缺曠合計，可直接修正。"' in page
    assert 'data-tour="核對完成後，確認並儲存學期合計。"' in page

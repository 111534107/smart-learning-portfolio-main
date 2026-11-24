"""實習履歷缺曠頁：讀截圖預填、總計取學校的累計值、缺曠資料不送外部。（僅為測試資料）"""
import io

from app.extensions import db
from app.models import AttendanceSummary, User
from app.services import absence_reader, attendance_import
from tests.test_autobiography import app, login  # noqa: F401

SAMPLE = """學年度: 113
學期: 2
曠課: 0
遲到: 1
事假: 0
病假: 4
生理假: 7
公假: 18
喪假: 20
至今缺課總時數: 11
"""


def test_rows_use_school_total_not_sum_of_rows():
    rows = attendance_import.parse_totals(SAMPLE)
    totals = {k: v for k, v in rows[0].items() if isinstance(v, int)}
    result = absence_reader.rows_from_totals(totals, "1132", overall=totals["至今缺課總時數"])
    assert result["rows"] == ["0節", "1節", "0節", "4節", "7節", "18節", "20節", "11節"]


def test_total_is_left_blank_when_school_total_missing():
    result = absence_reader.rows_from_totals({"曠課": 2, "病假": 3}, "1132")
    assert result["rows"][-1] == "" and result["rows"][0] == "2節"


def test_summary_table_reads_ocr_text_with_variant_characters():
    head = "學年期 1132 V 至 1141 V 該生本學期應上課1/3總時數為 162 節，至今缺課總時數為 11 節"
    labels = "项目 曠課 遅到 事假 病假 生理假 心理假 公假 丧假 產假 婚假 疫苗假"
    text = "\n".join([head, labels, "合計 0 1 0 4 7 0 18 20 0 0 0", "該生實習調補課及其他請假：", labels, "合計 0 0 0 0 0 0 0 0 0 0 0"])
    totals, overall, term = absence_reader.parse_summary_table(text)
    result = absence_reader.rows_from_totals(totals, term, overall)
    assert result["rows"] == ["0節", "1節", "0節", "4節", "7節", "18節", "20節", "11節"] and term == "1132至1141"


def test_summary_table_without_overall_number_keeps_total_blank():
    text = "\n".join(["至今缺課總時數為 節", "项目 曠課 遅到 事假 病假 生理假 心理假 公假 丧假", "合計 0 1 0 4 7 0 18 20"])
    totals, overall, _ = absence_reader.parse_summary_table(text)
    assert overall is None and absence_reader.rows_from_totals(totals, "", overall)["rows"][-1] == ""


def test_tokens_are_grouped_into_lines():
    tokens = [{"text": "曠課", "bbox": [10, 10, 40, 24]}, {"text": "0", "bbox": [200, 11, 210, 25]},
              {"text": "遲到", "bbox": [10, 40, 40, 54]}, {"text": "1", "bbox": [200, 41, 210, 55]}]
    assert absence_reader.tokens_to_text(tokens) == "曠課  0\n遲到  1"


def test_route_rejects_missing_file_and_bad_image(app):
    client = login(app)
    assert client.post("/student/internship-resume/absence/read").status_code == 400
    bad = client.post("/student/internship-resume/absence/read",
                      data={"file": (io.BytesIO(b"not an image"), "x.png")}, content_type="multipart/form-data")
    assert bad.status_code == 422 and bad.get_json()["error"]


def test_saved_records_are_summed_and_404_when_empty(app):
    client = login(app)
    assert client.get("/student/internship-resume/absence/saved").status_code == 404
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        db.session.add(AttendanceSummary(student_id=student.id, school_year=113, semester=1,
                                         totals={"曠課": 1, "遲到": 2, "至今缺課總時數": 3}))
        db.session.add(AttendanceSummary(student_id=student.id, school_year=113, semester=2,
                                         totals={"曠課": 0, "遲到": 1, "至今缺課總時數": 4}))
        db.session.commit()
    data = client.get("/student/internship-resume/absence/saved").get_json()
    assert data["rows"][0] == "1節" and data["rows"][1] == "3節" and data["rows"][-1] == "4節"
    assert data["source"] == "records"

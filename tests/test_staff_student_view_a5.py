"""科主任檢視全年級學生詳細資料、實習履歷與自傳意見測試（A5 規格）。

驗證項目：
1. 主任看得到學生實習履歷與自傳意見（建議修改狀態、段落註解）。
2. 科助或其他非主任人員無權存取（403 Forbidden）。
3. 主任查看學生詳細資料時確實寫入操作紀錄（AuditLog 包含實習履歷區塊）。
4. 全年級學生名單呈現「目標校系」與「自傳狀態」欄位。
"""

from app.extensions import db
from app.models import (
    AdmissionProgram,
    AuditLog,
    AutobiographyComment,
    AutobiographySuggestion,
    LearningProfileOutput,
    StudentProfile,
    StudentTarget,
    User,
)
from app.services import autobiography_service, internship_resume_draft
from tests.test_autobiography import app  # noqa: F401


def _setup_staff_and_student(app):
    with app.app_context():
        # 1. 建立科主任（job_title="主任"）
        chief = User(username="chief_a5", display_name="張主任", role="staff", job_title="主任", is_active=True)
        chief.set_password("pw")
        db.session.add(chief)

        # 2. 建立科助（非主任，job_title="科助"）
        assistant = User(username="asst_a5", display_name="李科助", role="staff", job_title="科助", is_active=True)
        assistant.set_password("pw")
        db.session.add(assistant)

        # 3. 建立學生
        student = User(username="stu_a5", display_name="林同學", role="student", is_active=True)
        student.set_password("pw")
        db.session.add(student)
        db.session.flush()
        db.session.add(StudentProfile(user_id=student.id, student_no="11054321", class_name="資管五乙", admission_year=111))

        # 4. 建立志願與目標
        prog = AdmissionProgram(
            school_name="國立臺北商業大學",
            department_name="資訊管理系",
            admission_year=115,
            program_code="DAY-NTUB-A5",
            status="published",
        )
        db.session.add(prog)
        db.session.flush()
        db.session.add(StudentTarget(student_id=student.id, rule_version_id=prog.id))

        # 5. 建立自傳與建議修改、段落註解
        out = LearningProfileOutput(
            student_id=student.id,
            output_type=autobiography_service.OUTPUT_TYPE,
            source_snapshot_json={},
            content_json={
                "program_id": prog.id,
                "version": 1,
                "paragraphs": [
                    {"title": "自傳主文", "text": "從小就對資訊管理充滿熱情。"}
                ]
            }
        )
        db.session.add(out)
        db.session.flush()

        sug = AutobiographySuggestion(
            student_id=student.id,
            program_id=prog.id,
            output_id=out.id,
            paragraph=0,
            start=0,
            end=2,
            original="從小",
            replacement="從專科一年級起",
            author_id=chief.id,
            status="pending"
        )
        db.session.add(sug)

        comm = AutobiographyComment(
            student_id=student.id,
            program_id=prog.id,
            output_id=out.id,
            paragraph=0,
            text="這句寫得很具體，繼續保持。",
            author_id=chief.id,
        )
        db.session.add(comm)

        # 6. 建立實習履歷草稿
        resume_out = LearningProfileOutput(
            student_id=student.id,
            output_type=internship_resume_draft.OUTPUT_TYPE,
            source_snapshot_json={},
            content_json={
                "period": "115年2月至6月",
                "email": "student@example.com",
                "phone": "0912345678",
                "choices": {
                    "texts": {
                        "family": "家境純樸，父母支持我的資訊專業學習。",
                        "study": "在校期間積極參與系統分析專題競賽。",
                        "skill": "熟悉 Python 與關聯式資料庫設計。",
                        "future": "希望能至大型軟體企業進行半年實務實習。"
                    }
                }
            }
        )
        db.session.add(resume_out)
        db.session.commit()
        return chief.id, assistant.id, student.id, prog.id


def test_chief_views_student_detail_with_internship_and_autobiography(app):
    """驗證主任看得到實習履歷與自傳意見，並成功寫入操作紀錄。"""
    chief_id, _, student_id, _ = _setup_staff_and_student(app)
    client = app.test_client()

    # 主任登入
    client.post("/staff/login", data={"username": "chief_a5", "password": "pw"})

    # 1. 從學生詳細頁前往「升學與備審」
    detail_url = f"/staff/students/{student_id}"
    admissions_url = f"{detail_url}/admissions"
    learning = client.get(detail_url)
    assert learning.status_code == 200
    learning_html = learning.get_data(as_text=True)
    assert f'href="{admissions_url}"' in learning_html
    assert "115年2月至6月" not in learning_html
    assert "這句寫得很具體" not in learning_html
    resp = client.get(admissions_url)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # 驗證包含實習履歷區塊及自傳四段
    assert "實習履歷" in html
    assert "115年2月至6月" in html
    assert "家境純樸" in html
    assert "積極參與系統分析專題" in html

    # 驗證自傳區塊及建議修改狀態
    assert "從專科一年級起" in html
    assert "待回覆" in html
    assert "這句寫得很具體" in html

    # 2. 驗證審計日誌 AuditLog 記錄了實習履歷區塊
    with app.app_context():
        log = AuditLog.query.filter_by(user_id=chief_id, action="staff.student_view").order_by(AuditLog.id.desc()).first()
        assert log is not None
        assert "實習履歷" in (log.detail_json or {}).get("sections", [])


def test_assistant_cannot_view_chief_pages_403(app):
    """驗證科助（非主任）存取全年級學生與詳細頁被拒絕（403 Forbidden）。"""
    _, asst_id, student_id, _ = _setup_staff_and_student(app)
    client = app.test_client()

    # 科助登入
    client.post("/staff/login", data={"username": "asst_a5", "password": "pw"})

    # 嘗試存取全年級學生清單
    list_resp = client.get("/staff/students")
    assert list_resp.status_code == 403

    # 嘗試存取學生詳細頁
    detail_resp = client.get(f"/staff/students/{student_id}")
    assert detail_resp.status_code == 403
    assert client.get(f"/staff/students/{student_id}/admissions").status_code == 403


def test_chief_students_list_displays_targets_and_bio_status(app):
    """驗證全年級名單包含目標校系與自傳狀態。"""
    _, _, student_id, _ = _setup_staff_and_student(app)
    client = app.test_client()

    # 主任登入
    client.post("/staff/login", data={"username": "chief_a5", "password": "pw"})

    resp = client.get("/staff/students")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # 檢查表格欄位名稱
    assert "目標校系" in html
    assert "自傳狀態" in html
    # 檢查學生列內容
    assert "國立臺北商業大學" in html
    assert "草稿中" in html or "已通過" in html or "待審閱" in html

"""各校備審白話建議（2026-11-20 使用者：中科大有規定的格式或建議，查到就放在目標校系，用淺顯的句子寫）。

建議只收簡章寫明的內容，每條附頁碼；目標校系清單和備審資料頁都看得到。
"""
from pathlib import Path

import pytest

from app.content.portfolio_tips import PORTFOLIO_TIPS, tips_for
from app.extensions import db
from app.models import AdmissionProgram, ClassAdvisor, StudentProfile, StudentTarget, User
from app.services.admission_service import import_seed_programs
from app.services.transfer_exam import import_transfer_programs
from tests.test_admission_agent import app, login  # noqa: F401  (app 是 fixture)

NIGHT_CODES = (
    "NIGHT-CSU-IM", "NIGHT-KSU-IM", "NIGHT-MUST-IM", "NIGHT-UCH-IM",
    "NIGHT-HDUT-CSIE", "NIGHT-CUST-HSH-CSIE", "NIGHT-CUST-TPE-IM", "NIGHT-JWU-ICOM",
)
WRITTEN_EXAMS = {"TRF-NCHU-CSIE-2": "A06", "TRF-CCU-IM-2": "B30", "TRF-CCU-IM-3": "D33"}
REMAINING_CODES = (*NIGHT_CODES, "TRF-NTU-CSIE-2", *WRITTEN_EXAMS)


def test_every_tip_has_source_page_and_url():
    for code, tips in PORTFOLIO_TIPS.items():
        assert tips["source_url"].startswith("https://"), code
        assert tips["summary"] and tips["tips"], code
        if code == "NIGHT-JWU-ICOM":
            assert "停止開班" in tips["notice"] and "71556" in tips["notice_url"]
        for tip in tips["tips"]:
            assert tip["text"].strip(), code
            assert tip["page"].startswith("第") and tip["page"].endswith("頁"), (code, tip)


def test_skill_brochure_tips_match_by_school_department_and_category():
    """聯招會技優甄審簡章整理的建議：校名、校區寫法不同也對得到；招生類別不同就不套用。"""
    ntub = AdmissionProgram(program_code="208003", school_name="國立臺北商業大學",
                            department_name="資訊管理系（臺北）", admission_category="管理類四")
    tips = tips_for(ntub)
    assert tips and tips["channel"] == "技優甄審"
    assert any("表A" in tip["text"] for tip in tips["tips"])
    chang_gung = AdmissionProgram(program_code="210009", school_name="長庚科技大學",
                                  department_name="護理系（林口）", admission_category="護理類一")
    assert tips_for(chang_gung)
    day = AdmissionProgram(program_code="DAY-X", school_name="國立臺北商業大學",
                           department_name="資訊管理系（臺北）", admission_category="日間部申請入學")
    assert tips_for(day) is None  # 日間部規定不同，不能套技優甄審的


def test_tips_for_unknown_program_is_none():
    assert tips_for(None) is None
    assert tips_for(AdmissionProgram(program_code="999999")) is None


def test_ntub_day_tips_are_specific_to_115():
    program = AdmissionProgram(
        program_code="DAY-NTUB-11507", admission_year=115,
        school_name="國立臺北商業大學", department_name="資訊管理系（臺北）",
        admission_category="日間部申請入學",
    )
    tips = tips_for(program)
    assert tips and tips["channel"] == "日間部申請入學"
    assert "115 學年度" in tips["source"]
    assert "書面審查占 75%" in tips["summary"] and "二技統測占 25%" in tips["summary"]
    statements = [tip["text"] for tip in tips["tips"] if tip["page"] == "第25頁"]
    assert any("表 A" in text and "表 B" in text for text in statements)
    assert any("50 MB" in text and "200 MB" in text for text in statements)
    program.admission_year = 116
    assert tips_for(program) is None


def test_yuntech_day_tips_are_specific_to_115():
    program = AdmissionProgram(
        program_code="DAY-YT-IM", admission_year=115, admission_category="日間部申請入學",
    )
    tips = tips_for(program)
    assert tips and tips["channel"] == "日間部申請入學"
    assert "書面審查占 70%" in tips["summary"] and "二技統測占 30%" in tips["summary"]
    statements = {page: " ".join(tip["text"] for tip in tips["tips"] if tip["page"] == page)
                  for page in ("第4頁", "第5頁", "第6頁")}
    assert "1 個 PDF" in statements["第4頁"] and "55 MB" in statements["第4頁"]
    assert "必交自傳和學習計畫書" in statements["第5頁"]
    assert "選交" in statements["第5頁"]
    assert statements["第6頁"].count("50%") == 2
    program.admission_year = 116
    assert tips_for(program) is None


@pytest.mark.parametrize("program_code,expected,page_number", [
    ("DAY-NTUB-11507", "自我推薦摘要表（表 A）", "第25頁"),
    ("DAY-YT-IM", "必交自傳和學習計畫書", "第5頁"),
])
def test_day_tips_show_on_targets_and_gap_page(app, program_code, expected, page_number):
    with app.app_context():
        seed = Path(__file__).resolve().parents[1] / "app/content/admission_demo_dayapply_115.csv"
        import_seed_programs(seed)
        program = AdmissionProgram.query.filter_by(program_code=program_code, admission_year=115).one()
        student = User.query.filter_by(username="stu").one()
        db.session.add(StudentTarget(student_id=student.id, rule_version_id=program.id))
        db.session.commit()
        program_id = program.id
    client = login(app, "stu")
    for path in ("/student/targets", f"/student/targets/{program_id}"):
        response = client.get(path)
        assert response.status_code == 200
        page = response.get_data(as_text=True)
        assert f'id="portfolio-tips-{program_id}"' in page
        assert expected in page
        assert page_number in page


def test_nutc_tips_show_on_targets_and_gap_page(app):
    with app.app_context():
        program = AdmissionProgram.query.filter_by(program_code="208001", data_origin="manual").one()
        student = User.query.filter_by(username="stu").one()
        db.session.add(StudentTarget(student_id=student.id, rule_version_id=program.id))
        db.session.commit()
        program_id = program.id
    client = login(app, "stu")
    targets = client.get("/student/targets").get_data(as_text=True)
    assert "data-portfolio-tips" in targets and "這所學校的備審，簡章這樣說" in targets
    gap = client.get(f"/student/targets/{program_id}").get_data(as_text=True)
    assert "data-portfolio-tips" in gap
    assert "同分時先比" in gap and "（第64頁）" in gap


@pytest.mark.parametrize("code", REMAINING_CODES)
def test_remaining_tips_match_only_115(code):
    program = AdmissionProgram(program_code=code, admission_year=115)
    tips = tips_for(program)
    assert tips and tips["admission_year"] == 115
    if code in WRITTEN_EXAMS:
        assert tips["heading"] == "筆試準備"
        assert WRITTEN_EXAMS[code] in tips["summary"]
        assert all("自傳" not in item["text"] for item in tips["tips"])
    program.admission_year = 116
    assert tips_for(program) is None


def test_remaining_tips_show_on_student_and_teacher_pages(app):
    with app.app_context():
        seed = Path(__file__).resolve().parents[1] / "app/content/admission_demo_night_private_115.csv"
        import_seed_programs(seed)
        import_transfer_programs()
        student = User.query.filter_by(username="stu").one()
        teacher = User(username="tips-teacher", role="teacher", display_name="測試導師")
        teacher.set_password("pw")
        db.session.add(teacher)
        db.session.flush()
        db.session.add(StudentProfile(user_id=student.id, student_no="TIP001", class_name="測試班", admission_year=113))
        db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name="測試班", school_year=115))
        programs = AdmissionProgram.query.filter(AdmissionProgram.program_code.in_(REMAINING_CODES)).all()
        assert len(programs) == len(REMAINING_CODES)
        ids = {program.program_code: program.id for program in programs}
        for program in programs:
            if program.program_code in WRITTEN_EXAMS:
                assert not program.items
            db.session.add(StudentTarget(student_id=student.id, rule_version_id=program.id))
        student_id = student.id
        db.session.commit()

    student = login(app, "stu")
    teacher = app.test_client()
    teacher.post("/staff/login", data={"username": "tips-teacher", "password": "pw"})
    staff_page = teacher.get(f"/teacher/students/{student_id}")
    assert staff_page.status_code == 200
    teacher_html = staff_page.get_data(as_text=True)
    for code, program_id in ids.items():
        track = "twotech" if code in NIGHT_CODES else "transfer"
        targets = student.get(f"/student/targets?track={track}&program_id={program_id}")
        detail = student.get(f"/student/targets/{program_id}")
        assert targets.status_code == detail.status_code == 200
        heading = "筆試準備" if code in WRITTEN_EXAMS else "這所學校的備審，簡章這樣說"
        marker = f'id="portfolio-tips-{program_id}">{heading}</h3>'
        for html in (targets.get_data(as_text=True), detail.get_data(as_text=True), teacher_html):
            assert marker in html, code
            if code == "NIGHT-JWU-ICOM":
                assert "115 學年度資訊與通訊系進修部二技已公告停止開班" in html
                assert "查看停止開班公告" in html

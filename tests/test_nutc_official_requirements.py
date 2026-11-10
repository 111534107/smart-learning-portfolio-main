"""中科大資管系、資訊應用菁英班依 115 學年度二技技優甄審簡章第 64 頁核對（2026-11-10）。"""
import io

from docx import Document

from app import create_app
from app.extensions import db
from app.models import AdmissionProgram, StudentProfile, User
from app.services.admission_service import import_seed_programs, refresh_seed_details
from app.services.gap_service import analyze_gap
from app.services.package_service import build_package_docx

URL = "https://admission.nutc.edu.tw/var/file/16/1016/img/3572/397031185.pdf"


def make_app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "WTF_CSRF_ENABLED": False, "TWO_FACTOR_REQUIRED": False})
    with app.app_context():
        db.create_all()
    return app


def items_of(code):
    program = AdmissionProgram.query.filter_by(program_code=code).one()
    return program, {item.source_item_name: item for item in program.items}


def test_seed_matches_official_brochure():
    app = make_app()
    with app.app_context():
        import_seed_programs()
        for code, weights in (("208001", (30, 50, 20)), ("208002", (25, 50, 25))):
            program, items = items_of(code)
            assert program.source_url == URL and "第64頁" in program.source_note
            assert [items[name].weight_percent for name in ("歷年成績", "個人特質與專業技能", "其他")] == list(weights)
            assert all(item.mapping_status == "confirmed" for item in items.values())
            assert "簡歷自傳讀書計畫" in items["個人特質與專業技能"].requirement
            # 簡章把競賽成果寫在「其他有助於審查之資料」
            assert "competition" in items["其他"].category_keys
            assert "competition" not in items["個人特質與專業技能"].category_keys
        # 沒核對過的學校不受影響
        other, other_items = items_of("208003")
        assert other.source_url is None and other_items["專業成果"].mapping_status == "pending"


def test_refresh_upgrades_existing_pending_items_but_keeps_admin_choices():
    app = make_app()
    with app.app_context():
        import_seed_programs()
        program, items = items_of("208002")
        program.source_url = None
        items["個人特質與專業技能"].requirement = None
        items["個人特質與專業技能"].mapping_status = "pending"
        items["個人特質與專業技能"].mapped_categories = "credential,competition"
        items["其他"].mapped_categories = "activity"  # 管理員已標確定的項目不覆蓋
        db.session.commit()
        assert refresh_seed_details() == 1
        program, items = items_of("208002")
        assert program.source_url == URL
        assert items["個人特質與專業技能"].mapping_status == "confirmed"
        assert "competition" not in items["個人特質與專業技能"].category_keys
        assert items["其他"].mapped_categories == "activity"
        assert refresh_seed_details() == 0  # 再按一次不會重複更新


def test_student_sees_requirement_and_word_lists_it():
    app = make_app()
    with app.app_context():
        import_seed_programs()
        student = User(username="stu", display_name="合成學生", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.flush()
        db.session.add(StudentProfile(user_id=student.id, student_no="111000001", class_name="資五甲", admission_year=111))
        db.session.commit()
        program, _ = items_of("208002")
        gap = analyze_gap(student, program)
        assert any("簡歷自傳讀書計畫" in (item["requirement"] or "") for item in gap["items"])
        text = "\n".join(p.text for p in Document(io.BytesIO(build_package_docx(student, program).read())).paragraphs)
        assert "簡章要求" in text and "其他（25%）：其他有助於審查之資料" in text and URL in text


def test_admin_import_button_reports_updates():
    app = make_app()
    with app.app_context():
        admin = User(username="admin", display_name="合成管理員", role="admin")
        admin.set_password("pw")
        db.session.add(admin)
        db.session.commit()
        import_seed_programs()
        _, items = items_of("208001")
        items["其他"].mapping_status = "pending"
        db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": "admin", "password": "pw"})
    response = client.post("/admin/programs/import-seed", follow_redirects=True)
    assert "依核對過的簡章更新 1 個項目" in response.get_data(as_text=True)

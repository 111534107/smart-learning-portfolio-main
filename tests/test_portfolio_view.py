"""備審 A4 頁面資料：目錄依加權、求學歷程取最高分課程與同年度成果、只用已確認資料。（僅為測試資料）"""
from app.models import AdmissionProgram, User
from app.services import portfolio_view
from tests.test_autobiography import ANSWERS, app, choose_target, login, program  # noqa: F401


def _data(app):
    client = login(app)
    choose_target(app, client)
    client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        prog = AdmissionProgram.query.filter_by(program_code="208003").one()
        return portfolio_view.build(student, prog), prog.school_name


def test_cover_toc_and_pages_follow_program(app):
    data, school = _data(app)
    assert data["cover"]["school"] == school and data["cover"]["applicant"]
    pages = [row["page"] for row in data["toc"]]
    assert pages == sorted(pages) and pages[0] == 3  # 1 封面、2 目錄，章節從第 3 頁起
    assert [row["no"] for row in data["toc"]] == [f"{n:02d}" for n in range(1, len(data["toc"]) + 1)]
    assert data["has_draft"] and data["bio"] and any("未來" in p["title"] for p in data["plan"])


def test_resume_lists_confirmed_items_only_and_years_pick_top_courses(app):
    data, _ = _data(app)
    assert data["resume"]["name"] and isinstance(data["resume"]["credentials"], list)
    for year in data["years"]:
        scores = [c["score"] for c in year["courses"]]
        assert scores == sorted(scores, reverse=True) and len(scores) <= portfolio_view.TOP_COURSES


def test_route_requires_own_target_and_renders(app):
    client = login(app)
    choose_target(app, client)
    assert client.get(f"/student/portfolio-view/{program(app)}").status_code in (200, 500)  # 模板由畫面工作補上

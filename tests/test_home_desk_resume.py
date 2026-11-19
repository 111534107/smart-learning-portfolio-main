"""學生首頁「散落的紙張」與專四上學期的實習履歷（2026-11-17）。

- 第一屏是散落的紙：一筆資料一張，位置固定（重新整理不亂跳），最多 24 張。
- 專四起首頁多一個按鈕；專三以前只看到一行預告，直接開網址也只看到說明。
- 實習履歷用學校格式檔填字：只填學生勾選的資料，沒勾的不會出現；不呼叫 AI。
"""
from datetime import date
from io import BytesIO

import pytest
from docx import Document

from app import create_app
from app.extensions import db
from app.models import AuditLog, ClassAdvisor, CredentialRecord, Portfolio, StudentProfile, User
from app.services import internship_resume as resume
from app.services.journey_home import SHEET_LIMIT, journey_home
from app.services.journey_service import academic_year_of, build_journey


def _make_app(grade):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        user = User(username="stu", display_name="測試生", role="student", email="stu@example.test")
        user.set_password("pw")
        db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=user.id, student_no="s1",
                                      admission_year=academic_year_of(date.today()) - (grade - 1)))
        db.session.add(AuditLog(user_id=user.id, action="student.welcome_done"))
        db.session.add(Portfolio(student_id=user.id, title="資訊社社課", category="activity", school_year=2,
                                 description="每週三社課", status="confirmed"))
        db.session.add(Portfolio(student_id=user.id, title="校內程式競賽佳作", category="competition", school_year=3, status="confirmed"))
        db.session.add(Portfolio(student_id=user.id, title="不想放的志工", category="service", school_year=1, status="confirmed"))
        db.session.add(CredentialRecord(student_id=user.id, credential_name="電腦軟體應用", level="丙級", issue_date=date.today()))
        db.session.add(CredentialRecord(student_id=user.id, credential_name="ITS Python", issue_date=date.today()))
        db.session.commit()
    return app


@pytest.fixture()
def app():  # 專四：有實習履歷按鈕
    yield _make_app(4)


def _login(app):
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    return client


def _user():
    return User.query.filter_by(username="stu").one()


def test_current_advisor_sees_only_the_last_saved_or_downloaded_resume(app):
    with app.app_context():
        student = _user()
        student.student_profile.class_name = "實習測試班"
        sid = student.id
        for username, year in (("advisor", academic_year_of(date.today())), ("old", academic_year_of(date.today()) - 1)):
            teacher = User(username=username, display_name=username, role="teacher")
            teacher.set_password("pw")
            db.session.add(teacher)
            db.session.flush()
            db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name="實習測試班", school_year=year))
        db.session.commit()

    def teacher_client(username):
        client = app.test_client()
        client.post("/staff/login", data={"username": username, "password": "pw"})
        return client

    student = _login(app)
    advisor = teacher_client("advisor")
    read_url = f"/teacher/students/{sid}/internship-resume"
    assert "實習履歷" in advisor.get(f"/teacher/students/{sid}").get_data(as_text=True)
    assert "尚未儲存或下載" in advisor.get(read_url).get_data(as_text=True)
    assert teacher_client("old").get(read_url).status_code == 403
    assert advisor.post(read_url).status_code == 405
    with app.app_context():
        chosen = Portfolio.query.filter_by(title="資訊社社課").one().id
    form_url = "/student/internship-resume"
    saved = student.post(form_url, data={"action": "save", "text_study": "第一份合成履歷",
                                        "exp": f"portfolio-{chosen}"}, follow_redirects=True)
    assert "第一份合成履歷" in saved.get_data(as_text=True)
    page = advisor.get(read_url).get_data(as_text=True)
    assert "第一份合成履歷" in page and "資訊社社課" in page and "不想放的志工" not in page
    exported = student.post(form_url, data={"text_study": "第二份合成履歷"})
    assert exported.status_code == 200 and ".docx" in exported.headers["Content-Disposition"]
    page = advisor.get(read_url).get_data(as_text=True)
    assert "第二份合成履歷" in page and "第一份合成履歷" not in page


# ---------- 散落的紙 ----------

def test_desk_has_one_sheet_per_record_and_positions_are_stable(app):
    with app.test_request_context():
        first = journey_home(_user())["desk"]
        second = journey_home(_user())["desk"]
    assert first["count"] == 5 and len(first["sheets"]) == 5 and first["more"] == 0
    assert [(s["id"], s["x"], s["y"], s["turn"]) for s in first["sheets"]] == \
           [(s["id"], s["x"], s["y"], s["turn"]) for s in second["sheets"]]
    for sheet in first["sheets"]:
        assert 0 < sheet["x"] < 100 and 0 < sheet["y"] < 100 and 0 < sheet["mx"] < 100
    assert {s["title"] for s in first["sheets"]} >= {"資訊社社課", "電腦軟體應用"}
    assert next(s for s in first["sheets"] if s["title"] == "資訊社社課")["detail"] == "每週三社課"


def test_desk_shows_at_most_the_limit_and_says_how_many_more(app):
    with app.test_request_context():
        user = _user()
        for n in range(SHEET_LIMIT + 3):
            db.session.add(Portfolio(student_id=user.id, title=f"活動{n}", category="activity", school_year=4))
        db.session.commit()
        desk = journey_home(user)["desk"]
    assert len(desk["sheets"]) == SHEET_LIMIT
    assert desk["more"] == desk["count"] - SHEET_LIMIT == 8


def test_home_page_shows_sheets_dialog_and_bottom_route(app):
    page = _login(app).get("/student/dashboard").get_data(as_text=True)
    assert page.count('data-sheet="') == 5
    assert 'class="desk__me"' in page  # 中間站一個小人（舊版設計示範）
    assert "data-sheet-doc" in page and 'data-title="資訊社社課"' in page
    assert "js/home-desk.js" in page and "css/student-v2/home-desk.css" in page
    # 紙張在最上面，「今天先完成哪一步」縮在紙張下面，五年路線在最底下
    assert page.index("data-desk ") < page.index('id="today-title"') < page.index('class="route-map"') < page.index('id="folders"')
    assert "學校專四的規劃：上學期交實習申請，下學期去實習" in page


def test_sheet_titles_are_escaped(app):
    with app.app_context():
        db.session.add(Portfolio(student_id=_user().id, title='<img src=x onerror=alert(1)>', category="activity", school_year=4))
        db.session.commit()
    page = _login(app).get("/student/dashboard").get_data(as_text=True)
    assert "<img src=x" not in page and "&lt;img src=x" in page


# ---------- 專四上學期的按鈕 ----------

def test_resume_button_only_from_grade_four(app):
    page = _login(app).get("/student/dashboard").get_data(as_text=True)
    assert 'href="/student/internship-resume" data-stage-go>產生學校格式的實習履歷</a>' in page
    assert "data-resume-later" not in page

    younger = _make_app(3)
    client = _login(younger)
    page = client.get("/student/dashboard").get_data(as_text=True)
    assert 'href="/student/internship-resume"' not in page and "data-resume-later" in page
    locked = client.get("/student/internship-resume").get_data(as_text=True)
    assert "專四上學期才會用到實習履歷" in locked and "data-resume-form" not in locked
    # 專三直接送表單也不會產生檔案
    response = client.post("/student/internship-resume", data={})
    assert response.mimetype == "text/html"


def test_resume_page_lists_my_records_with_school_sections(app):
    page = _login(app).get("/student/internship-resume").get_data(as_text=True)
    for title in ("家庭生活", "求學經過、社團活動", "個人專長、簡要經歷", "未來生涯規劃"):
        assert title in page
    assert page.count('name="cred"') == 2 and page.count('name="exp"') == 3
    assert "系統不會替你寫" in page  # 沒有自傳時不自動產生內容
    assert "缺曠記錄" in page  # 說明哪些要自己補


def test_credentials_are_sorted_into_the_school_columns(app):
    with app.app_context():
        options = resume.build_options(_user(), build_journey(_user()))
    columns = {item["name"]: item["column"] for item in options["credentials"]}
    assert columns == {"電腦軟體應用 丙級": "labor", "ITS Python": "international"}


# ---------- 下載 Word ----------

def _all_text(document):
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


def test_download_fills_the_school_template_with_only_what_was_picked(app):
    client = _login(app)
    with app.app_context():
        user = _user()
        creds = {c.credential_name: c.id for c in CredentialRecord.query.filter_by(student_id=user.id)}
        records = {p.title: f"portfolio-{p.id}" for p in Portfolio.query.filter_by(student_id=user.id)}
    response = client.post("/student/internship-resume", data={
        "cred": [str(creds["電腦軟體應用"]), str(creds["ITS Python"])],
        f"col_{creds['ITS Python']}": "domestic",  # 學生把欄位改成國內證照
        "exp": [records["資訊社社課"], records["校內程式競賽佳作"]],  # 「不想放的志工」沒勾
        "text_family": "家裡有四個人。",
        "text_future": "想先到企業實習。",
    })
    assert response.status_code == 200
    assert "wordprocessingml" in response.mimetype
    assert "attachment" in response.headers["Content-Disposition"]

    document = Document(BytesIO(response.data))
    text = _all_text(document)
    # 學校格式原本的字都還在（只填字、不改版面）
    for fixed in ("實習生履歷表", "已修習專業核心科目", "勞動部", "語文能力", "缺曠記錄", "生理假"):
        assert fixed in text
    assert len(document.tables) == 5 and len(document.tables[0].rows) == 25
    # 填進去的
    assert "學號：s1" in text and "測試生" in text and "stu@example.test" in text
    assert "【家庭生活】" in text and "家裡有四個人。" in text and "想先到企業實習。" in text
    assert "專二活動：資訊社社課" in text and "專三競賽：校內程式競賽佳作" in text
    assert "證照名稱：電腦軟體應用 丙級" in text
    # 沒勾的不會出現
    assert "不想放的志工" not in text
    # 證照欄位：丙級在勞動部欄，ITS 依學生的選擇放在國內證照欄
    sheet = document.tables[0]
    header = next(i for i, row in enumerate(sheet.rows) if row.cells[0].text.strip() == "勞動部")
    cells = resume._unique_cells(sheet.rows[header + 1])
    assert [cell.text.strip() for cell in cells] == ["電腦軟體應用 丙級", "", "ITS Python", ""]
    with app.app_context():
        assert AuditLog.query.filter_by(action="student.internship_resume_docx").count() == 1


def test_download_ignores_other_students_records_and_keeps_placeholder_when_empty(app):
    with app.app_context():
        other = User(username="other", display_name="別人", role="student")
        other.set_password("pw")
        db.session.add(other)
        db.session.flush()
        secret = Portfolio(student_id=other.id, title="別人的活動", category="activity", school_year=2)
        db.session.add(secret)
        db.session.commit()
        secret_id = f"portfolio-{secret.id}"
    response = _login(app).post("/student/internship-resume", data={"exp": [secret_id]})
    document = Document(BytesIO(response.data))
    text = _all_text(document)
    assert "別人的活動" not in text
    assert document.tables[1].rows[0].cells[0].text.strip() == "自傳"  # 什麼都沒選：自傳格維持學校原樣


def test_resume_prefills_my_latest_autobiography_but_never_calls_ai(app, monkeypatch):
    from app.models import LearningProfileOutput
    from app.services import autobiography_service
    monkeypatch.setattr(autobiography_service, "generate_draft",
                        lambda *args, **kwargs: pytest.fail("實習履歷不應該呼叫 AI"))
    with app.app_context():
        db.session.add(LearningProfileOutput(
            student_id=_user().id, output_type=autobiography_service.OUTPUT_TYPE,
            content_json={"program_id": 1, "version": 2, "paragraphs": [{"title": "", "text": "我在專二加入資訊社。"}]},
            source_snapshot_json={}))
        db.session.commit()
    page = _login(app).get("/student/internship-resume").get_data(as_text=True)
    assert "我在專二加入資訊社。" in page and "自傳第 2 版" in page


def test_teacher_cannot_open_the_resume_page(app):
    with app.app_context():
        teacher = User(username="t1", display_name="老師", role="teacher")
        teacher.set_password("pw")
        db.session.add(teacher)
        db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": "t1", "password": "pw"})
    assert client.get("/student/internship-resume").status_code == 403


def test_resume_excludes_draft_records_from_options_and_download(app):
    with app.app_context():
        user = _user()
        credential = CredentialRecord(student_id=user.id, credential_name="草稿證照不得引用", confirmation_status="draft")
        record = Portfolio(student_id=user.id, title="草稿經歷不得引用", category="activity", school_year=4, status="draft")
        db.session.add_all([credential, record]); db.session.commit()
        cid, rid = credential.id, record.id
    client = _login(app)
    page = client.get("/student/internship-resume").get_data(as_text=True)
    assert "草稿證照不得引用" not in page
    assert "草稿經歷不得引用" not in page
    response = client.post("/student/internship-resume", data={"cred": [str(cid)], "exp": [f"portfolio-{rid}"]})
    text = _all_text(Document(BytesIO(response.data)))
    assert "草稿證照不得引用" not in text and "草稿經歷不得引用" not in text


def test_resume_does_not_export_old_template_internship_dates(app):
    response = _login(app).post("/student/internship-resume", data={})
    text = _all_text(Document(BytesIO(response.data)))
    assert "113年2月19日至6月21日" not in text
    assert "1112至1121" not in text
    assert "實習期間：" in text


def _core_cells(document):
    """格式檔核心科目區：{科目名稱: 學分格文字}（被刪掉的科目不會出現）。"""
    out = {}
    for row in document.tables[0].rows[5:15]:
        cells = resume._unique_cells(row)
        for pair in range(3):
            name = cells[2 * pair].text.strip()
            if name:
                out[name] = cells[2 * pair + 1].text.strip()
    return out


def test_core_courses_follow_the_school_fill_in_rules(app):
    """照資管科「實習申請表填寫說明」第 2 點：及格填學分、不及格整科刪掉、只有一學期及格算不及格；
    系統沒有成績的學分留白讓學生核對，表頭不改。"""
    from app.models import LearningCourseRecord
    with app.app_context():
        uid = _user().id
        def add(name, score):
            db.session.add(LearningCourseRecord(student_id=uid, course_name=name, normalized_course_name=name, score=score, credits=3))
        add("程式設計", 80); add("程式設計", 75)          # 上下學期都及格 → 填學分 3/3
        add("會計學", 70); add("會計學", 40)              # 只有一學期及格 → 視同不及格，刪掉
        add("資料結構", 90)                               # 一學期的課及格 → 填 3
        db.session.commit()
    client = _login(app)
    page = client.get("/student/internship-resume").get_data(as_text=True)
    assert "及格，填學分 2 科" in page and "不及格，會刪掉 1 科" in page
    assert 'href="https://im.ukn.edu.tw/p/405-1028-2626,c1193.php?Lang=zh-tw"' in page
    document = Document(BytesIO(client.post("/student/internship-resume", data={}).data))
    cells = _core_cells(document)
    assert cells["程式設計"] == "3/3" and cells["資料結構"] == "3"
    assert "會計學" not in cells           # 不及格：整科刪掉
    assert cells["管理學"] == ""             # 系統沒有成績：學分留白
    assert "已修習專業核心科目" in _all_text(document) and "學校預列" not in _all_text(document)


def test_no_department_banner_anywhere_on_home(app):
    """使用者看過後決定橫幅拿掉（2026-11-17）：首頁和拼圖畫面都不放。"""
    page = _login(app).get("/student/dashboard").get_data(as_text=True)
    assert "banner-strip" not in page and "im-banner" not in page


def test_sheets_grow_with_content_and_thick_stacks_for_many_courses(app):
    """舊版紙張：寫得越多越大張（--p 1～6），成績門數多的疊成一疊，有說明的有小圓點。"""
    from app.models import LearningCourseRecord
    with app.test_request_context():
        user = _user()
        for n in range(14):
            db.session.add(LearningCourseRecord(student_id=user.id, course_name=f"課{n}", normalized_course_name=f"課{n}", school_year=2, credits=2, score=80))
        db.session.commit()
        sheets = {s["title"]: s for s in journey_home(user)["desk"]["sheets"]}
    grades = next(s for t, s in sheets.items() if "成績" in t)
    assert grades["pages"] == 5 and grades["thick"]
    assert sheets["資訊社社課"]["note"] and not sheets["資訊社社課"]["thick"]
    assert sheets["校內程式競賽佳作"]["pages"] == 1 and not sheets["校內程式競賽佳作"]["note"]
    # 手機格子避開中間四格（小人站的地方）
    from app.services.journey_home import PHONE_CELLS
    assert not {9, 10, 13, 14} & set(PHONE_CELLS)


def test_route_is_irregular_and_carries_the_school_plan(app):
    """數線圖：彎來彎去的路，每一站插著學校那一年的規劃（出自 113 年度入學修業科目表）。"""
    page = _login(app).get("/student/dashboard").get_data(as_text=True)
    assert page.count('class="route-note ') == 5
    for text in ("學校專一的規劃", "打基本功：程式、會計、管理", "可以考：硬體裝修丙級、軟體應用丙級",
                 "上學期交實習申請，下學期去實習", "做實務專題，準備二技備審"):
        assert text in page
    assert "資管科修業科目表（113 年度入學）" in page
    assert page.count('class="route-list__plan"') == 5  # 手機直式列表也有
    # 專四的學生：走過的路畫到第四站，預設小人物停在專四
    walked = page.split('class="route-map__walked" d="', 1)[1].split('"', 1)[0]
    assert walked.count("C") == 5 and walked.startswith("M100 280")
    assert 'data-walker data-grade="4" transform="translate(700 116)"' in page


def test_school_plan_and_resume_format_link_to_the_school_originals(app):
    """依學校文件寫的東西都要附原檔連結（使用者 2026-11-17 要求）。"""
    client = _login(app)
    page = client.get("/student/dashboard").get_data(as_text=True)
    subject_list = 'href="https://im.ukn.edu.tw/p/405-1028-609,c82-1.php"'
    assert page.count(subject_list) == 6  # 路線下方一次＋五個年級的規劃各一次
    assert page.count('href="https://im.ukn.edu.tw/p/405-1028-2626,c1193.php?Lang=zh-tw"') == 2  # 路線下方＋專四
    resume_page = client.get("/student/internship-resume").get_data(as_text=True)
    assert 'href="https://im.ukn.edu.tw/p/405-1028-7223,c1193.php?Lang=zh-tw"' in resume_page

def test_desk_shows_both_actions_at_each_grade(app):
    for grade in (3, 4, 5):
        use_app = app if grade == 4 else _make_app(grade)
        page = _login(use_app).get("/student/dashboard").get_data(as_text=True)
        actions = page.split('class="desk-actions"', 1)[1].split('<nav class="maker-row"', 1)[0]
        assert "產生學校格式的實習履歷" in actions
        assert "拼好拼圖、生成自傳" in actions
        assert ('href="/student/internship-resume"' in actions) == (grade >= 4)
        assert ('href="/student/autobiography"' in actions) == (grade >= 5)
        if grade < 5:
            assert "專五開放生成自傳" in actions
        if grade < 4:
            assert "專四上學期開放" in actions


def test_dashboard_discloses_locked_actions_and_initially_hides_reset():
    page = _login(_make_app(3)).get("/student/dashboard").get_data(as_text=True)
    assert page.count('aria-disabled="true" aria-describedby="desk-') == 2
    assert page.count('class="desk-action-tip" role="tooltip"') == 2
    assert 'data-desk-owner="' in page
    assert 'data-desk-reset hidden' in page
    assert 'class="route-legend"' in page

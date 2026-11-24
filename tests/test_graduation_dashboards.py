"""導師首頁 A 版、導師學生頁、科辦待核對。（僅為測試資料）"""
from datetime import date

from app.extensions import db
from app.models import (ClassAdvisor, GraduationCase, GraduationCaseEvent, Notification,
                        StudentProfile, User)
from app.services import graduation_case_service as svc
from app.services import graduation_check_service as check
from tests.test_graduation_case_pages import as_user, make_case, pages_app

TODAY = date(2026, 3, 1)


def _student(username, name, no, grade_year=111, class_name="五專四甲"):
    user = User(username=username, display_name=name, role="student")
    user.set_password("pw")
    db.session.add(user)
    db.session.flush()
    db.session.add(StudentProfile(user_id=user.id, student_no=no, admission_year=grade_year,
                                  class_name=class_name))
    db.session.flush()
    return user


def _case(student, item, case_type, amount=None, status="pending"):
    case = GraduationCase(student_id=student.id, case_type=case_type, item=item, status=status,
                          initial_amount=amount, current_amount=amount, unit="學分",
                          open_key=GraduationCase.open_key_for(student.id, item, case_type))
    db.session.add(case)
    db.session.flush()
    return case


def _fake_assess(table):
    """table: 學生 id -> (四項結果, 年級)。"""
    def fake(student, today=None, curriculum=None):
        results, grade = table[student.id]
        return {"stage": {"grade": grade, "formal": True},
                "items": {name: {"result": results.get(name, "progress")} for name in check.ITEMS}}
    return fake


ALL_MET = {name: "met" for name in check.ITEMS}


def _setup(monkeypatch, tmp_path, spec):
    """spec: [(帳號, 姓名, 結果表, 年級, 案件清單)]；回傳 (app, {帳號: id})。"""
    app = pages_app(tmp_path)
    ids, table = {}, {}
    with app.app_context():
        for index, (username, name, results, grade, cases) in enumerate(spec):
            student = _student(username, name, f"9990{index}")
            ids[username] = student.id
            table[student.id] = (results, grade)
            for item, case_type, amount, *rest in cases:
                case = _case(student, item, case_type, amount, *rest[:1])
                if len(rest) > 1:
                    case.last_result = rest[1]
        db.session.commit()
    monkeypatch.setattr(check, "assess", _fake_assess(table))
    return app, ids


def _overview(app, ids):
    with app.app_context():
        students = [db.session.get(User, i) for i in ids.values()]
        return svc.class_overview(students, today=TODAY)


BASIC = [
    ("m1", "達標生", ALL_MET, 5, []),
    ("g1", "缺口生", {"certificates": "gap"}, 5, [("certificates", "gap", 2)]),
    ("d1", "待確認生", {"certificates": "insufficient_data"}, 5, [("certificates", "data_needed", None)]),
    ("p1", "修課生", {}, 3, []),
]


def test_class_overview_counts(monkeypatch, tmp_path):
    app, ids = _setup(monkeypatch, tmp_path, BASIC)
    overview = _overview(app, ids)
    assert (overview["total"], overview["met"], overview["gap"], overview["data"], overview["other"]) == (4, 1, 1, 1, 1)


def test_priority_excludes_inquiry(monkeypatch, tmp_path):
    spec = BASIC + [("i1", "詢問生", {}, 5, [("general", "inquiry", None)])]
    app, ids = _setup(monkeypatch, tmp_path, spec)
    overview = _overview(app, ids)
    assert {row["case"].case_type for row in overview["priority"]} == {"gap", "data_needed"}
    assert overview["other"] == 2


def test_priority_order(monkeypatch, tmp_path):
    spec = [
        ("d1", "資料生", {}, 5, [("certificates", "data_needed", None)]),
        ("r1", "必修生", {}, 5, [("required_credits", "gap", 9)]),
        ("c1", "證照生", {}, 5, [("certificates", "gap", 1)]),
        ("r2", "必修高年級小缺口", {}, 5, [("required_credits", "gap", 3)]),
        ("r3", "必修低年級", {}, 4, [("required_credits", "gap", 30)]),
    ]
    app, ids = _setup(monkeypatch, tmp_path, spec)
    names = [row["student"].display_name for row in _overview(app, ids)["priority"]]
    assert names == ["證照生", "必修生", "必修高年級小缺口", "必修低年級", "資料生"]


def test_awaiting_case_not_counted_as_gap_and_ranks_last(monkeypatch, tmp_path):
    spec = [
        ("w1", "待核對生", {"certificates": "met"}, 5,
         [("certificates", "gap", 1, "awaiting_verification", "met")]),
        ("d1", "資料生", {}, 5, [("certificates", "data_needed", None)]),
        ("g1", "缺口生", {"certificates": "gap"}, 5, [("certificates", "gap", 2)]),
    ]
    app, ids = _setup(monkeypatch, tmp_path, spec)
    overview = _overview(app, ids)
    assert overview["gap"] == 1 and overview["other"] == 1
    rows = overview["priority"]
    assert [row["student"].display_name for row in rows] == ["缺口生", "資料生", "待核對生"]
    assert rows[-1]["label"] == "資料已改善，下次重新對照時會自動結案"
    assert "還差" not in rows[-1]["label"]


def test_teacher_pages_show_improved_label_for_awaiting(tmp_path):
    app = pages_app(tmp_path)
    case_id = make_case(app)
    with app.app_context():
        case = db.session.get(GraduationCase, case_id)
        case.status, case.last_result = "awaiting_verification", "met"
        student_id = case.student_id
        db.session.commit()
    client = as_user(app, "tea")
    for path in ("/teacher/dashboard", f"/teacher/students/{student_id}", f"/graduation/cases/{case_id}"):
        html = client.get(path).get_data(as_text=True)
        assert "資料已改善，下次重新對照時會自動結案" in html, path
        assert "證照還差" not in html and "目前還差" not in html, path


def test_priority_hints(monkeypatch, tmp_path):
    app, ids = _setup(monkeypatch, tmp_path, BASIC)
    hints = {row["student"].display_name: row["hint"] for row in _overview(app, ids)["priority"]}
    assert hints["缺口生"] == "依實施要點第五點補救"
    assert hints["待確認生"] == "請學生上傳並確認資料"


def test_teacher_dashboard_shows_cards_and_names(tmp_path):
    app = pages_app(tmp_path)
    make_case(app)
    client = as_user(app, "tea")
    # 工作台（2026-11-21 拆頁）：待處理與優先關心的學生預覽
    dashboard = client.get("/teacher/dashboard").get_data(as_text=True)
    for text in ("確定有缺口", "需要優先關心的學生", "G-0000", "僅供提醒"):
        assert text in dashboard
    # 畢業門檻頁：四個人數卡與完整優先名單；學生名單頁：學生名字
    graduation = client.get("/teacher/graduation").get_data(as_text=True)
    for text in ("已達門檻", "確定有缺口", "資料待確認", "需要優先關心的學生", "G-0000", "僅供提醒"):
        assert text in graduation
    assert "測試學生" in client.get("/teacher/roster").get_data(as_text=True)


def test_teacher_dashboard_is_split_into_pages_and_rows_clickable(tmp_path):
    """2026-11-21 導師工作台拆成四頁：工作台只放待處理與入口，畢業門檻、學生名單、目標校系各自一頁。"""
    app = pages_app(tmp_path)
    case_id = make_case(app)
    with app.app_context():
        student_id = User.query.filter_by(username="stu").one().id
    client = as_user(app, "tea")
    dashboard = client.get("/teacher/dashboard").get_data(as_text=True)
    # 工作台：先看待處理（優先關心的學生預覽），下面是三個分頁入口；不再放整張學生表
    assert "data-grad-overview" in dashboard and "data-priority-preview" in dashboard
    assert "data-teacher-entries" in dashboard
    assert "data-class-roster" not in dashboard and "teacher-roster-table" not in dashboard
    assert f'href="/graduation/cases/{case_id}"' in dashboard
    for path in ("/teacher/graduation", "/teacher/roster", "/teacher/targets"):
        assert f'href="{path}"' in dashboard
    # 沒有待確認的備審資料時，數字卡不連結
    assert "data-pending-link" not in dashboard
    # 畢業門檻頁：完整的優先關心名單，每一列右邊有明確的「查看」按鈕，整列可點
    graduation = client.get("/teacher/graduation").get_data(as_text=True)
    assert "data-grad-overview" in graduation and "需要優先關心的學生" in graduation
    priority = graduation[graduation.index("data-priority-list"):]
    assert f'class="button button--small row-link__target" href="/graduation/cases/{case_id}"' in priority
    # 學生名單頁：本班學生表，每一列整列可點
    roster = client.get("/teacher/roster").get_data(as_text=True)
    assert "data-class-roster" in roster
    assert f'class="button button--small row-link__target" href="/teacher/students/{student_id}"' in roster[roster.index("data-class-roster"):]
    assert '<tr class="row-link">' in roster


def test_teacher_split_pages_open_filter_and_guard_roles(tmp_path):
    """導師四個分頁都打得開、導覽列有四個入口、班級篩選與「只看待確認」正確，學生不能進。"""
    app = pages_app(tmp_path)
    make_case(app)
    teacher = as_user(app, "tea")
    pages = {"/teacher/dashboard": "老師", "/teacher/graduation": "畢業門檻",
             "/teacher/roster": "學生名單", "/teacher/targets": "目標校系"}
    for path, heading in pages.items():
        response = teacher.get(path)
        assert response.status_code == 200, path
        html = response.get_data(as_text=True)
        assert heading in html
        for other in pages:   # 每一頁的導覽列都有四個入口
            assert f'href="{other}"' in html, (path, other)
    # 不是自己負責的班級：400；一進來就只看待確認：勾選框預設勾起
    assert teacher.get("/teacher/roster?class_name=不存在的班").status_code == 400
    assert teacher.get("/teacher/graduation?class_name=不存在的班").status_code == 400
    assert 'id="roster-filter-pending" checked' in teacher.get("/teacher/roster?pending=1").get_data(as_text=True)
    assert 'id="roster-filter-pending" checked' not in teacher.get("/teacher/roster").get_data(as_text=True)
    # 學生不能進導師的頁面
    student = as_user(app, "stu")
    for path in ("/teacher/graduation", "/teacher/roster", "/teacher/targets"):
        assert student.get(path).status_code != 200, path


def test_teacher_sees_only_own_class(tmp_path):
    app = pages_app(tmp_path)
    make_case(app)
    with app.app_context():
        other = _student("far", "別班學生", "99999", class_name="五專五乙")
        _case(other, "certificates", "gap", 2)
        db.session.commit()
    html = as_user(app, "tea").get("/teacher/dashboard").get_data(as_text=True)
    assert "測試學生" in html
    assert "別班學生" not in html


def test_dashboard_get_is_read_only(tmp_path):
    app = pages_app(tmp_path)
    make_case(app)
    with app.app_context():
        before = (GraduationCase.query.count(), GraduationCaseEvent.query.count(), Notification.query.count())
    client = as_user(app, "tea")
    client.get("/teacher/dashboard")
    with app.app_context():
        student_id = User.query.filter_by(username="stu").one().id
    client.get(f"/teacher/students/{student_id}")
    with app.app_context():
        assert before == (GraduationCase.query.count(), GraduationCaseEvent.query.count(),
                          Notification.query.count())


def test_teacher_student_page_shows_case_and_note_form(tmp_path):
    app = pages_app(tmp_path)
    case_id = make_case(app)
    with app.app_context():
        student_id = User.query.filter_by(username="stu").one().id
    client = as_user(app, "tea")
    html = client.get(f"/teacher/students/{student_id}").get_data(as_text=True)
    assert "僅供提醒" in html
    assert f"/graduation/cases/{case_id}/actions" in html
    assert 'value="note"' in html
    assert "專四下學期期末考前兩週" in html or "已過兩次檢核" in html or "專五上學期期末考前兩週" in html
    response = client.post(f"/graduation/cases/{case_id}/actions", data={"action": "note", "note": "面談過了"})
    assert response.status_code == 302
    html = client.get(f"/teacher/students/{student_id}").get_data(as_text=True)
    assert "面談過了" in html


def test_next_check_text():
    assert svc.next_check_text({"grade": 3, "semester": "上"}) == "專四下學期期末考前兩週"
    assert svc.next_check_text({"grade": 4, "semester": "下"}) == "專四下學期期末考前兩週"
    assert svc.next_check_text({"grade": 5, "semester": "上"}) == "專五上學期期末考前兩週"
    assert svc.next_check_text({"grade": 5, "semester": "下"}) == "已過兩次檢核，請向教務處確認"


def test_staff_dashboard_has_no_graduation_cases(tmp_path):
    # 2026-11-09：畢業資格審查由教務處負責，科辦首頁不再列畢業缺口，重新對照按鈕移到管理員首頁
    app = pages_app(tmp_path)
    case_id = make_case(app)
    with app.app_context():
        case = db.session.get(GraduationCase, case_id)
        case.status = "awaiting_verification"
        number = case.number
        db.session.commit()
    html = as_user(app, "sta").get("/staff/dashboard").get_data(as_text=True)
    assert number not in html and "畢業缺口" not in html and "recheck" not in html
    admin = as_user(app, "adm").get("/admin/dashboard").get_data(as_text=True)
    assert "/admin/graduation/recheck" in admin and "data-grad-recheck" in admin

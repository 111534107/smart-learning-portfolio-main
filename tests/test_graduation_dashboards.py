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
    assert rows[-1]["label"] == "資料已改善，待科辦核對"
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
        assert "資料已改善，待科辦核對" in html, path
        assert "證照還差" not in html and "目前還差" not in html, path


def test_priority_hints(monkeypatch, tmp_path):
    app, ids = _setup(monkeypatch, tmp_path, BASIC)
    hints = {row["student"].display_name: row["hint"] for row in _overview(app, ids)["priority"]}
    assert hints["缺口生"] == "依實施要點第五點補救"
    assert hints["待確認生"] == "請學生上傳並確認資料"


def test_teacher_dashboard_shows_cards_and_names(tmp_path):
    app = pages_app(tmp_path)
    make_case(app)
    html = as_user(app, "tea").get("/teacher/dashboard").get_data(as_text=True)
    for text in ("已達門檻", "確定有缺口", "資料待確認", "測試學生", "需要優先關心的學生", "G-0000", "僅供提醒"):
        assert text in html


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
    assert svc.next_check_text({"grade": 5, "semester": "下"}) == "已過兩次檢核，請與科辦確認"


def test_staff_dashboard_lists_awaiting_cases(tmp_path):
    app = pages_app(tmp_path)
    case_id = make_case(app)
    with app.app_context():
        case = db.session.get(GraduationCase, case_id)
        case.status = "awaiting_verification"
        number = case.number
        db.session.commit()
    html = as_user(app, "sta").get("/staff/dashboard").get_data(as_text=True)
    assert number in html
    assert "/staff/graduation/recheck" in html
    assert "僅供提醒" in html

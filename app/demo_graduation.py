"""畢業缺口案件的展示資料：只放合成學生，供展示站與測試使用。

呼叫 seed_graduation_demo(today) 會建立一個 111 學年度入學的班級、四位假學生，
設定檢核用的「今天」，再同步案件。可重複呼叫：已存在的帳號與資料不會重複建立。
"""

from datetime import date

from app.extensions import db
from app.models import (ClassAdvisor, CredentialRecord, LearningCourseRecord, StudentProfile,
                        SystemSetting, User)
from app.services import graduation_case_service
from app.services import graduation_check_service as check
from app.services.eligibility_service import load_curriculum, normalize_course_name

DEMO_CLASS = "資管科五甲"
ADMISSION_YEAR = 111
NOTE = "僅為測試資料"
DEMO_PASSWORD = "demo2026"
TEACHER_USERNAME = "teacher_demo"

# (帳號, 姓名, 學號, 情境)
STUDENTS = (
    ("grad_demo_met", "測試甲", "GD-1110001", "met"),
    ("grad_demo_cert", "測試乙", "GD-1110002", "cert_gap"),
    ("grad_demo_fail", "測試丙", "GD-1110003", "failed_required"),
    ("grad_demo_data", "測試丁", "GD-1110004", "missing_term"),
)
CERTIFICATES = (
    ("電腦軟體應用", "丙級"),
    ("網頁設計", "丙級"),
    ("電腦軟體設計", "丙級"),
)
REQUIRED_CATEGORIES = check.REQUIRED_CATEGORIES
FAILED_COURSE = "計算機網路"
MISSING_TERM = (113, "下")


def _course_plan(table):
    """依 111 屆科目表排出 [(課名, 學分)]：必修合計 181、選修合計 39。"""
    required = [e["name"] for e in table.values() if e["category"] in REQUIRED_CATEGORIES]
    elective = [e["name"] for e in table.values() if e["category"] == "專業選修"][:13]
    credits = [2] * len(required)
    index = 0
    while sum(credits) < check.CREDIT_RULES[ADMISSION_YEAR]["required"]:
        credits[index % len(credits)] += 1
        index += 1
    plan = list(zip(required, credits)) + [(name, 3) for name in elective]
    return plan


def _terms():
    return [(ADMISSION_YEAR + i // 2, "上" if i % 2 == 0 else "下") for i in range(8)]


def _get_or_create_student(username, name, student_no):
    user = User.query.filter_by(username=username).first()
    if user is not None:
        return user, False
    user = User(username=username, display_name=f"{name}（{NOTE}）", role="student")
    user.set_password(DEMO_PASSWORD)
    db.session.add(user)
    db.session.flush()
    db.session.add(StudentProfile(user_id=user.id, student_no=student_no, class_name=DEMO_CLASS,
                                  admission_year=ADMISSION_YEAR))
    return user, True


def _add_courses(student, plan, scenario):
    terms = _terms()
    for number, (name, credits) in enumerate(plan):
        year, semester = terms[number % len(terms)]
        score = 80 + number % 15
        if scenario == "missing_term" and (year, semester) == MISSING_TERM:
            continue
        if scenario == "failed_required" and name == FAILED_COURSE:
            score = 45
        db.session.add(LearningCourseRecord(
            student_id=student.id, school_year=year, semester=semester, course_name=name,
            normalized_course_name=normalize_course_name(name), credits=credits, score=score,
            confirmation_status="confirmed"))


def _add_certificates(student, count):
    for name, level in CERTIFICATES[:count]:
        db.session.add(CredentialRecord(student_id=student.id, credential_name=name,
                                        level=level, issuing_organization="勞動部（合成資料）",
                                        confirmation_status="confirmed"))


def seed_graduation_demo(today: date) -> dict:
    """建立畢業缺口展示資料並同步案件；回傳建立的帳號與案件編號供驗收使用。"""
    teacher = User.query.filter_by(username=TEACHER_USERNAME).first()
    if teacher is not None and not ClassAdvisor.query.filter_by(
            teacher_id=teacher.id, class_name=DEMO_CLASS).first():
        db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name=DEMO_CLASS,
                                    school_year=check.academic_term(today)[0]))
    setting = SystemSetting.query.filter_by(key=check.TODAY_SETTING_KEY).first()
    if setting is None:
        db.session.add(SystemSetting(key=check.TODAY_SETTING_KEY, value=today.isoformat()))
    else:
        setting.value = today.isoformat()

    plan = _course_plan(load_curriculum()[ADMISSION_YEAR])
    students = {}
    for username, name, student_no, scenario in STUDENTS:
        student, created = _get_or_create_student(username, name, student_no)
        students[scenario] = username
        if not created:
            continue
        _add_courses(student, plan, scenario)
        _add_certificates(student, 1 if scenario == "cert_gap" else 3)
    db.session.flush()
    graduation_case_service.sync_all(today)
    db.session.commit()

    from app.models import GraduationCase
    ids = [u.id for u in User.query.filter(User.username.in_([s[0] for s in STUDENTS])).all()]
    cases = (GraduationCase.query.filter(GraduationCase.student_id.in_(ids), GraduationCase.status != "closed")
             .order_by(GraduationCase.id).all())
    return {"class_name": DEMO_CLASS, "teacher": TEACHER_USERNAME, "students": students,
            "cases": [{"number": c.number, "student": c.student.username, "type": c.case_type,
                       "item": c.item} for c in cases]}

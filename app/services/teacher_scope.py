"""導師只可查看目前學年度已指派班級的學生。"""

from datetime import datetime, timedelta, timezone

from app.models import ClassAdvisor, StudentProfile, User


def school_year_for_date(day):
    """民國學年度：8 月 1 日起為新學年度。"""
    return day.year - 1911 - (1 if day.month < 8 else 0)


def current_school_year():
    return school_year_for_date(datetime.now(timezone(timedelta(hours=8))).date())


def advised_classes(teacher):
    if teacher.role != "teacher" or not teacher.is_active:
        return []
    return sorted({row.class_name for row in ClassAdvisor.query.filter_by(
        teacher_id=teacher.id, school_year=current_school_year()).all()})


def teachers_for_student(student):
    """同年同班的啟用中導師，每位只回傳一次。"""
    profile = student.student_profile
    if student.role != "student" or not student.is_active or not profile or not profile.class_name:
        return []
    ids = {row.teacher_id for row in ClassAdvisor.query.filter_by(
        class_name=profile.class_name, school_year=current_school_year()).all()}
    return (User.query.filter(User.id.in_(ids), User.role == "teacher", User.is_active.is_(True))
            .order_by(User.id).all())


def students_for_teacher(teacher):
    classes = advised_classes(teacher)
    if not classes:
        return []
    return (User.query.join(StudentProfile, StudentProfile.user_id == User.id)
            .filter(User.role == "student", User.is_active.is_(True), StudentProfile.class_name.in_(classes))
            .order_by(StudentProfile.student_no).all())


def can_view_student(teacher, student):
    if teacher.role != "teacher" or student.role != "student" or not student.is_active or not student.student_profile:
        return False
    return student.student_profile.class_name in advised_classes(teacher)

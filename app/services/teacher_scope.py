"""導師可以看哪些學生：只看自己負責班級（class_advisors）的學生。"""

from app.models import ClassAdvisor, StudentProfile, User


def advised_classes(teacher):
    return sorted({row.class_name for row in ClassAdvisor.query.filter_by(teacher_id=teacher.id).all()})


def students_for_teacher(teacher):
    classes = advised_classes(teacher)
    if not classes:
        return []
    return (User.query.join(StudentProfile, StudentProfile.user_id == User.id)
            .filter(User.role == "student", User.is_active.is_(True), StudentProfile.class_name.in_(classes))
            .order_by(StudentProfile.student_no).all())


def can_view_student(teacher, student):
    if teacher.role != "teacher" or student.role != "student" or not student.student_profile:
        return False
    return student.student_profile.class_name in advised_classes(teacher)

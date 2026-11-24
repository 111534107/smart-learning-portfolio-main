"""導師班級指派（管理員與科主任共用）：新增、移除都寫操作紀錄；只記編號與學年度，不記學生資料。

同班可有多位導師；同一位導師同班同學年度不能重複。移除沿用既有行為（刪除指派這一列，操作紀錄永久保留）。
"""

from app.extensions import db
from app.models import ClassAdvisor, User
from app.services import audit_service


class AssignmentError(ValueError):
    pass


def add(actor, teacher_id, class_name, school_year):
    teacher = db.session.get(User, teacher_id or 0)
    class_name = (class_name or "").strip()
    if not teacher or teacher.role != "teacher" or not teacher.is_active:
        raise AssignmentError("請選擇導師帳號")
    if not class_name or not school_year:
        raise AssignmentError("請填寫班級與學年度")
    if ClassAdvisor.query.filter_by(teacher_id=teacher.id, class_name=class_name, school_year=school_year).first():
        raise AssignmentError("這位導師已經負責這個班級")
    advisor = ClassAdvisor(teacher_id=teacher.id, class_name=class_name, school_year=school_year)
    db.session.add(advisor)
    db.session.flush()
    audit_service.record(actor, "class_advisor.add", "class_advisor", advisor.id,
                         {"teacher_id": teacher.id, "school_year": school_year})
    db.session.commit()
    return advisor


def remove(actor, advisor_id):
    advisor = db.session.get(ClassAdvisor, advisor_id)
    if advisor:
        audit_service.record(actor, "class_advisor.remove", "class_advisor", advisor.id,
                             {"teacher_id": advisor.teacher_id, "school_year": advisor.school_year})
        db.session.delete(advisor)
        db.session.commit()


def page_data():
    """班級指派頁共用的清單（管理員頁與科主任頁同一個樣板）。"""
    from app.models import StudentProfile
    return {
        "advisors": ClassAdvisor.query.order_by(ClassAdvisor.school_year.desc(), ClassAdvisor.class_name).all(),
        "teachers": User.query.filter_by(role="teacher", is_active=True).order_by(User.display_name).all(),
        "class_names": sorted({p.class_name for p in StudentProfile.query.all() if p.class_name}),
    }

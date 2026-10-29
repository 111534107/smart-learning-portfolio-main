"""測試共用：把學生的拼圖桌板補滿（走過的每個年級 × 六類都有一筆資料）。"""
from datetime import date

from app.extensions import db
from app.models import CredentialRecord, LearningCourseRecord, Portfolio
from app.services.journey_service import EXPERIENCE_CATEGORIES, current_grade


def fill_board(user):
    """依學生目前年級，補到每一格都有資料；已有的資料不動，呼叫端要自己 commit 之外的事不用管。"""
    admission_year = user.student_profile.admission_year
    for grade in range(1, current_grade(admission_year) + 1):
        year = admission_year + grade - 1
        db.session.add(LearningCourseRecord(student_id=user.id, school_year=grade, course_name=f"拼圖課程{grade}",
                                            normalized_course_name=f"拼圖課程{grade}", score=80,
                                            confirmation_status="confirmed"))
        db.session.add(CredentialRecord(student_id=user.id, credential_name=f"拼圖證照{grade}",
                                        issue_date=date(year + 1911, 10, 1), confirmation_status="confirmed"))
        for category in EXPERIENCE_CATEGORIES:
            db.session.add(Portfolio(student_id=user.id, title=f"拼圖{category}{grade}", category=category,
                                     school_year=grade, status="confirmed"))
    db.session.commit()

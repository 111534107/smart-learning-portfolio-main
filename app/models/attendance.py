from app.extensions import db


class AttendanceSummary(db.Model):
    """One private, student-confirmed attendance summary per school term."""

    __tablename__ = "attendance_summaries"
    __table_args__ = (db.UniqueConstraint("student_id", "school_year", "semester",
                                          name="uq_attendance_student_term"),)

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    school_year = db.Column(db.Integer, nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    totals = db.Column(db.JSON, nullable=False)

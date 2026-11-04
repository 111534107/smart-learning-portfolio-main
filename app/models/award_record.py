from datetime import datetime, timezone

from app.extensions import db


class SchoolAwardRecord(db.Model):
    """學校獎懲記錄的每一列（獎勵與懲處都存）。

    獎勵確認後會另外建一筆「活動與經歷」（portfolio_id 指向它）；懲處只存在這裡，
    不會進活動與經歷。record_key 是同一列的指紋，用來避免重複匯入，
    學生刪掉已匯入的經歷後再匯入一次也不會冒回來。
    """

    __tablename__ = "school_award_records"
    __table_args__ = (db.UniqueConstraint("student_id", "record_key", name="uq_school_award_student_key"),)

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    source_document_id = db.Column(db.Integer, db.ForeignKey("source_documents.id"), nullable=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey("portfolios.id"), nullable=True)
    record_key = db.Column(db.String(64), nullable=False)
    record_type = db.Column(db.String(20), nullable=False)  # reward 獎勵／punishment 懲處
    date = db.Column(db.String(20), nullable=True)
    name = db.Column(db.String(20), nullable=True)  # 嘉獎、小功、警告……
    count = db.Column(db.Integer, nullable=True)
    reason = db.Column(db.Text, nullable=False)
    revoked = db.Column(db.String(50), nullable=False, default="", server_default="")  # 銷過欄原文，空字串表示未銷過
    school_year = db.Column(db.Integer, nullable=True)  # 學年度，寫民國年（例如 114）
    semester = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

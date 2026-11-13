"""學校名錄（2026-11-13）：地區、縣市、座標與網站，給目標校系頁的分區選單、台灣地圖與學校卡片用。

學校名稱和 admission_rule_versions.school_name 對應（簡章上的校名）。管理員在「學校資料」頁維護。
"""
from datetime import datetime, timezone

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class School(db.Model):
    __tablename__ = "schools"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    region = db.Column(db.String(10), nullable=False)  # 北部／中部／南部／東部／離島
    city = db.Column(db.String(20), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    website_url = db.Column(db.String(500), nullable=True)
    admission_url = db.Column(db.String(500), nullable=True)
    checked_on = db.Column(db.Date, nullable=True)  # 資料最後人工確認的日期
    links_checked_at = db.Column(db.DateTime, nullable=True)  # 系統最後自動檢查連結的時間
    link_problems = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    department_links = db.relationship("SchoolDepartmentLink", back_populates="school", cascade="all, delete-orphan",
                                       order_by="SchoolDepartmentLink.department_name")


class SchoolDepartmentLink(db.Model):
    """一所學校一個科系的介紹網址（科系名稱用簡章上的寫法）。"""

    __tablename__ = "school_department_links"
    __table_args__ = (db.UniqueConstraint("school_id", "department_name", name="uq_school_department"),)

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    department_name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(500), nullable=False)

    school = db.relationship("School", back_populates="department_links")

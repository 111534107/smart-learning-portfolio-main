from datetime import datetime, timezone

from app.extensions import db
from app.services import file_preview

# 每筆資料的證明來源。之後新增來源（例如競賽報名系統）只要在這裡多加一個。
SOURCE_LABELS = {
    "student": "學生填寫",
    "award_record": "學校獎懲記錄",
    "school_certificate": "學校電子證書",
    "organizer": "競賽主辦方",
    "department_certificate": "科辦電子獎狀",
}


class Portfolio(db.Model):
    __tablename__ = "portfolios"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=True)
    course_name = db.Column(db.String(100), nullable=True)
    school_year = db.Column(db.Integer, nullable=True)
    semester = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    source = db.Column(db.String(30), nullable=False, default="student", server_default="student")
    source_document_id = db.Column(db.Integer, db.ForeignKey("source_documents.id"), nullable=True, index=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    # 學生刪除只標記時間，資料列保留（規格 M10）；讀經歷一律用 Portfolio.active() 排除
    deleted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    student = db.relationship("User", back_populates="portfolios")
    source_document = db.relationship("SourceDocument")
    certificate = db.relationship("AwardCertificate", back_populates="portfolio", uselist=False,
                                  cascade="all, delete-orphan")
    # evidence_items 只含沒刪除的佐證；all_evidence_items 連已刪除的也算（只讀）
    evidence_items = db.relationship(
        "PortfolioEvidence", back_populates="portfolio", cascade="all, delete-orphan",
        primaryjoin="and_(Portfolio.id == PortfolioEvidence.portfolio_id, PortfolioEvidence.deleted_at.is_(None))",
    )
    all_evidence_items = db.relationship("PortfolioEvidence", viewonly=True, order_by="PortfolioEvidence.id")
    submissions = db.relationship(
        "PortfolioSubmission", back_populates="portfolio", cascade="all, delete-orphan",
        order_by="PortfolioSubmission.version_no",
    )

    @classmethod
    def active(cls):
        """沒被學生刪除的經歷。讀經歷的地方都從這裡開始查。"""
        return cls.query.filter(cls.deleted_at.is_(None))

    @property
    def source_label(self):
        return SOURCE_LABELS.get(self.source, self.source)


class PortfolioEvidence(db.Model):
    __tablename__ = "portfolio_evidence"

    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(
        db.Integer, db.ForeignKey("portfolios.id"), nullable=False, index=True
    )
    evidence_type = db.Column(db.String(30), nullable=False)
    display_name = db.Column(db.String(150), nullable=False)
    file_path = db.Column(db.String(255), nullable=True)
    external_url = db.Column(db.String(500), nullable=True)
    is_available = db.Column(db.Boolean, nullable=False, default=True)
    deleted_at = db.Column(db.DateTime, nullable=True)  # 學生刪除只標記，資料列保留
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    portfolio = db.relationship("Portfolio", back_populates="evidence_items", overlaps="all_evidence_items")

    @property
    def extension(self):
        return file_preview.extension(self.display_name)

    @property
    def preview_kind(self):
        """"image"、"pdf" 或 None（不能預覽，只能下載）。"""
        return file_preview.preview_kind(self.display_name)

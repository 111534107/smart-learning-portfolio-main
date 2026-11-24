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
    # 寫自傳用的四個細節（設計書 D-1）：各校備審指引都要求團體作品寫個人貢獻、成果與反思
    role = db.Column(db.Text, nullable=True)  # 我負責的部分
    achievement = db.Column(db.String(300), nullable=True)  # 數字成果（人數、名次、件數、時間）
    learned = db.Column(db.Text, nullable=True)  # 學到什麼
    # 相關領域存在 portfolio_domain_tags（一個領域一列，第一正規化，2026-11-13）；domain_tags 屬性讀寫「、」分隔字串
    domain_tag_rows = db.relationship("PortfolioDomainTag", cascade="all, delete-orphan",
                                      order_by="PortfolioDomainTag.sort_order")
    course_name = db.Column(db.String(100), nullable=True)
    school_year = db.Column(db.Integer, nullable=True)
    semester = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    source = db.Column(db.String(30), nullable=False, default="student", server_default="student")
    source_document_id = db.Column(db.Integer, db.ForeignKey("source_documents.id"), nullable=True, index=True)
    # 學生選擇不放進備審（2026-11-12）；簡章規定必備的類別仍會放，見 services/package_exclusion.py
    excluded_from_package = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
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

    @property
    def domain_tags(self):
        return "、".join(row.tag for row in self.domain_tag_rows) or None

    @domain_tags.setter
    def domain_tags(self, value):
        import re
        tags = re.split(r"[、,，;；/\s]+", value) if isinstance(value, str) else list(value or [])
        tags = list(dict.fromkeys(tag.strip()[:50] for tag in tags if tag and tag.strip()))
        self.domain_tag_rows = [PortfolioDomainTag(tag=tag, sort_order=order) for order, tag in enumerate(tags)]

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


class PortfolioDomainTag(db.Model):
    """經歷的一個相關領域（例如「系統開發」）。一筆經歷可以有多個領域，一個領域一列（第一正規化，2026-11-13）。"""

    __tablename__ = "portfolio_domain_tags"

    portfolio_id = db.Column(db.Integer, db.ForeignKey("portfolios.id", ondelete="CASCADE"), primary_key=True)
    tag = db.Column(db.String(50), primary_key=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

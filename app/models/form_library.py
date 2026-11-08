"""表單下載區（UC-28／F-53）：科辦上架的表單、分類與每一版的檔案。

版本發布後不能覆寫：改內容就新增一版，學生與老師下載的一定是最新版，舊版留在後台。
收件（學生繳回）2026-10-09 暫停，本版沒有收件的表。
"""
from datetime import datetime, timezone

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class FormCategory(db.Model):
    """科辦自訂的分類；不能刪除，只能停用（停用後底下的表單學生老師看不到）。"""

    __tablename__ = "form_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    items = db.relationship("FormItem", back_populates="category", order_by="FormItem.title")


class FormItem(db.Model):
    __tablename__ = "form_items"

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("form_categories.id"), nullable=False, index=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    open_to_students = db.Column(db.Boolean, nullable=False, default=False)
    open_to_teachers = db.Column(db.Boolean, nullable=False, default=False)
    is_published = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    category = db.relationship("FormCategory", back_populates="items")
    created_by = db.relationship("User")
    versions = db.relationship("FormItemVersion", back_populates="item", order_by="FormItemVersion.version_no")

    @property
    def latest_version(self):
        return self.versions[-1] if self.versions else None


class FormItemVersion(db.Model):
    """一版的檔案。程式裡沒有任何修改這張表既有資料的路徑。"""

    __tablename__ = "form_item_versions"
    __table_args__ = (db.UniqueConstraint("item_id", "version_no", name="uq_form_item_version"),)

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("form_items.id"), nullable=False, index=True)
    version_no = db.Column(db.Integer, nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    file_sha256 = db.Column(db.String(64), nullable=False)
    note = db.Column(db.String(200), nullable=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    item = db.relationship("FormItem", back_populates="versions")
    uploaded_by = db.relationship("User")

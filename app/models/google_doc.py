from datetime import datetime, timezone

from app.extensions import db


class AutobiographyGoogleDoc(db.Model):
    """學生把某個校系的自傳放到自己 My Drive 的那一份 Google 文件。

    只記文件 ID、連結和對應的自傳版本；Google 權杖不存在這裡（只放伺服器記憶體，見 google_docs_service）。
    同一位學生、同一個校系只有一份，之後再按「在 Google 文件中編輯」就開同一份。
    """

    __tablename__ = "autobiography_google_docs"
    __table_args__ = (db.UniqueConstraint("student_id", "program_id", name="uq_autobiography_google_doc"),)

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    program_id = db.Column(db.Integer, db.ForeignKey("admission_rule_versions.id"), nullable=False)
    google_file_id = db.Column(db.String(128), nullable=False)
    web_view_link = db.Column(db.String(500), nullable=False)
    based_on_output_id = db.Column(db.Integer, db.ForeignKey("learning_profile_outputs.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    last_pulled_at = db.Column(db.DateTime, nullable=True)
    last_pulled_output_id = db.Column(db.Integer, db.ForeignKey("learning_profile_outputs.id"), nullable=True)


class StudentDriveFolder(db.Model):
    """學生雲端硬碟裡本系統建立的資料夾編號：「備審資料」一個，各校系一個（備審資料／校名_科系）。

    只建一次，之後重用；編號只是 Drive 上的 ID，不含檔案內容。
    folder_key：root 代表「備審資料」，program:<校系 id> 代表該校系的資料夾。
    """

    __tablename__ = "student_drive_folders"
    __table_args__ = (db.UniqueConstraint("student_id", "folder_key", name="uq_student_drive_folder"),)

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    folder_key = db.Column(db.String(40), nullable=False)
    google_folder_id = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

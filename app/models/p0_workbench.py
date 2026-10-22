from datetime import datetime, timezone
from app.extensions import db

def _utcnow():
    return datetime.now(timezone.utc)

class ConsentRecord(db.Model):
    __tablename__ = "consent_records"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    source_document_id = db.Column(db.Integer, db.ForeignKey("source_documents.id"), nullable=False, index=True)
    purpose = db.Column(db.String(100), nullable=False)
    mask_version = db.Column(db.String(50), nullable=False)
    agreed_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    revoked_at = db.Column(db.DateTime, nullable=True)

    def revoke(self):
        self.revoked_at = _utcnow()

class PuzzlePiece(db.Model):
    __tablename__ = "puzzle_pieces"
    __table_args__ = (
        db.UniqueConstraint("student_id", "piece_key", name="uq_puzzle_piece_student_key"),
    )
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    piece_key = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="empty")
    guidance = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    @db.validates("piece_key")
    def validate_piece_key(self, key, value):
        valid_keys = {"course", "work", "credential_skill", "competition_activity", "project", "internship", "reflection", "next_step"}
        if value not in valid_keys:
            raise ValueError(f"Invalid piece_key: {value}")
        return value

class PuzzleEvidence(db.Model):
    __tablename__ = "puzzle_evidence"
    id = db.Column(db.Integer, primary_key=True)
    piece_id = db.Column(db.Integer, db.ForeignKey("puzzle_pieces.id"), nullable=False, index=True)
    evidence_type = db.Column(db.String(50), nullable=False)
    evidence_id = db.Column(db.Integer, nullable=False)
    confirmed_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

class EditableDraft(db.Model):
    __tablename__ = "editable_drafts"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    draft_type = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    source_snapshot_json = db.Column(db.JSON, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="draft")
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

class ApiKeyMetadata(db.Model):
    __tablename__ = "api_key_metadata"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    mode = db.Column(db.String(30), nullable=False)
    last_four = db.Column(db.String(4), nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

class PublicSource(db.Model):
    __tablename__ = "public_sources"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    source_type = db.Column(db.String(50), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

class PublicSourceSnapshot(db.Model):
    __tablename__ = "public_source_snapshots"
    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.Integer, db.ForeignKey("public_sources.id"), nullable=False, index=True)
    content_hash = db.Column(db.String(64), nullable=False)
    fetched_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

class PublicSourceChange(db.Model):
    __tablename__ = "public_source_changes"
    id = db.Column(db.Integer, primary_key=True)
    snapshot_id = db.Column(db.Integer, db.ForeignKey("public_source_snapshots.id"), nullable=False, index=True)
    change_type = db.Column(db.String(30), nullable=False)
    diff_json = db.Column(db.JSON, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="candidate")

class PublicSourcePublication(db.Model):
    __tablename__ = "public_source_publications"
    id = db.Column(db.Integer, primary_key=True)
    snapshot_id = db.Column(db.Integer, db.ForeignKey("public_source_snapshots.id"), nullable=False, unique=True)
    published_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    published_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

import pytest
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from app.models.p0_workbench import (
    ConsentRecord, PuzzlePiece, PuzzleEvidence, EditableDraft, ApiKeyMetadata,
    PublicSource, PublicSourceSnapshot, PublicSourceChange, PublicSourcePublication
)
from app.models.user import User
from app.extensions import db
from app import create_app

def p0_app(tmp_path):
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
        "UPLOAD_FOLDER": str(tmp_path),
    })
    with app.app_context():
        db.create_all()
        # Create a dummy user for foreign keys
        student = User(username="student_demo", display_name="測試學生", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.commit()
    return app

def test_consent_record_creation_and_revoke(tmp_path):
    app = p0_app(tmp_path)
    with app.app_context():
        student_id = User.query.first().id
        consent = ConsentRecord(
            student_id=student_id,
            source_document_id=101, # Can be dummy as we don't enforce all FKs strictly in this quick test if source_documents table is empty, wait SQLite does enforce FK if PRAGMA foreign_keys=ON
            purpose="learning_profile_analysis",
            mask_version="v1.0"
        )
        db.session.add(consent)
        db.session.commit()
        
        assert consent.id is not None
        assert consent.agreed_at is not None
        assert consent.revoked_at is None
        
        consent.revoke()
        db.session.commit()
        assert consent.revoked_at is not None

def test_puzzle_piece_unique_constraint(tmp_path):
    app = p0_app(tmp_path)
    with app.app_context():
        student_id = User.query.first().id
        piece1 = PuzzlePiece(student_id=student_id, piece_key="course", status="empty")
        db.session.add(piece1)
        db.session.commit()
        
        piece2 = PuzzlePiece(student_id=student_id, piece_key="course", status="lit")
        db.session.add(piece2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

def test_puzzle_piece_fixed_keys(tmp_path):
    app = p0_app(tmp_path)
    with app.app_context():
        student_id = User.query.first().id
        valid_keys = {"course", "work", "credential_skill", "competition_activity", "project", "internship", "reflection", "next_step"}
        
        with pytest.raises(ValueError):
            piece = PuzzlePiece(student_id=student_id, piece_key="invalid_key", status="empty")
            db.session.add(piece)
            db.session.commit()
        db.session.rollback()
        db.session.rollback()

def test_editable_draft_snapshot(tmp_path):
    app = p0_app(tmp_path)
    with app.app_context():
        student_id = User.query.first().id
        draft = EditableDraft(
            student_id=student_id,
            draft_type="autobiography",
            content="Hello world",
            source_snapshot_json={"courses": [], "credentials": []}
        )
        db.session.add(draft)
        db.session.commit()
        
        assert draft.source_snapshot_json == {"courses": [], "credentials": []}

def test_api_key_metadata_no_raw_key(tmp_path):
    app = p0_app(tmp_path)
    with app.app_context():
        student_id = User.query.first().id
        # Should not be able to store the full raw key
        metadata = ApiKeyMetadata(
            student_id=student_id,
            mode="personal_saved",
            last_four="1234"
        )
        db.session.add(metadata)
        db.session.commit()
        
        assert not hasattr(metadata, "raw_key")
        assert metadata.last_four == "1234"

def test_public_source_publication_workflow(tmp_path):
    app = p0_app(tmp_path)
    with app.app_context():
        student_id = User.query.first().id
        source = PublicSource(name="Test Source", url="http://test.com", source_type="api")
        db.session.add(source)
        db.session.commit()
        
        snapshot = PublicSourceSnapshot(source_id=source.id, content_hash="abc", fetched_at=datetime.now(timezone.utc))
        db.session.add(snapshot)
        db.session.commit()
        
        # Candidate changes cannot be published directly without a publication record
        change = PublicSourceChange(snapshot_id=snapshot.id, change_type="added", diff_json={})
        db.session.add(change)
        db.session.commit()
        
        pub = PublicSourcePublication(snapshot_id=snapshot.id, published_by=student_id)
        db.session.add(pub)
        db.session.commit()
        
        assert pub.published_at is not None

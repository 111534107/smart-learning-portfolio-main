from datetime import datetime, timezone
from app.extensions import db

def now():
    return datetime.now(timezone.utc)

class TransferReviewCase(db.Model):
    __tablename__ = 'transfer_review_cases'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    open_key = db.Column(db.Integer, unique=True, nullable=True)
    class_name = db.Column(db.String(50), nullable=False)
    admission_year = db.Column(db.Integer, nullable=False)
    assistant_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    chief_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    previous_case_id = db.Column(db.Integer, db.ForeignKey('transfer_review_cases.id'))
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    student = db.relationship('User', foreign_keys=[student_id])

class TransferReviewEvent(db.Model):
    __tablename__ = 'transfer_review_events'
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('transfer_review_cases.id'), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(30), nullable=False)
    reason = db.Column(db.Text, nullable=False, default='')
    class_name = db.Column(db.String(50), nullable=False)
    admission_year = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=now, nullable=False)
    case = db.relationship('TransferReviewCase', backref=db.backref('events', order_by='TransferReviewEvent.id'))
    actor = db.relationship('User', foreign_keys=[actor_id])

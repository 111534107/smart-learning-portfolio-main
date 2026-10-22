from datetime import datetime, timezone

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class ProjectType(db.Model):
    __tablename__ = "project_types"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), nullable=False, unique=True)
    name = db.Column(db.String(100), nullable=False)
    school_year = db.Column(db.Integer, nullable=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    templates = db.relationship("RequirementTemplate", back_populates="project_type", cascade="all, delete-orphan")
    groups = db.relationship("ProjectGroup", back_populates="project_type")


class RequirementTemplate(db.Model):
    __tablename__ = "requirement_templates"
    id = db.Column(db.Integer, primary_key=True)
    project_type_id = db.Column(db.Integer, db.ForeignKey("project_types.id"), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    version = db.Column(db.String(30), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    project_type = db.relationship("ProjectType", back_populates="templates")
    items = db.relationship("RequirementItem", back_populates="template", cascade="all, delete-orphan", order_by="RequirementItem.sort_order")
    assignments = db.relationship("StudentProjectAssignment", back_populates="template")


class RequirementItem(db.Model):
    __tablename__ = "requirement_items"
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("requirement_templates.id"), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    stage = db.Column(db.String(30), nullable=False, default="midterm")
    is_required = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    template = db.relationship("RequirementTemplate", back_populates="items")


class ProjectGroup(db.Model):
    __tablename__ = "project_groups"
    id = db.Column(db.Integer, primary_key=True)
    project_type_id = db.Column(db.Integer, db.ForeignKey("project_types.id"), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    school_year = db.Column(db.Integer, nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default="active")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    project_type = db.relationship("ProjectType", back_populates="groups")
    teacher = db.relationship("User", foreign_keys=[teacher_id])
    members = db.relationship("ProjectMember", back_populates="project_group", cascade="all, delete-orphan")
    assignments = db.relationship("StudentProjectAssignment", back_populates="project_group")


class ProjectMember(db.Model):
    __tablename__ = "project_members"
    id = db.Column(db.Integer, primary_key=True)
    project_group_id = db.Column(db.Integer, db.ForeignKey("project_groups.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    contribution = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="active")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    project_group = db.relationship("ProjectGroup", back_populates="members")
    student = db.relationship("User", foreign_keys=[student_id])


class StudentProjectAssignment(db.Model):
    __tablename__ = "student_project_assignments"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    project_group_id = db.Column(db.Integer, db.ForeignKey("project_groups.id"), nullable=True)
    template_id = db.Column(db.Integer, db.ForeignKey("requirement_templates.id"), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="active")
    assigned_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    student = db.relationship("User", foreign_keys=[student_id])
    project_group = db.relationship("ProjectGroup", back_populates="assignments")
    template = db.relationship("RequirementTemplate", back_populates="assignments")

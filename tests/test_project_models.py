from app import create_app
from app.extensions import db
from app import models
from app.models import User


def test_project_template_and_group_relationships():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        teacher = User(username="teacher", display_name="教師", role="teacher")
        student = User(username="student", display_name="學生", role="student")
        teacher.set_password("pw")
        student.set_password("pw")
        project_type = models.ProjectType(name="資訊軟體開發", code="software", school_year=115, is_active=True)
        template = models.RequirementTemplate(name="115 年期中模板", version="1.0", is_active=True, project_type=project_type)
        item = models.RequirementItem(title="功能展示", stage="midterm", is_required=True, sort_order=1, template=template)
        group = models.ProjectGroup(name="第一組", school_year=115, project_type=project_type, teacher=teacher)
        member = models.ProjectMember(student=student, project_group=group, contribution="後端開發")
        assignment = models.StudentProjectAssignment(student=student, project_group=group, template=template)
        db.session.add_all([teacher, student, project_type, template, item, group, member, assignment])
        db.session.commit()

        assert project_type.templates[0].items[0].title == "功能展示"
        assert group.members[0].student.username == "student"
        assert group.teacher.username == "teacher"
        assert assignment.template.version == "1.0"

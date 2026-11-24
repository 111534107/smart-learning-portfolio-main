"""送給 AI 的指示不能有學生姓名（專案原則：只傳去識別化的最小必要資料；會議室 GPT #10 查證）。"""
from app import create_app
from app.extensions import db
from app.models import StudentProfile, User
from app.services.admission_service import import_seed_programs
from app.models import AdmissionProgram
from app.services.assistant_service import system_instruction
from app.services import autobiography_service


def test_prompts_do_not_contain_student_name():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context(), app.test_request_context():
        db.create_all()
        import_seed_programs()
        user = User(username="s1", display_name="王真名", role="student")
        user.set_password("pw")
        db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=user.id, student_no="111534999", admission_year=113))
        db.session.commit()
        program = AdmissionProgram.query.first()

        assert "王真名" not in system_instruction(user)
        facts = autobiography_service.build_facts(user, program)
        prompt = autobiography_service._prompt(user, program, facts, {})
        assert "王真名" not in prompt and "111534999" not in prompt

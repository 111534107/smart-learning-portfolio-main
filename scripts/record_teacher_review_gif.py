"""以獨立假資料庫錄製導師確認與段落註解，僅監聽 5195。"""
import io
import os
import sys
import threading
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for key in ("AI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"):
    os.environ[key] = ""

from PIL import Image
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from app import create_app
from app.extensions import db
from app.models import AdmissionProgram, ClassAdvisor, LearningProfileOutput, StudentProfile, StudentTarget, User
from app.services import review_snapshot_service


def main():
    run_dir = ROOT / "logs" / "howto-recordings" / uuid.uuid4().hex
    run_dir.mkdir(parents=True)
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(run_dir / 'demo.sqlite').as_posix()}",
                      "UPLOAD_FOLDER": str(run_dir / "uploads"), "TWO_FACTOR_REQUIRED": False,
                      "ADMIN_TWO_FACTOR_REQUIRED": False, "SESSION_COOKIE_NAME": "howto_teacher_5195"})
    with app.app_context():
        db.create_all()
        student = User(username="demo-student", display_name="測試學生", role="student")
        teacher = User(username="demo-teacher", display_name="測試導師", role="teacher")
        for user in (student, teacher):
            user.set_password("demo1234")
            db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=student.id, student_no="test-student", class_name="測試班", admission_year=113))
        db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name="測試班", school_year=115))
        program = AdmissionProgram(program_code="TEST01", admission_year=116, school_name="測試學校", department_name="測試科系", status="published")
        db.session.add(program)
        db.session.flush()
        db.session.add(StudentTarget(student_id=student.id, rule_version_id=program.id))
        output = LearningProfileOutput(student_id=student.id, output_type="autobiography_ai", source_snapshot_json={},
                                       content_json={"program_id": program.id, "version": 1, "editor_role": "student",
                                                     "paragraphs": [{"title": "學習動機", "text": "測試自傳內容。", "sources": []}]})
        db.session.add(output)
        db.session.commit()
        review_snapshot_service.request_review(student, program)
        student_id, output_id = student.id, output.id
    server = make_server("127.0.0.1", 5195, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    frames = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 720, "height": 600})
            page.add_init_script("""document.addEventListener('DOMContentLoaded', () => {
              const label = document.createElement('div'); label.textContent = '僅為測試資料';
              label.style.cssText = 'position:fixed;bottom:0;left:0;z-index:99999;background:#fff;color:#111;padding:3px 8px;font-size:14px';
              document.body.appendChild(label);
            });""")
            def capture():
                page.wait_for_timeout(300)
                frames.append(Image.open(io.BytesIO(page.screenshot())).convert("RGB"))
            page.goto("http://127.0.0.1:5195/staff/login")
            page.locator('input[name="username"]').first.fill("demo-teacher")
            page.locator('input[name="password"]').first.fill("demo1234")
            page.locator('input[name="password"]').first.press("Enter")
            page.goto(f"http://127.0.0.1:5195/teacher/students/{student_id}")
            capture()
            page.locator('[id^="teacher-target-"]').first.scroll_into_view_if_needed()
            capture()
            page.locator('[data-submitted-autobiography] summary').click()
            capture()
            page.goto(f"http://127.0.0.1:5195/teacher/students/{student_id}/autobiography/{output_id}/edit")
            page.locator('[form="cform-new-0"][name="text"]').fill("建議補充實作經驗。")
            page.locator('[form="cform-new-0"][name="text"]').scroll_into_view_if_needed()
            capture()
            page.locator('button[form="cform-new-0"]').click()
            page.wait_for_load_state("networkidle")
            capture()
            page.goto(f"http://127.0.0.1:5195/teacher/students/{student_id}")
            page.locator('input[name="decision"][value="confirmed"]').check()
            page.locator('input[name="decision"][value="confirmed"]').scroll_into_view_if_needed()
            capture()
            page.locator('input[name="decision"][value="confirmed"]').locator('xpath=ancestor::form').get_by_role("button", name="送出", exact=True).click()
            page.wait_for_load_state("networkidle")
            capture()
            browser.close()
        target = ROOT / "app" / "static" / "img" / "howto" / "teacher-review-and-comment.gif"
        if target.exists():
            target = run_dir / target.name
        frames[0].save(target, save_all=True, append_images=frames[1:], duration=1500, loop=0, optimize=True)
        print(f"已錄製 {target}，{target.stat().st_size} 位元組")
    finally:
        server.shutdown()
        thread.join()


if __name__ == "__main__":
    main()

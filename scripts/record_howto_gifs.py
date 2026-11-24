"""以獨立假資料錄製操作示範；只使用 127.0.0.1:5195。"""
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

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from app import create_app
from app.extensions import db
from app.models import AdmissionProgram, AdmissionRequirementItem, AuditLog, ClassAdvisor, StudentProfile, User


def main():
    run_dir = ROOT / "logs" / "howto-recordings" / uuid.uuid4().hex
    run_dir.mkdir(parents=True)
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(run_dir / 'demo.sqlite').as_posix()}",
                      "UPLOAD_FOLDER": str(run_dir / "uploads"), "DOCUMENT_ANALYSIS_PROVIDER": "demo",
                      "TWO_FACTOR_REQUIRED": False, "ADMIN_TWO_FACTOR_REQUIRED": False,
                      "SESSION_COOKIE_NAME": "howto_session_5195"})
    with app.app_context():
        db.create_all()
        user = User(username="demo-student", display_name="測試學生", role="student")
        user.set_password("demo1234")
        db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=user.id, student_no="T0001", class_name="測試班", admission_year=111))
        db.session.add(AuditLog(user_id=user.id, action="student.welcome_done"))
        teacher = User(username="demo-teacher", display_name="測試導師", role="teacher")
        teacher.set_password("demo1234")
        db.session.add(teacher)
        db.session.flush()
        db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name="測試班", school_year=115))
        program = AdmissionProgram(program_code="TEST01", admission_year=116, school_name="測試學校", department_name="測試科系", status="published")
        program.items.append(AdmissionRequirementItem(source_item_name="證照", weight_percent=100, mapped_categories="credential", mapping_status="confirmed"))
        db.session.add(program)
        db.session.commit()
        program_id = program.id
    server = make_server("127.0.0.1", 5195, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    frames = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 720, "height": 600}, device_scale_factor=1)
            page.add_init_script("""localStorage.setItem('tour-declined', '1'); document.addEventListener('DOMContentLoaded', () => {
              const label = document.createElement('div');
              label.textContent = '僅為測試資料';
              label.style.cssText = 'position:fixed;bottom:0;left:0;z-index:99999;background:#fff;color:#111;padding:3px 8px;font-size:14px';
              document.body.appendChild(label);
            });""")
            def capture():
                page.wait_for_timeout(400)
                frames.append(Image.open(io.BytesIO(page.screenshot())).convert("RGB"))
            page.goto("http://127.0.0.1:5195/login")
            page.locator("details.auth__fallback summary").click()
            page.locator('input[name="username"]').fill("demo-student")
            page.locator('input[name="password"]').fill("demo1234")
            page.locator('input[name="password"]').press("Enter")
            page.goto("http://127.0.0.1:5195/student/learning-profile/upload")
            capture()
            sample = Image.new("RGB", (2500, 3500), "white")
            draw = ImageDraw.Draw(sample)
            draw.text((50, 60), "SAMPLE TRANSCRIPT - TEST DATA ONLY", fill="black")
            content = io.BytesIO()
            sample.save(content, format="PNG")
            page.locator('input[type="file"]').set_input_files({"name": "test-transcript.png", "mimeType": "image/png", "buffer": content.getvalue()})
            capture()
            page.get_by_role("button", name="上傳", exact=True).click()
            page.wait_for_url("**/review*", timeout=30000)
            capture()
            page.get_by_role("button", name="確認並儲存").last.scroll_into_view_if_needed()
            capture()
            page.get_by_role("button", name="確認並儲存").last.click()
            page.wait_for_load_state("networkidle")
            capture()
            transcript_frames = frames
            frames = []
            page.goto("http://127.0.0.1:5195/student/attendance-records")
            capture()
            page.locator('#attendance-paste').fill("學年度\t學期\t曠課\t事假\t病假\n114\t1\t2\t0\t3")
            capture()
            page.get_by_role("button", name="預覽貼上的表格").click()
            capture()
            page.get_by_role("button", name="確認並儲存合計").scroll_into_view_if_needed()
            capture()
            page.get_by_role("button", name="確認並儲存合計").click()
            page.wait_for_load_state("networkidle")
            page.locator('#saved-attendance').scroll_into_view_if_needed()
            capture()
            attendance_frames = frames
            frames = []
            page.goto("http://127.0.0.1:5195/student/targets")
            page.locator(f'#target-program-{program_id} summary').scroll_into_view_if_needed()
            capture()
            page.locator(f'#target-program-{program_id} summary').click()
            capture()
            page.get_by_role("button", name="設為目標校系").click()
            page.wait_for_load_state("networkidle")
            page.wait_for_url(f"**/student/targets/{program_id}")
            capture()
            page.locator('.vessel').first.click()
            page.locator('#detail-1').scroll_into_view_if_needed()
            capture()
            target_frames = frames
            frames = []
            page.goto(f"http://127.0.0.1:5195/student/autobiography?program_id={program_id}")
            page.locator('form[data-steps] textarea:visible').first.fill("我喜歡用程式解決問題。（測試）")
            page.locator('form[data-steps] textarea:visible').first.scroll_into_view_if_needed()
            capture()
            page.get_by_role('button', name='自己寫草稿（不使用 AI）').click()
            page.wait_for_load_state("networkidle")
            page.locator('textarea[name="paragraph_0"]').fill("我喜歡用程式解決問題，並持續練習。（測試）")
            capture()
            page.locator('form[data-draft-form]').get_by_role('button', name='儲存', exact=True).first.click()
            page.wait_for_load_state("networkidle")
            capture()
            page.goto(f"http://127.0.0.1:5195/student/targets/{program_id}#review")
            page.get_by_role('button', name='請導師確認內容').scroll_into_view_if_needed()
            capture()
            page.get_by_role('button', name='請導師確認內容').click()
            page.wait_for_load_state("networkidle")
            page.locator('#review').scroll_into_view_if_needed()
            capture()
            autobiography_frames = frames
            frames = []
            page.goto("http://127.0.0.1:5195/student/internship-resume")
            page.locator('input[name="period"]').fill("115年2月至6月（測試）")
            page.locator('input[name="period"]').evaluate("el => el.scrollIntoView({block: 'center'})")
            capture()
            page.locator('button[name="action"][value="save"]').first.scroll_into_view_if_needed()
            capture()
            page.locator('button[name="action"][value="save"]').first.click()
            page.wait_for_load_state("networkidle")
            capture()
            page.locator('button[name="action"][value="download"]').first.scroll_into_view_if_needed()
            capture()
            with page.expect_download() as download_info:
                page.locator('button[name="action"][value="download"]').first.click()
            download_info.value.save_as(run_dir / "test-resume.docx")
            capture()
            browser.close()
        target = ROOT / "app" / "static" / "img" / "howto" / "student-upload-transcript-labelled.gif"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target = run_dir / target.name  # 重跑保留先前成品，不覆寫既有檔案。
        transcript_frames[0].save(target, save_all=True, append_images=transcript_frames[1:], duration=1500, loop=0, optimize=True)
        print(f"已錄製 {target}，{target.stat().st_size} 位元組")
        target = ROOT / "app" / "static" / "img" / "howto" / "student-import-attendance.gif"
        if target.exists():
            target = run_dir / target.name
        attendance_frames[0].save(target, save_all=True, append_images=attendance_frames[1:], duration=1500, loop=0, optimize=True)
        print(f"已錄製 {target}，{target.stat().st_size} 位元組")
        target = ROOT / "app" / "static" / "img" / "howto" / "student-target-gap-detail.gif"
        if target.exists():
            target = run_dir / target.name
        target_frames[0].save(target, save_all=True, append_images=target_frames[1:], duration=1500, loop=0, optimize=True)
        print(f"已錄製 {target}，{target.stat().st_size} 位元組")
        target = ROOT / "app" / "static" / "img" / "howto" / "student-autobiography-review.gif"
        if target.exists():
            target = run_dir / target.name
        autobiography_frames[0].save(target, save_all=True, append_images=autobiography_frames[1:], duration=1500, loop=0, optimize=True)
        print(f"已錄製 {target}，{target.stat().st_size} 位元組")
        target = ROOT / "app" / "static" / "img" / "howto" / "student-internship-resume-edit.gif"
        if target.exists():
            target = run_dir / target.name
        frames[0].save(target, save_all=True, append_images=frames[1:], duration=1500, loop=0, optimize=True)
        print(f"已錄製 {target}，{target.stat().st_size} 位元組")
    finally:
        server.shutdown()
        thread.join()


if __name__ == "__main__":
    main()
    if '--all' in sys.argv:
        import record_teacher_review_gif
        import record_staff_batch_gif
        import record_admin_account_gif
        import record_transfer_gifs
        for recorder in (record_teacher_review_gif, record_staff_batch_gif, record_admin_account_gif, record_transfer_gifs):
            recorder.main()




"""以隔離假資料錄製科助批次開立獎狀，只使用 5195。"""
import io
import os
import sys
import threading
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for key in ('AI_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'OPENAI_API_KEY', 'GOOGLE_OAUTH_CLIENT_ID', 'GOOGLE_OAUTH_CLIENT_SECRET'):
    os.environ[key] = ''
from PIL import Image
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from app import create_app
from app.extensions import db
from app.models import FormCategory, StudentProfile, User


def main():
    run_dir = ROOT / 'logs' / 'howto-recordings' / uuid.uuid4().hex
    run_dir.mkdir(parents=True)
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f"sqlite:///{(run_dir / 'demo.sqlite').as_posix()}",
                      'UPLOAD_FOLDER': str(run_dir / 'uploads'), 'TWO_FACTOR_REQUIRED': False,
                      'SESSION_COOKIE_NAME': 'howto_staff_5195'})
    with app.app_context():
        db.create_all()
        staff = User(username='demo-staff', display_name='測試科助', role='staff', job_title='科助')
        chief = User(username='demo-chief', display_name='測試主任', role='staff', job_title='主任')
        teacher = User(username='demo-teacher', display_name='測試導師', role='teacher')
        student = User(username='demo-student', display_name='測試學生', role='student')
        for user in (staff, chief, teacher, student):
            user.set_password('demo1234')
            db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=student.id, student_no='113000001', class_name='測試班', admission_year=113))
        db.session.add(FormCategory(name='測試分類', is_active=True))
        db.session.commit()
        teacher_id = teacher.id
    server = make_server('127.0.0.1', 5195, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    frames = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width': 720, 'height': 600})
            page.add_init_script("""localStorage.setItem('tour-declined','1'); document.addEventListener('DOMContentLoaded', () => {
              const label = document.createElement('div'); label.textContent = '僅為測試資料';
              label.style.cssText = 'position:fixed;bottom:0;left:0;z-index:99999;background:#fff;color:#111;padding:3px 8px;font-size:14px';
              document.body.appendChild(label);
            });""")
            def capture():
                page.wait_for_timeout(300)
                frames.append(Image.open(io.BytesIO(page.screenshot())).convert('RGB'))
            page.goto('http://127.0.0.1:5195/staff/login')
            page.locator('input[name="username"]').first.fill('demo-staff')
            page.locator('input[name="password"]').first.fill('demo1234')
            page.locator('input[name="password"]').first.press('Enter')
            page.goto('http://127.0.0.1:5195/staff/certificates/batch')
            page.locator('textarea[name="rows"]').fill('113000001,測試活動,協助活動,2026-11-01')
            page.locator('input[name="title"]').fill('測試活動證明')
            page.locator('textarea[name="rows"]').scroll_into_view_if_needed()
            capture()
            page.get_by_role('button', name='預覽名單').click()
            page.get_by_text('預覽：可以建立').first.wait_for()
            capture()
            page.get_by_role('button', name='確認建立', exact=False).click()
            page.get_by_text('等主任或副主任核准', exact=False).first.wait_for()
            capture()
            staff_frames = frames
            frames = []
            page.goto('http://127.0.0.1:5195/staff/forms')
            page.get_by_text('學校網站沒有的表單，才手動上架').click()
            form = page.locator('form[action="/staff/forms"]')
            form.locator('input[name="title"]').fill('測試申請表')
            pdf = io.BytesIO()
            Image.new('RGB', (200, 200), 'white').save(pdf, format='PDF')
            form.locator('input[name="file"]').set_input_files({'name': 'test-form.pdf', 'mimeType': 'application/pdf', 'buffer': pdf.getvalue()})
            form.scroll_into_view_if_needed()
            capture()
            form.get_by_role('button', name='上架', exact=True).click()
            page.wait_for_url('**/staff/forms/*')
            capture()
            form_frames = frames
            frames = []
            page.close()
            page = browser.new_page(viewport={'width': 720, 'height': 600})
            page.add_init_script("""localStorage.setItem('tour-declined','1'); document.addEventListener('DOMContentLoaded', () => {
              const label = document.createElement('div'); label.textContent = '僅為測試資料';
              label.style.cssText = 'position:fixed;bottom:0;left:0;z-index:99999;background:#fff;color:#111;padding:3px 8px;font-size:14px';
              document.body.appendChild(label);
            });""")
            page.goto('http://127.0.0.1:5195/staff/login')
            page.locator('input[name="username"]').first.fill('demo-chief')
            page.locator('input[name="password"]').first.fill('demo1234')
            page.locator('input[name="password"]').first.press('Enter')
            page.goto('http://127.0.0.1:5195/staff/forms')
            page.get_by_text('測試申請表', exact=True).first.scroll_into_view_if_needed()
            capture()
            page.locator('tr').filter(has_text='測試申請表').get_by_role('button', name='核准上架').click()
            page.wait_for_load_state('networkidle')
            capture()
            form_frames.extend(frames)
            frames = []
            page.goto('http://127.0.0.1:5195/staff/certificates')
            capture()
            page.get_by_role('link', name='審核').first.click()
            capture()
            page.get_by_role('button', name='核准並產出獎狀').scroll_into_view_if_needed()
            capture()
            page.get_by_role('button', name='核准並產出獎狀').click()
            page.wait_for_load_state('networkidle')
            capture()
            chief_certificate_frames = frames
            frames = []
            page.goto('http://127.0.0.1:5195/staff/classes')
            page.locator('select[name="teacher_id"]').select_option(str(teacher_id))
            page.locator('input[name="class_name"]').fill('測試班')
            page.locator('input[name="school_year"]').fill('115')
            capture()
            page.get_by_role('button', name='新增指派').click()
            page.wait_for_load_state('networkidle')
            capture()
            page.goto('http://127.0.0.1:5195/staff/students')
            capture()
            page.get_by_role('link', name='測試學生', exact=False).first.click()
            page.wait_for_load_state('networkidle')
            capture()
            browser.close()
        target = ROOT / 'app' / 'static' / 'img' / 'howto' / 'staff-batch-certificates.gif'
        if target.exists():
            target = run_dir / target.name
        staff_frames[0].save(target, save_all=True, append_images=staff_frames[1:], duration=1800, loop=0, optimize=True)
        print(f'已錄製 {target}，{target.stat().st_size} 位元組')
        target = ROOT / 'app' / 'static' / 'img' / 'howto' / 'chief-approve-certificate.gif'
        if target.exists():
            target = run_dir / target.name
        chief_certificate_frames[0].save(target, save_all=True, append_images=chief_certificate_frames[1:], duration=1800, loop=0, optimize=True)
        print(f'已錄製 {target}，{target.stat().st_size} 位元組')
        target = ROOT / 'app' / 'static' / 'img' / 'howto' / 'chief-class-and-students.gif'
        if target.exists():
            target = run_dir / target.name
        frames[0].save(target, save_all=True, append_images=frames[1:], duration=1800, loop=0, optimize=True)
        print(f'已錄製 {target}，{target.stat().st_size} 位元組')
        target = ROOT / 'app' / 'static' / 'img' / 'howto' / 'staff-publish-form.gif'
        if target.exists():
            target = run_dir / target.name
        form_frames[0].save(target, save_all=True, append_images=form_frames[1:], duration=1800, loop=0, optimize=True)
        print(f'已錄製 {target}，{target.stat().st_size} 位元組')
    finally:
        server.shutdown()
        thread.join()


if __name__ == '__main__':
    main()

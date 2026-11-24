"""用獨立假資料錄製轉科送核、退回、重送與結案；僅用 5195。"""
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
from app.models import StudentProfile, User


def main():
    run_dir = ROOT / 'logs' / 'howto-recordings' / uuid.uuid4().hex
    run_dir.mkdir(parents=True)
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f"sqlite:///{(run_dir / 'demo.sqlite').as_posix()}",
                      'UPLOAD_FOLDER': str(run_dir / 'uploads'), 'TWO_FACTOR_REQUIRED': False,
                      'ADMIN_TWO_FACTOR_REQUIRED': False, 'SESSION_COOKIE_NAME': 'howto_transfer_5195'})
    with app.app_context():
        db.create_all()
        admin = User(username='demo-admin', display_name='測試管理員', role='admin')
        staff = User(username='demo-staff', display_name='測試科助', role='staff', job_title='科助')
        chief = User(username='demo-chief', display_name='測試主任', role='staff', job_title='主任')
        student = User(username='demo-student', display_name='測試學生', role='student')
        for user in (admin, staff, chief, student):
            user.set_password('demo1234')
            db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=student.id, student_no='113000001', class_name='測試原班', admission_year=113))
        db.session.commit()
    server = make_server('127.0.0.1', 5195, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    admin_frames, staff_frames, chief_frames = [], [], []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge', headless=True)
            def login(role):
                page = browser.new_page(viewport={'width': 720, 'height': 600})
                page.add_init_script("""localStorage.setItem('tour-declined','1'); document.addEventListener('DOMContentLoaded', () => {
                  const label = document.createElement('div'); label.textContent = '僅為測試資料';
                  label.style.cssText = 'position:fixed;bottom:0;left:0;z-index:99999;background:#fff;color:#111;padding:3px 8px;font-size:14px';
                  document.body.appendChild(label);
                });""")
                page.goto('http://127.0.0.1:5195/' + ('admin/login' if role == 'admin' else 'staff/login'))
                page.locator('input[name="username"]').first.fill('demo-' + role)
                page.locator('input[name="password"]').first.fill('demo1234')
                page.locator('input[name="password"]').first.press('Enter')
                return page
            def capture(page, frames):
                page.wait_for_timeout(300)
                frames.append(Image.open(io.BytesIO(page.screenshot())).convert('RGB'))
            page = login('admin')
            page.goto('http://127.0.0.1:5195/admin/transfer-reviews')
            page.locator('input[name="student_no"]').fill('113000001')
            capture(page, admin_frames)
            page.get_by_role('button', name='查詢').click()
            page.locator('input[name="class_name"]').first.fill('測試新班')
            page.locator('input[name="admission_year"]').first.fill('113')
            capture(page, admin_frames)
            page.get_by_role('button', name='送科助核對').scroll_into_view_if_needed()
            capture(page, admin_frames)
            page.get_by_role('button', name='送科助核對').click()
            page.wait_for_load_state('networkidle')
            page.locator('#case-1').scroll_into_view_if_needed()
            capture(page, admin_frames)
            page.close()
            page = login('staff')
            page.goto('http://127.0.0.1:5195/staff/transfer-reviews')
            page.locator('input[name="reason"]').first.fill('測試：請更正班級。')
            page.locator('input[name="reason"]').first.scroll_into_view_if_needed()
            capture(page, staff_frames)
            page.get_by_role('button', name='退回管理員').click()
            page.wait_for_load_state('networkidle')
            capture(page, staff_frames)
            page.close()
            page = login('admin')
            page.goto('http://127.0.0.1:5195/admin/transfer-reviews')
            page.locator('input[name="class_name"]').last.fill('測試三甲')
            page.get_by_role('button', name='更正並重送科助').scroll_into_view_if_needed()
            capture(page, admin_frames)
            page.get_by_role('button', name='更正並重送科助').click()
            page.wait_for_load_state('networkidle')
            page.locator('#case-1').scroll_into_view_if_needed()
            capture(page, admin_frames)
            page.close()
            page = login('staff')
            page.goto('http://127.0.0.1:5195/staff/transfer-reviews')
            page.get_by_role('button', name='核對無誤，送主任').scroll_into_view_if_needed()
            capture(page, staff_frames)
            page.get_by_role('button', name='核對無誤，送主任').click()
            page.wait_for_load_state('networkidle')
            capture(page, staff_frames)
            page.close()
            page = login('chief')
            page.goto('http://127.0.0.1:5195/staff/transfer-reviews')
            page.get_by_role('button', name='確認並結案').scroll_into_view_if_needed()
            capture(page, chief_frames)
            page.get_by_role('button', name='確認並結案').click()
            page.wait_for_load_state('networkidle')
            capture(page, chief_frames)
            browser.close()
        for name, frames in [('admin-transfer-review-clear.gif', admin_frames), ('staff-transfer-return.gif', staff_frames), ('chief-transfer-close.gif', chief_frames)]:
            target = ROOT / 'app' / 'static' / 'img' / 'howto' / name
            if target.exists():
                target = run_dir / name
            frames[0].save(target, save_all=True, append_images=frames[1:], duration=1800, loop=0, optimize=True)
            print(f'已錄製 {target}，{target.stat().st_size} 位元組')
    finally:
        server.shutdown()
        thread.join()


if __name__ == '__main__':
    main()

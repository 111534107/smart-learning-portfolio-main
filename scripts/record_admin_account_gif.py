"""用隔離假資料錄製管理員新增帳號，只監聽 5195。"""
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
from app.models import User


def main():
    run_dir = ROOT / 'logs' / 'howto-recordings' / uuid.uuid4().hex
    run_dir.mkdir(parents=True)
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f"sqlite:///{(run_dir / 'demo.sqlite').as_posix()}",
                      'UPLOAD_FOLDER': str(run_dir / 'uploads'), 'TWO_FACTOR_REQUIRED': False,
                      'ADMIN_TWO_FACTOR_REQUIRED': False, 'SESSION_COOKIE_NAME': 'howto_admin_5195'})
    with app.app_context():
        db.create_all()
        admin = User(username='demo-admin', display_name='測試管理員', role='admin')
        admin.set_password('demo1234')
        db.session.add(admin)
        db.session.commit()
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
            page.goto('http://127.0.0.1:5195/admin/login')
            page.locator('input[name="username"]').first.fill('demo-admin')
            page.locator('input[name="password"]').first.fill('demo1234')
            page.locator('input[name="password"]').first.press('Enter')
            page.goto('http://127.0.0.1:5195/admin/accounts#staff-create')
            form = page.locator('#staff-create form')
            form.locator('select[name="role"]').select_option('teacher')
            form.locator('select[name="job_title"]').select_option('')
            form.locator('input[name="display_name"]').fill('測試導師')
            form.locator('input[name="username"]').fill('test-teacher')
            form.locator('input[name="password"]').fill('Test12345678')
            form.scroll_into_view_if_needed()
            capture()
            form.get_by_role('button', name='建立帳號').scroll_into_view_if_needed()
            capture()
            form.get_by_role('button', name='建立帳號').click()
            page.get_by_text('已建立 測試導師', exact=False).wait_for()
            capture()
            browser.close()
        target = ROOT / 'app' / 'static' / 'img' / 'howto' / 'admin-create-teacher.gif'
        if target.exists():
            target = run_dir / target.name
        frames[0].save(target, save_all=True, append_images=frames[1:], duration=1800, loop=0, optimize=True)
        print(f'已錄製 {target}，{target.stat().st_size} 位元組')
    finally:
        server.shutdown()
        thread.join()


if __name__ == '__main__':
    main()

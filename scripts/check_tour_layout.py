"""用獨立假資料在 5195 檢查學生、導師導覽卡是否超出視窗。"""
import os
import sys
import threading
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for key in ("AI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
    os.environ[key] = ""

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from app import create_app
from app.extensions import db
from app.models import AuditLog, ClassAdvisor, StudentProfile, User


def main():
    run_dir = ROOT / 'logs' / 'tour-layout' / uuid.uuid4().hex
    run_dir.mkdir(parents=True)
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f"sqlite:///{(run_dir / 'demo.sqlite').as_posix()}",
                      'UPLOAD_FOLDER': str(run_dir / 'uploads'), 'TWO_FACTOR_REQUIRED': False, 'ADMIN_TWO_FACTOR_REQUIRED': False,
                      'SESSION_COOKIE_NAME': 'tour_layout_5195'})
    with app.app_context():
        db.create_all()
        student = User(username='layout-student', display_name='測試學生', role='student')
        teacher = User(username='layout-teacher', display_name='測試導師', role='teacher')
        staff = User(username='layout-staff', display_name='測試科助', role='staff', job_title='科助')
        chief = User(username='layout-chief', display_name='測試主任', role='staff', job_title='主任')
        admin = User(username='layout-admin', display_name='測試管理員', role='admin')
        for user in (student, teacher, staff, chief, admin):
            user.set_password('demo1234')
            db.session.add(user)
        db.session.flush()
        db.session.add_all([StudentProfile(user_id=student.id, student_no='T0001', class_name='測試班', admission_year=113),
                            ClassAdvisor(teacher_id=teacher.id, class_name='測試班', school_year=115),
                            AuditLog(user_id=student.id, action='student.welcome_done')])
        db.session.commit()
        student_id = student.id
    server = make_server('127.0.0.1', 5195, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge', headless=True)
            for width in (375, 1280):
                for role, routes in [('student', ['/student/search', '/student/pathways']),
                                     ('teacher', ['/teacher/dashboard', f'/teacher/students/{student_id}']),
                                     ('staff', ['/staff/forms', '/staff/certificates/batch']),
                                     ('chief', ['/staff/classes', '/staff/students']),
                                     ('admin', ['/admin/accounts', '/admin/ai'])]:
                    page = browser.new_page(viewport={'width': width, 'height': 800}, reduced_motion='reduce')
                    page.goto('http://127.0.0.1:5195/' + ('login' if role == 'student' else 'admin/login' if role == 'admin' else 'staff/login'))
                    if role == 'student':
                        page.locator('details.auth__fallback summary').click()
                    page.locator('input[name="username"]').first.fill('layout-' + role)
                    page.locator('input[name="password"]').first.fill('demo1234')
                    page.locator('input[name="password"]').first.press('Enter')
                    for route in routes:
                        page.goto('http://127.0.0.1:5195' + route + '?tour=1')
                        page.locator('.tour__card').wait_for()
                        count = 0
                        while page.locator('.tour__card').count():
                            page.wait_for_timeout(450)
                            box = page.locator('.tour__card').bounding_box()
                            assert box and box['x'] >= 0 and box['y'] >= 0 and box['x'] + box['width'] <= width and box['y'] + box['height'] <= 800, (role, route, width, box)
                            overlap = page.evaluate('''() => {
                              const text = document.querySelector('.tour__text').textContent;
                              const target = [...document.querySelectorAll('[data-tour]')].find(el => el.dataset.tour === text && el.getClientRects().length);
                              if (!target || !target.matches('button, a, input, select')) return false;
                              const a = target.getBoundingClientRect(), b = document.querySelector('.tour__card').getBoundingClientRect();
                              return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
                            }''')
                            assert not overlap, (role, route, width, '說明卡遮住目標按鈕')
                            count += 1
                            page.locator('[data-tour-next]').click()
                        assert count >= 2, (role, route, width, count)
                        print(f'{role} {route} {width}px：{count} 步，說明卡在視窗內')
                    page.close()
            browser.close()
    finally:
        server.shutdown()
        thread.join()


if __name__ == '__main__':
    main()

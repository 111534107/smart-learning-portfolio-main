import re

from app import create_app
from app.extensions import db
from app.models import User


def test_expired_login_form_is_rejected_and_offers_fresh_form():
    app = create_app({'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:', 'TESTING': False,
                      'CSRF_ENABLED': True, 'OCR_QUEUE_MODE': 'inline'})
    with app.app_context():
        db.create_all()
        teacher = User(username='teacher', display_name='Teacher', role='teacher')
        teacher.set_password('pw')
        db.session.add(teacher)
        db.session.commit()
    client = app.test_client()
    response = client.post('/login', data={'username': 'teacher', 'password': 'pw'})
    assert response.status_code == 400
    assert client.post('/logout').status_code == 400
    original = client.get('/login').get_data(as_text=True)
    old_token = re.search(r'name="csrf_token" value="([^"]+)"', original).group(1)
    with client.session_transaction() as session:
        session.clear()
    response = client.post('/login', data={'username': 'teacher', 'password': 'pw', 'csrf_token': old_token})
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert '登入頁已過期' in html
    assert 'name="csrf_token"' in html
    with client.session_transaction() as session:
        assert 'user_id' not in session
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    response = client.post('/login', data={'username': 'teacher', 'password': 'pw', 'csrf_token': token})
    assert response.status_code == 302
    assert response.location.endswith('/teacher/dashboard')


def test_stale_logout_form_shows_current_account_and_requires_new_confirmation():
    app = create_app({'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:', 'TESTING': False,
                      'CSRF_ENABLED': True, 'OCR_QUEUE_MODE': 'inline'})
    with app.app_context():
        db.create_all()
        first = User(username='first', display_name='第一位', role='student')
        second = User(username='second', display_name='第二位', role='student')
        first.set_password('pw')
        second.set_password('pw')
        db.session.add_all([first, second])
        db.session.commit()
        second_id = second.id
    client = app.test_client()
    client.get('/login')
    with client.session_transaction() as session:
        stale_token = session['csrf_token']
        session.clear()
        session['user_id'] = second_id
        session['csrf_token'] = 'new-session-token'
    response = client.post('/logout', data={'csrf_token': stale_token})
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert '登入狀態已更新' in html
    assert '第二位' in html
    with client.session_transaction() as session:
        assert session['user_id'] == second_id
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    assert client.post('/logout', data={'csrf_token': token}).status_code == 302
    with client.session_transaction() as session:
        assert 'user_id' not in session

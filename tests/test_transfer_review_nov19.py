import pytest
from app import create_app
from app.extensions import db
from app.models import User, StudentProfile

@pytest.fixture
def site(tmp_path):
    app = create_app({'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:', 'TESTING':True, 'UPLOAD_FOLDER':str(tmp_path / 'up')})
    with app.app_context():
        db.create_all()
        for name, role, title in [('admin','admin',None),('assist','staff','科助'),('chief','staff','主任'),('vice','staff','副主任'),('clerk','staff','其他')]:
            u = User(username=name, display_name=name, role=role, job_title=title); u.set_password('pw'); db.session.add(u)
        s = User(username='existing', display_name='測試學生', role='student'); s.set_password('pw'); db.session.add(s); db.session.flush()
        db.session.add(StudentProfile(user_id=s.id,student_no='113534991',class_name='原班',admission_year=113)); db.session.commit()
    return app

def login(app, name):
    c=app.test_client(); c.post('/admin/login' if name == 'admin' else '/staff/login',data={'username':name,'password':'pw'}); return c

def case_post(client, cid, action, data=None):
    from app.models import TransferReviewCase
    with client.application.app_context():
        version = db.session.get(TransferReviewCase, cid).version
    path = 'admin' if action == 'resubmit' else 'staff'
    return client.post(f'/{path}/transfer-reviews/{cid}/{action}', data={**(data or {}), 'version': str(version)})

def test_transfer_review_round_trip_and_permissions(site):
    admin, assist, chief, clerk = [login(site, n) for n in ('admin','assist','chief','clerk')]
    assert assist.post('/staff/transfer-students',data={}).status_code == 403
    assert clerk.get('/staff/transfer-reviews').status_code == 403
    assert assist.get('/staff/students').status_code == 403
    assert admin.post('/admin/transfer-reviews',data={'student_no':'113534991','class_name':'新班','admission_year':'114'}).status_code == 302
    from app.models import TransferReviewCase, TransferReviewEvent
    with site.app_context():
        case=TransferReviewCase.query.one(); cid=case.id; assert case.student.username=='existing'; assert case.status=='assistant_pending'; assert case.student.student_profile.class_name=='原班'
    assert case_post(chief,cid,'confirm').status_code == 409
    assert case_post(assist,cid,'return',{'reason':'請更正'}).status_code == 302
    assert case_post(admin,cid,'resubmit',{'class_name':'更正班','admission_year':'114'}).status_code == 302
    assert case_post(assist,cid,'confirm').status_code == 302
    assert case_post(assist,cid,'confirm').status_code == 409
    assert case_post(chief,cid,'confirm').status_code == 302
    with site.app_context():
        case=db.session.get(TransferReviewCase,cid); assert case.status=='closed'; assert case.student.student_profile.class_name=='更正班'; assert TransferReviewEvent.query.filter_by(case_id=cid).count()==5
    assert case_post(admin,cid,'resubmit',{'class_name':'另案','admission_year':'115'}).status_code == 409



def test_create_duplicate_and_chief_return_history(site):
    from app.models import TransferReviewCase, TransferReviewEvent, AuditLog, TransferCreditRecord
    admin, assist, chief = [login(site,n) for n in ('admin','assist','chief')]
    form={'student_no':'114534901','display_name':'測試新生','class_name':'甲班','admission_year':'114','password':'Synthetic98765'}
    assert admin.get('/admin/transfer-reviews?student_no=114534901').status_code==200
    assert admin.post('/admin/transfer-reviews',data=form).status_code==302
    assert admin.post('/admin/transfer-reviews',data={**form}).status_code==400
    with site.app_context():
        u=User.query.filter_by(username='114534901').one(); cid=TransferReviewCase.query.one().id
        assert u.check_password(form['password']); assert User.query.filter_by(username='114534901').count()==1
        assert TransferCreditRecord.query.filter_by(student_id=u.id).count()==0
        assert form['password'] not in str([a.detail_json for a in AuditLog.query.all()])
    assert case_post(assist,cid,'confirm').status_code==302
    assert case_post(chief,cid,'return',{'reason':'資料錯誤'}).status_code==302
    assert case_post(admin,cid,'resubmit',{'class_name':'乙班','admission_year':'115'}).status_code==302
    with site.app_context():
        c=db.session.get(TransferReviewCase,cid); assert c.assistant_id is None and c.chief_id is None
        assert [(e.action,e.class_name) for e in c.events]==[('submitted','甲班'),('confirm','甲班'),('return','甲班'),('resubmit','乙班')]
    assert case_post(assist,cid,'confirm').status_code==302
    assert case_post(chief,cid,'confirm').status_code==302
    assert admin.post('/admin/transfer-reviews',data={**form,'class_name':'丙班'}).status_code==302
    with site.app_context():
        cases=TransferReviewCase.query.order_by(TransferReviewCase.id).all(); assert len(cases)==2 and cases[1].previous_case_id==cases[0].id
        assert cases[0].status=='closed' and cases[0].class_name=='乙班'
        assert form['password'] not in str([(e.reason,e.class_name) for e in TransferReviewEvent.query.all()])

def test_permissions_and_required_reason(site):
    admin, assist, chief, vice, clerk=[login(site,n) for n in ('admin','assist','chief','vice','clerk')]
    assert admin.post('/admin/transfer-reviews',data={'student_no':'113534991','class_name':'甲','admission_year':'114'}).status_code==302
    from app.models import TransferReviewCase
    with site.app_context(): cid=TransferReviewCase.query.one().id
    assert case_post(assist,cid,'return',{}).status_code==400
    assert case_post(clerk,cid,'confirm').status_code==403
    assert case_post(vice,cid,'confirm').status_code==409
    assert case_post(assist,cid,'confirm').status_code==302
    assert case_post(vice,cid,'confirm').status_code==302

def test_migration_upgrade_and_downgrade():
    import importlib.util
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    spec=importlib.util.spec_from_file_location('transfer_migration','migrations/versions/f20261119a01_transfer_review.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    engine=sa.create_engine('sqlite:///:memory:')
    with engine.begin() as connection:
        connection.execute(sa.text('CREATE TABLE users (id INTEGER PRIMARY KEY)'))
        module.op=Operations(MigrationContext.configure(connection))
        module.upgrade()
        assert {'transfer_review_cases','transfer_review_events'} <= set(sa.inspect(connection).get_table_names())
        assert {'class_name','admission_year','reason'} <= {c['name'] for c in sa.inspect(connection).get_columns('transfer_review_events')}
        module.downgrade()
        assert 'transfer_review_cases' not in sa.inspect(connection).get_table_names()


def test_simultaneous_confirm_only_one_succeeds(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.models import TransferReviewCase, TransferReviewEvent
    path=(tmp_path / 'concurrent.sqlite').as_posix()
    app=create_app({'SQLALCHEMY_DATABASE_URI':f'sqlite:///{path}', 'TESTING':True})
    with app.app_context():
        db.create_all()
        for name,role,title in [('a','staff','科助'),('b','staff','科助'),('student','student',None)]:
            u=User(username=name,display_name=name,role=role,job_title=title); u.set_password('pw'); db.session.add(u)
        db.session.flush(); student=User.query.filter_by(username='student').one()
        db.session.add(StudentProfile(user_id=student.id,student_no='SYN123',class_name='甲',admission_year=114))
        case=TransferReviewCase(student_id=student.id,status='assistant_pending',open_key=student.id,class_name='甲',admission_year=114)
        db.session.add(case); db.session.commit(); cid=case.id
    clients=[login(app,'a'),login(app,'b')]; barrier=Barrier(2)
    def confirm(client):
        barrier.wait(); return case_post(client,cid,'confirm').status_code
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(confirm,clients))
    assert sorted(results)==[302,409]
    with app.app_context():
        assert db.session.get(TransferReviewCase,cid).status=='chief_pending'
        assert TransferReviewEvent.query.filter_by(case_id=cid,action='confirm').count()==1

def test_simultaneous_new_account_is_unique(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.models import TransferReviewCase
    path=(tmp_path / 'accounts.sqlite').as_posix()
    app=create_app({'SQLALCHEMY_DATABASE_URI':f'sqlite:///{path}', 'TESTING':True})
    with app.app_context():
        db.create_all()
        for name in ('admin','admin2'):
            u=User(username=name,display_name=name,role='admin'); u.set_password('pw'); db.session.add(u)
        db.session.commit()
    clients=[]
    for name in ('admin','admin2'):
        c=app.test_client(); c.post('/admin/login',data={'username':name,'password':'pw'}); clients.append(c)
    barrier=Barrier(2)
    def submit(pair):
        c,number=pair; barrier.wait()
        return c.post('/admin/transfer-reviews',data={'student_no':number,'display_name':'測試','class_name':'甲','admission_year':'114','password':'Synthetic98765'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool: result=list(pool.map(submit,zip(clients,('114534777','114534777'))))
    assert sorted(result)==[302,400]
    with app.app_context():
        assert User.query.filter_by(username='114534777').count()==1
        assert StudentProfile.query.filter_by(student_no='114534777').count()==1
        assert TransferReviewCase.query.count()==1
def test_review_pages_render_minimal_data(site):
    admin, assist, chief = [login(site,n) for n in ('admin','assist','chief')]
    assert admin.post('/admin/transfer-reviews',data={'student_no':'113534991','class_name':'甲班','admission_year':'114'}).status_code == 302
    page=admin.get('/admin/transfer-reviews').get_data(as_text=True)
    assert '待科助核對' in page and '113534991' in page
    page=assist.get('/staff/transfer-reviews').get_data(as_text=True)
    assert '待科助核對' in page and '113534991' in page
    waiting_for_assistant = chief.get('/staff/transfer-reviews').get_data(as_text=True)
    assert '113534991' in waiting_for_assistant and '待科助核對' in waiting_for_assistant
    assert '/confirm"' not in waiting_for_assistant
    # 科助和主任都只能核對案件，不能直接向管理員入口新增轉學生名單。
    for clerk in (assist, chief):
        forbidden = clerk.post('/admin/transfer-reviews', data={
            'student_no': '114534999', 'display_name': '合成驗收',
            'class_name': '測試班', 'admission_year': '114', 'password': 'Synthetic9382',
        })
        assert forbidden.status_code == 403
        assert clerk.post('/staff/transfer-students', data={'student_no': '114534999'}).status_code == 403
    from app.models import TransferReviewCase
    with site.app_context(): cid=TransferReviewCase.query.one().id
    assert case_post(assist,cid,'confirm').status_code==302
    assert '待主任確認' in chief.get('/staff/transfer-reviews').get_data(as_text=True)

def test_stale_review_from_previous_round_cannot_confirm(site):
    from app.models import TransferReviewCase
    admin, assist = [login(site,n) for n in ('admin','assist')]
    admin.post('/admin/transfer-reviews',data={'student_no':'113534991','class_name':'甲','admission_year':'114'})
    with site.app_context(): cid=TransferReviewCase.query.one().id
    assist.post(f'/staff/transfer-reviews/{cid}/return',data={'reason':'更正','version':'1'})
    admin.post(f'/admin/transfer-reviews/{cid}/resubmit',data={'class_name':'乙','admission_year':'115','version':'2'})
    assert assist.post(f'/staff/transfer-reviews/{cid}/confirm',data={'version':'1'}).status_code==409


def test_transfer_notifications_and_wrong_account_withdrawal(site):
    from app.models import Notification, TransferReviewCase

    admin, assistant, chief = [login(site, name) for name in ('admin', 'assist', 'chief')]
    assert admin.post('/admin/transfer-reviews', data={
        'student_no': '113534991', 'class_name': '假資料測試班', 'admission_year': '114',
    }).status_code == 302
    with site.app_context():
        case = TransferReviewCase.query.one()
        case_id, version = case.id, case.version
        notes = Notification.query.filter(Notification.notify_key.like('transfer_review:%')).all()
        assert {n.recipient.username for n in notes} == {'assist', 'chief', 'vice'}
        assert all(n.link == f'/staff/transfer-reviews#case-{case_id}' for n in notes)
        assert all('113534991' not in n.message and '假資料測試班' not in n.message for n in notes)
    url = f'/admin/transfer-reviews/{case_id}/withdraw'
    data = {'reason': '合成驗收：學號對錯人', 'version': str(version)}
    assert chief.post(url, data=data).status_code == 403
    assert admin.post(url, data={**data, 'reason': ''}).status_code == 400
    assert admin.post(url, data=data).status_code == 302
    assert case_post(assistant, case_id, 'confirm').status_code == 409
    with site.app_context():
        case = db.session.get(TransferReviewCase, case_id)
        assert case.status == 'withdrawn' and case.open_key is None
        assert case.student.student_profile.class_name == '原班'
        assert [(event.action, event.reason) for event in case.events][-1] == ('withdraw', data['reason'])


@pytest.mark.parametrize('number', ['T1199001', '11353490', '1135349012', 'abc534901'])
def test_student_number_must_be_nine_digits(site, number):
    """學校學號一律 9 碼數字；其他格式查詢與建帳都拒絕，也不會偷偷改成小寫建立。"""
    admin = login(site, 'admin')
    page = admin.get(f'/admin/transfer-reviews?student_no={number}')
    assert page.status_code == 400 and '9 碼數字' in page.get_data(as_text=True)
    created = admin.post('/admin/transfer-reviews', data={'student_no': number, 'display_name': '測試', 'class_name': '甲',
                                                         'admission_year': '114', 'password': 'Synthetic98765'})
    assert created.status_code == 400
    with site.app_context():
        assert User.query.filter_by(username=number).count() == 0
        assert User.query.filter_by(username=number.lower()).count() == 0

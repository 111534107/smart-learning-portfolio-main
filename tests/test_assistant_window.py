"""共用小助手視窗：角色保持一致，對話介面仍使用原送出路徑。"""
import pytest
from tests.test_assistant import app

@pytest.mark.parametrize('name,path', [('stu','/student/learning-profile'), ('teacher','/teacher/dashboard')])
def test_student_and_teacher_receive_accessible_dialog_controls(app, name, path):
    client=app.test_client()
    client.post('/login',data={'username':name,'password':'pw'})
    page=client.get(path).get_data(as_text=True)
    assert page.count('id="assistant-panel"') == 1
    assert 'role="dialog" aria-modal="true"' in page
    assert 'data-assistant-reset' in page and 'data-assistant-expand' in page
    assert 'js/assistant-window.js' in page
    assert 'data-assistant-form' in page and 'maxlength="1500"' in page

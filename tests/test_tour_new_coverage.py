from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[1] / 'app' / 'templates'

def test_review_and_teacher_edit_have_action_specific_tours():
    expected = {
        'learning_profile_review.html': ['對照原始文件核對辨識內容', '確認無誤後儲存'],
        'teacher_autobiography_edit.html': ['修改段落內容', '新增段落留言', '儲存成新版本'],
        'student_graduation_check.html': ['查看校方標準', '查看目前進度', '依建議完成下一步'],
        'teacher_internship_resume.html': ['查看學生填寫的基本資料', '查看自傳與所選資料'],
        'student_transfer_plans.html': ['拖曳考科進度條', '儲存進度', '新增考試準備計畫'],
        'student_agent_issues.html': ['切換進行中或已完成', '依標籤篩選待辦', '標記完成或重新開啟'],
        'student_agent_proposal.html': ['查看小助手會讀取的資料', '確認將建立的待辦', '才會建立待辦'],
    }
    for name, phrases in expected.items():
        text = (TEMPLATES / name).read_text(encoding='utf-8')
        for phrase in phrases:
            assert phrase in text, (name, phrase)

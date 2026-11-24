from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_specific_tours_for_search_review_and_versions():
    for name in ('student_search.html', 'review_queue.html', 'autobiography_versions.html'):
        text = (ROOT / 'app' / 'templates' / name).read_text(encoding='utf-8')
        assert text.count('data-tour=') >= 2, name


def test_search_has_two_steps_before_results_exist():
    text = (ROOT / 'app' / 'templates' / 'student_search.html').read_text(encoding='utf-8')
    assert text.index('data-tour-order="2"') < text.index('{% if q %}')


def test_pathway_and_package_pages_explain_their_controls():
    for name in ('student_pathways.html', 'student_package_exclusions.html'):
        text = (ROOT / 'app' / 'templates' / name).read_text(encoding='utf-8')
        assert text.count('data-tour=') >= 2, name


def test_processing_and_agent_run_explain_status_and_next_steps():
    for name in ('learning_profile_processing.html', 'student_agent_run.html'):
        text = (ROOT / 'app' / 'templates' / name).read_text(encoding='utf-8')
        assert text.count('data-tour=') >= 2, name


def test_agent_hub_navigation_has_specific_guidance():
    text = (ROOT / 'app' / 'templates' / 'partials' / 'agent_hub.html').read_text(encoding='utf-8')
    assert text.count('data-tour=') >= 2


def test_teacher_review_help_animation_is_available():
    from app.content.help import HELP
    item = next(item for section in HELP['teacher'] for item in section['items']
                if item['q'] == '怎麼確認學生的備審？')
    assert item['gif_alt']
    path = ROOT / 'app' / 'static' / 'img' / 'howto' / item['gif']
    assert path.is_file() and path.stat().st_size < 3 * 1024 * 1024


def test_attendance_help_animation_is_available():
    from app.content.help import HELP
    item = next(item for section in HELP['student'] for item in section['items']
                if item['q'] == '怎麼匯入缺曠記錄？')
    assert item['gif_alt']
    path = ROOT / 'app' / 'static' / 'img' / 'howto' / item['gif']
    assert path.is_file() and path.stat().st_size < 3 * 1024 * 1024


def test_resume_help_animation_is_available():
    from app.content.help import HELP
    item = next(item for section in HELP['student'] for item in section['items']
                if item['q'] == '怎麼編輯及下載實習履歷？')
    assert item['gif_alt']
    path = ROOT / 'app' / 'static' / 'img' / 'howto' / item['gif']
    assert path.is_file() and path.stat().st_size < 3 * 1024 * 1024


def test_agent_lists_explain_opening_items():
    for name in ('student_agent_activity.html', 'student_agent_proposals.html'):
        text = (ROOT / 'app' / 'templates' / name).read_text(encoding='utf-8')
        assert 'data-tour-order="3"' in text


def test_target_help_animation_is_available():
    from app.content.help import HELP
    item = next(item for section in HELP['student'] for item in section['items']
                if item['q'] == '怎麼加入目標並查看缺件？')
    assert item['gif_alt']
    path = ROOT / 'app' / 'static' / 'img' / 'howto' / item['gif']
    assert path.is_file() and path.stat().st_size < 3 * 1024 * 1024


def test_autobiography_help_animation_is_available():
    from app.content.help import HELP
    item = next(item for section in HELP['student'] for item in section['items']
                if item['q'] == '怎麼寫自傳並送導師確認？')
    assert item['gif_alt']
    path = ROOT / 'app' / 'static' / 'img' / 'howto' / item['gif']
    assert path.is_file() and path.stat().st_size < 3 * 1024 * 1024


def test_award_and_analysis_pages_have_action_guidance():
    for name in ('award_upload.html', 'award_review.html', 'student_project_analysis.html', 'student_review_result.html'):
        text = (ROOT / 'app' / 'templates' / name).read_text(encoding='utf-8')
        assert text.count('data-tour=') >= 2, name


def test_discipline_page_explains_retained_records():
    text = (ROOT / 'app' / 'templates' / 'award_discipline.html').read_text(encoding='utf-8')
    assert text.count('data-tour=') >= 2


def test_teacher_summary_and_attendance_have_specific_guidance():
    summary = (ROOT / 'app' / 'templates' / 'teacher_class_summary.html').read_text(encoding='utf-8')
    attendance = (ROOT / 'app' / 'templates' / 'attendance_import.html').read_text(encoding='utf-8')
    assert summary.count('data-tour=') >= 2
    assert '選擇學年期範圍' in attendance


def test_autobiography_guides_manual_edit_and_save():
    text = (ROOT / 'app' / 'templates' / 'student_autobiography.html').read_text(encoding='utf-8')
    assert '選擇下一題或自己寫草稿' in text
    assert '改成自己的文字，完成後儲存' in text


def test_targets_page_explains_tracks_and_selected_programs():
    text = (ROOT / 'app' / 'templates' / 'student_targets.html').read_text(encoding='utf-8')
    assert '切換二技或插大' in text
    assert '點已選校系查看缺件' in text
    assert 'data-tour-order="0"' not in text


def test_portfolio_guides_filters_and_records():
    text = (ROOT / 'app' / 'templates' / 'student_portfolio.html').read_text(encoding='utf-8')
    assert '依年級或類別篩選' in text
    assert '點紀錄卡片編輯' in text


def test_all_help_animations_have_accessible_text_and_fit_limits():
    from PIL import Image
    from app.content.help import HELP
    for sections in HELP.values():
        for section in sections:
            for item in section['items']:
                if 'gif' not in item:
                    continue
                path = ROOT / 'app' / 'static' / 'img' / 'howto' / item['gif']
                assert item.get('gif_alt') and path.is_file()
                assert path.stat().st_size < 3 * 1024 * 1024
                with Image.open(path) as gif:
                    assert gif.width <= 720
                    duration = 0
                    for index in range(gif.n_frames):
                        gif.seek(index)
                        duration += gif.info.get('duration', 0)
                    assert duration <= 15000


def test_staff_forms_have_task_specific_guidance():
    for name in ('staff_forms.html', 'staff_form_detail.html', 'staff_form_links.html'):
        text = (ROOT / 'app' / 'templates' / name).read_text(encoding='utf-8')
        assert text.count('data-tour=') >= 2, name


def test_admin_ai_announcements_and_audit_have_guidance():
    for name in ('admin_ai.html', 'admin_announcement_form.html', 'admin_announcements.html', 'admin_audit_logs.html'):
        text = (ROOT / 'app' / 'templates' / name).read_text(encoding='utf-8')
        assert text.count('data-tour=') >= 2, name


def test_admin_rules_and_integrations_have_guidance():
    for name in ('admin_course_rules.html', 'admin_curriculum.html', 'admin_google_workspace.html', 'admin_match_filters.html', 'admin_ocr.html'):
        text = (ROOT / 'app' / 'templates' / name).read_text(encoding='utf-8')
        assert text.count('data-tour=') >= 2, name


def test_admin_catalog_and_storage_have_guidance():
    for name in ('admin_agent.html', 'admin_programs.html', 'admin_rules.html', 'admin_schools.html', 'admin_storage.html', 'admin_storage_migration.html'):
        text = (ROOT / 'app' / 'templates' / name).read_text(encoding='utf-8')
        assert text.count('data-tour=') >= 2, name


def test_staff_certificates_students_and_activity_have_guidance():
    for name in ('staff_activity.html', 'staff_certificate_issue.html', 'staff_certificate_review.html', 'staff_certificates.html', 'staff_student_detail.html', 'staff_transfer_students.html'):
        text = (ROOT / 'app' / 'templates' / name).read_text(encoding='utf-8')
        assert text.count('data-tour=') >= 2, name


def test_staff_batch_help_animation_is_available():
    from app.content.help import HELP
    item = next(item for section in HELP['staff'] for item in section['items']
                if item['q'] == '怎麼批次開立電子獎狀？')
    assert item['gif_alt']
    path = ROOT / 'app' / 'static' / 'img' / 'howto' / item['gif']
    assert path.is_file() and path.stat().st_size < 3 * 1024 * 1024


def test_chief_certificate_help_animation_is_available():
    from app.content.help import HELP
    item = next(item for section in HELP['staff'] for item in section['items']
                if item['q'] == '怎麼核准電子獎狀？')
    assert item['gif_alt']
    path = ROOT / 'app' / 'static' / 'img' / 'howto' / item['gif']
    assert path.is_file() and path.stat().st_size < 3 * 1024 * 1024


def test_chief_class_help_animation_is_available():
    from app.content.help import HELP
    item = next(item for section in HELP['staff'] for item in section['items']
                if item['q'] == '主任怎麼指派班級並查看學生？')
    assert item['gif_alt']
    path = ROOT / 'app' / 'static' / 'img' / 'howto' / item['gif']
    assert path.is_file() and path.stat().st_size < 3 * 1024 * 1024


def test_admin_account_help_animation_is_available():
    from app.content.help import HELP
    item = next(item for section in HELP['admin'] for item in section['items']
                if item['q'] == '怎麼建立教職員帳號？')
    assert item['gif_alt']
    path = ROOT / 'app' / 'static' / 'img' / 'howto' / item['gif']
    assert path.is_file() and path.stat().st_size < 3 * 1024 * 1024


def test_staff_form_help_animation_is_available():
    from app.content.help import HELP
    item = next(item for section in HELP['staff'] for item in section['items']
                if item['q'] == '怎麼上架學校沒有的表單？')
    assert item['gif_alt']
    path = ROOT / 'app' / 'static' / 'img' / 'howto' / item['gif']
    assert path.is_file() and path.stat().st_size < 3 * 1024 * 1024


def test_transfer_reviews_explains_each_role_workflow():
    text = (ROOT / 'app' / 'templates' / 'transfer_reviews.html').read_text(encoding='utf-8')
    assert '先查九碼學號' in text
    assert '核對後確認或寫原因退回' in text


def test_transfer_help_animations_are_available():
    from app.content.help import HELP
    for role, question in [('admin', '怎麼送核及更正轉科案件？'), ('staff', '怎麼核對並退回轉科案件？'), ('staff', '主任怎麼確認轉科結案？')]:
        item = next(item for section in HELP[role] for item in section['items'] if item['q'] == question)
        assert item['gif_alt']
        path = ROOT / 'app' / 'static' / 'img' / 'howto' / item['gif']
        assert path.is_file() and path.stat().st_size < 3 * 1024 * 1024


def test_recording_entrypoint_can_run_all_role_recorders():
    text = (ROOT / 'scripts' / 'record_howto_gifs.py').read_text(encoding='utf-8')
    assert "'--all'" in text
    for name in ('record_teacher_review_gif', 'record_staff_batch_gif', 'record_admin_account_gif', 'record_transfer_gifs'):
        assert name in text


def test_shared_pages_have_specific_guidance():
    for name in ('account_password.html', 'announcements.html', 'announcement_detail.html', 'forms_list.html', 'notifications.html', 'grade_overview.html', 'graduation_case.html'):
        text = (ROOT / 'app' / 'templates' / name).read_text(encoding='utf-8')
        assert text.count('data-tour=') >= 2, name


def test_security_and_certificate_pages_explain_controls():
    for name in ('two_factor_account.html', 'two_factor_setup.html', 'two_factor_verify.html', 'two_factor_backup_codes.html', 'certificate_verify.html'):
        text = (ROOT / 'app' / 'templates' / name).read_text(encoding='utf-8')
        assert text.count('data-tour=') >= 2, name


def test_login_forms_explain_available_sign_in_methods():
    text = (ROOT / 'app' / 'templates' / 'partials' / 'login_parts.html').read_text(encoding='utf-8')
    assert '使用學校 Google 帳號登入' in text
    assert '填帳號與密碼後按登入' in text


def test_public_and_demo_pages_explain_their_links():
    for name in ('index.html', 'ocr_acceptance.html', 'proposal_preview.html'):
        text = (ROOT / 'app' / 'templates' / name).read_text(encoding='utf-8')
        assert text.count('data-tour=') >= 2, name


def test_error_and_welcome_pages_explain_next_step():
    for name in ('error_page.html', 'student_blocked.html', 'student_input_error.html', 'staff_review_error.html', 'upload_too_large.html', 'student_welcome.html'):
        text = (ROOT / 'app' / 'templates' / name).read_text(encoding='utf-8')
        assert text.count('data-tour=') >= 2, name


def test_tour_engine_does_not_invent_generic_steps():
    text = (ROOT / 'app' / 'static' / 'js' / 'components.js').read_text(encoding='utf-8')
    assert '這裡提供本頁主要的資料或操作' not in text


def test_role_main_templates_have_at_least_two_specific_steps():
    pages = {
        '學生': ('student_home.html', 'student_portfolio.html'),
        '導師': ('dashboard.html', 'teacher_student.html'),
        '科助': ('staff_forms.html', 'staff_certificate_batch.html'),
        '主任': ('admin_classes.html', 'staff_students.html'),
        '管理員': ('admin_accounts.html', 'admin_ai.html'),
    }
    for role, names in pages.items():
        for name in names:
            text = (ROOT / 'app' / 'templates' / name).read_text(encoding='utf-8')
            assert text.count('data-tour=') >= 2, (role, name)


def test_literal_tour_text_is_short():
    import re
    for path in (ROOT / 'app' / 'templates').rglob('*.html'):
        text = path.read_text(encoding='utf-8')
        for sentence in re.findall(r'data-tour="([^"]*)"', text):
            if '{{' not in sentence:
                assert len(sentence) <= 30, (path.name, sentence)

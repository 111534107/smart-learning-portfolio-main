"""手機版說明按鈕應有足夠觸控範圍。"""
from pathlib import Path


def test_info_tip_touch_target_is_at_least_44_pixels():
    css = (Path(__file__).resolve().parents[1] / 'app/static/css/student-v2/shell.css').read_text(encoding='utf-8')
    # 看起來維持小圓，點按範圍用 ::after 放大到 44px
    rule = css.split('.info-tip__btn {', 1)[1].split('}', 1)[0]
    assert 'position: relative' in rule
    after = css.split('.info-tip__btn::after {', 1)[1].split('}', 1)[0]
    assert '44px' in after and 'inset' in after


def test_shared_mobile_controls_have_44_pixel_targets():
    css = (Path(__file__).resolve().parents[1] / 'app/static/css/design-system.css').read_text(encoding='utf-8')
    assert '/* mobile-sweep touch targets */' in css
    block = css.split('/* mobile-sweep touch targets */', 1)[1]
    for selector in ('.button', '.account-menu__button', '.snav-bell'):
        assert selector in block
    assert 'min-height: 44px' in block
    assert 'min-width: 44px' in block


def test_mobile_breadcrumb_links_have_touch_height():
    css = (Path(__file__).resolve().parents[1] / 'app/static/css/design-system.css').read_text(encoding='utf-8')
    block = css.split('/* mobile-sweep touch targets */', 1)[1]
    assert '.band__crumbs a' in block
    assert 'min-height: 44px' in block


def test_attendance_return_link_has_mobile_touch_target():
    css = (Path(__file__).resolve().parents[1] / 'app/static/css/attendance.css').read_text(encoding='utf-8')
    assert '.attendance-register__head--sub > a' in css
    block = css.split('.attendance-register__head--sub > a', 1)[1].split('}', 1)[0]
    assert 'min-height: 44px' in block


def test_mobile_special_controls_have_touch_targets():
    root = Path(__file__).resolve().parents[1] / 'app/static/css'
    for file, selector in [('student-v2/shell.css', '.school-map__tool'), ('student-v2/graduation.css', '.gd-go--small'), ('agent-hub.css', '.hub-chip')]:
        css = (root / file).read_text(encoding='utf-8')
        assert '/* mobile-sweep special controls */' in css
        block = css.split('/* mobile-sweep special controls */', 1)[1]
        assert selector in block and 'min-height: 44px' in block


def test_mobile_record_and_navigation_targets():
    root = Path(__file__).resolve().parents[1] / 'app/static/css'
    for file, selectors in [('design-system.css', ('.brand', '.match-chart__label', '.link-button')), ('student-v2/portfolio.css', ('.pf-cat',)), ('student-v2/graduation.css', ('.gd-go',))]:
        css = (root / file).read_text(encoding='utf-8')
        assert '/* mobile-sweep additional targets */' in css
        block = css.split('/* mobile-sweep additional targets */', 1)[1]
        assert all(selector in block for selector in selectors)
        assert 'min-height: 44px' in block


def test_mobile_resume_remove_button_is_44_pixels():
    css = (Path(__file__).resolve().parents[1] / 'app/static/css/student-v2/home-desk.css').read_text(encoding='utf-8')
    assert '.rz-cellremove { width: 44px; height: 44px; }' in css


def test_touch_devices_stop_continuous_missing_and_hub_animations():
    root = Path(__file__).resolve().parents[1] / 'app/static/css'
    for file, selectors in [('design-system.css', ('.vessel--missing', '.piece--missing')), ('agent-hub.css', ('.hub-pulse',))]:
        css = (root / file).read_text(encoding='utf-8')
        assert '/* mobile-sweep continuous animation */' in css
        block = css.split('/* mobile-sweep continuous animation */', 1)[1]
        assert all(selector in block for selector in selectors)
        assert 'animation: none' in block

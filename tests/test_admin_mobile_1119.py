from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ocr_device_choices_have_explicit_single_column_layout():
    css = (ROOT / 'app/static/css/student-v2/staff.css').read_text(encoding='utf-8')
    assert 'body[data-page="admin-ocr"] .ocr-device-form' in css
    assert 'grid-template-columns: minmax(0, 1fr)' in css
    assert 'body[data-page="admin-ocr"] .ocr-device-form .choice' in css


def test_admin_mobile_menu_can_scroll_within_viewport():
    css = (ROOT / 'app/static/css/student-v2/staff.css').read_text(encoding='utf-8')
    assert 'max-height: calc(100dvh' in css
    assert 'overflow-y: auto' in css


def test_stacked_admin_table_content_can_wrap_on_narrow_screens():
    css = (ROOT / 'app/static/css/student-v2/staff.css').read_text(encoding='utf-8')
    assert 'table.table--stack td > *' in css
    assert 'overflow-wrap: anywhere' in css


def test_admin_ai_mobile_table_fields_fill_their_cells():
    css = (ROOT / 'app/static/css/student-v2/staff.css').read_text(encoding='utf-8')
    assert 'body[data-page="admin-ai"] table.table--stack input:not([type="checkbox"])' in css
    assert 'width: 100% !important' in css

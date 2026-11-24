"""2026-11-19 手機回報：「?」改彈跳視窗、畢業門檻說明不疊在卡片上、觸控裝置不做背景模糊、教職員表格在手機排成卡片。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "app/static/js/components.js").read_text(encoding="utf-8")
DESIGN = (ROOT / "app/static/css/design-system.css").read_text(encoding="utf-8")
SHELL = (ROOT / "app/static/css/student-v2/shell.css").read_text(encoding="utf-8")
GRAD = (ROOT / "app/static/css/student-v2/graduation.css").read_text(encoding="utf-8")


def test_info_tip_opens_a_dialog_instead_of_expanding():
    block = JS[JS.index("長說明收成「?」"):JS.index("手機上的教職員表格")]
    assert "showModal" in block and "info-tip-dialog" in block
    assert 'aria-haspopup", "dialog"' in block
    assert "p.hidden = !open" not in block          # 不再在原位往下展開
    assert "details.g2-help" in block               # 畢業門檻頁自己的說明也走彈跳視窗
    assert ".info-tip-dialog::backdrop" in DESIGN


def test_graduation_help_popover_has_solid_background():
    rule = GRAD[GRAD.index(".g2-help .info-tip__body {"):]
    rule = rule[:rule.index("}")]
    assert "background: var(--card)" in rule and "padding" in rule


def test_touch_devices_skip_backdrop_blur():
    block = SHELL[SHELL.index("手機效能（2026-11-19"):]
    assert "@media (pointer: coarse)" in block
    assert "backdrop-filter: none !important" in block


def test_staff_tables_stack_on_phones():
    block = JS[JS.index("手機上的教職員表格"):]
    assert 'hasAttribute("data-staff-ui")' in block and "data-no-stack" in block
    assert "cell.dataset.label" in block
    assert "table.table--stack td::before { content: attr(data-label)" in DESIGN

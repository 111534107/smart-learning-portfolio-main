"""字體大小切換（2026-11-04 使用者：系統字太大，要能調小／中／大，並統一字級）。"""
import re
from pathlib import Path

from app import create_app

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app" / "static" / "css" / "design-system.css").read_text(encoding="utf-8")


def test_default_is_16px_and_switch_has_three_sizes():
    assert "html { scroll-behavior: smooth; font-size: 100%; }" in CSS
    assert 'html[data-font-size="sm"] { font-size: 87.5%; }' in CSS
    assert 'html[data-font-size="lg"] { font-size: 112.5%; }' in CSS


def test_page_applies_saved_size_before_drawing_and_shows_switch():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    html = app.test_client().get("/login").get_data(as_text=True)

    head = html.split("</head>")[0]
    assert 'localStorage.getItem("font-size")' in head  # 在 <head> 先套用，避免閃動
    assert 'class="font-switch"' in html
    assert all(f'data-font-size-set="{size}"' in html for size in ("sm", "md", "lg"))


def test_shared_css_uses_size_tokens_not_one_off_rem_values():
    """統一字級：共用樣式的字體大小只用 --fs-* 六級（大標題用 clamp），不再出現 .93rem 這種零散值。"""
    for name in ("design-system.css", "agent-hub.css", "theme-campus.css"):
        text = (ROOT / "app" / "static" / "css" / name).read_text(encoding="utf-8")
        loose = re.findall(r"font-size:\s*[0-9.]+rem", text)
        assert loose == [], f"{name}: {loose}"


def test_headings_use_the_two_title_levels():
    """大標題只用 --fs-display、--fs-hero 兩級，不再各自寫 clamp()（11-04 首頁標題曾大到 48px）。"""
    for name in ("design-system.css", "theme-campus.css", "agent-hub.css"):
        text = (ROOT / "app" / "static" / "css" / name).read_text(encoding="utf-8")
        assert re.findall(r"font-size:\s*clamp\(", text) == [], name

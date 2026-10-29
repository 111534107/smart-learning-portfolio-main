"""共用樣式檔不能有合併衝突標記、大括號要成對；否則後面的樣式會整段失效（2026-10-11 合併時發生過）。"""
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / "app" / "static" / "css" / "design-system.css"


def test_no_merge_markers_and_balanced_braces():
    text = CSS.read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), 1):
        # 衝突標記一定在行首；註解裡的裝飾線「/* ====」不算
        assert not line.startswith(("<<<<<<<", ">>>>>>>")) and line.strip() != "=======", f"第 {number} 行有合併衝突標記"
    depth = 0
    for number, line in enumerate(text.splitlines(), 1):
        depth += line.count("{") - line.count("}")
        assert depth >= 0, f"第 {number} 行多了一個 }}"
    assert depth == 0, "有區塊沒有關閉"


def test_home_cover_layers_stay_below_the_sticky_masthead():
    """首頁封面的標語層 z-index 是 30（要蓋過資料夾），比刊頭的 20 高；
    封面要自成一個圖層（isolation: isolate），捲動時標語才不會蓋到刊頭（2026-10-22 使用者回報）。"""
    text = CSS.read_text(encoding="utf-8")
    assert '[data-page="public-home"] .cover.story-scene--scatter { isolation: isolate; }' in text

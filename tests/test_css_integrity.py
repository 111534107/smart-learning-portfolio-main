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

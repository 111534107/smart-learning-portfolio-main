from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_readme_links_to_the_current_specification_path():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    expected = "docs/01_正式規格/資管科智慧學習歷程系統-系統規格設計書-開發閱讀版.md"

    assert expected in readme
    assert (PROJECT_ROOT / expected).is_file()


def test_current_design_plan_uses_teacher_role_without_reviewer_login_role():
    plan = (PROJECT_ROOT / "docs/02_需求與設計/04_原始資料與參考/system-design-action-plan.md").read_text(encoding="utf-8")

    assert "教師/導師 | `teacher` |" in plan
    assert "教師/導師/評審 | `teacher` 或 `reviewer`" not in plan


def test_current_documents_use_moved_document_paths():
    current_documents = [
        PROJECT_ROOT / "docs/01_正式規格/資管科智慧學習歷程系統-系統規格設計書-開發閱讀版.md",
        PROJECT_ROOT / "docs/02_需求與設計/04_原始資料與參考/system-design-action-plan.md",
        PROJECT_ROOT / "docs/04_圖表與介面/03_檢查與圖表規範/diagram-style-guide.md",
    ]

    for document in current_documents:
        content = document.read_text(encoding="utf-8")
        assert "docs/diagrams.md" not in content
        assert "docs/system-design-action-plan.md" not in content

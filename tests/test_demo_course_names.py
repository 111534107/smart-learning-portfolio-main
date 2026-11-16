"""B26：展示用假成績單與示範學生的課名都要對得到修業科目表，畢業門檻才不會整片「待人工確認」。僅為測試資料。"""
import ast
import runpy
from pathlib import Path

import pytest

from app import create_app
from app.extensions import db
from app.services.graduation_check_service import credit_status, load_curriculum, normalize_course_name

ROOT = Path(__file__).resolve().parents[1]


def fake_transcript_courses():
    """不執行腳本（它會畫圖），只讀出 YEARS 的課表。"""
    tree = ast.parse((ROOT / "scripts" / "make_fake_transcript.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "YEARS":
            return ast.literal_eval(node.value)
    raise AssertionError("找不到 YEARS")


@pytest.mark.parametrize("admission_year", [111, 113])
def test_fake_transcript_course_names_are_in_curriculum(admission_year):
    table = load_curriculum()[admission_year]
    names = [name for _, _, courses in fake_transcript_courses() for name, *_ in courses]
    assert [name for name in names if normalize_course_name(name) not in table] == []


def test_demo_students_have_no_unmatched_courses():
    seed = runpy.run_path(str(ROOT / "scripts" / "run_demo.py"), run_name="demo_course_names")["seed"]
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite://", "TESTING": True})
    with app.app_context():
        db.create_all()
        seed()
        from app.models import User
        for username in ("113534901", "113534902", "113534903"):
            result = credit_status(User.query.filter_by(username=username).one())
            assert result["unmatched"] == [], username
            assert result["duplicates"] == [], username

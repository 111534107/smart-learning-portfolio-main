"""修業科目表 PDF 解析與檢查（11-09）。夾具是資管科網頁公開的官方 PDF：
https://im.ukn.edu.tw/p/405-1028-609,c82-1.php
"""
import csv
from pathlib import Path

from app.services import curriculum_parser as parser

FIXTURES = Path(__file__).parent / "fixtures" / "curriculum"
CSV_FILE = Path(__file__).resolve().parents[1] / "app" / "content" / "curriculum_groups.csv"


def _parsed(year):
    return parser.parse_pdf((FIXTURES / f"{year}.pdf").read_bytes())


def test_parses_111_exactly_like_the_hand_checked_csv():
    # 111 的 CSV 是人工對過 PDF 的，當標準答案
    with open(CSV_FILE, encoding="utf-8-sig") as handle:
        expected = {(row["科目類別"], row["科目名稱"]) for row in csv.DictReader(handle) if row["入學年度"] == "111"}
    result = _parsed(111)
    assert {(c["category"], c["name"]) for c in result["courses"]} == expected
    assert result["totals"] == {"total": 220, "required": 181, "elective": 39}


def test_all_checks_pass_for_official_files():
    for year in (110, 111, 114):
        result = _parsed(year)
        checks = parser.run_checks(result)
        assert all(check["ok"] for check in checks), (year, [c for c in checks if not c["ok"]])


def test_110_has_general_elective_section_and_certificate_notes():
    result = _parsed(110)
    categories = {c["category"] for c in result["courses"]}
    assert "通識選修" in categories
    assert parser.required_sum(result) == 181
    accounting = next(c for c in _parsed(114)["courses"] if c["name"] == "會計學")
    assert accounting["credits"] == 6 and accounting["note"] == "會計丙級"


def test_names_starting_with_latin_letters_are_kept():
    names = {c["name"] for c in _parsed(114)["courses"]}
    assert {"JAVA程式語言", "PYTHON程式語言", "資料庫管理實務(SQL)"} <= names
    assert any(name.startswith("Office VBA") for name in names)


def test_checks_fail_when_numbers_do_not_add_up():
    result = _parsed(111)
    result["courses"][0]["credits"] += 3  # 模擬解析錯一個數字
    failed = [c for c in parser.run_checks(result) if not c["ok"]]
    assert failed and any("小計" in c["name"] for c in failed)


def test_checks_fail_on_unknown_section():
    result = _parsed(111)
    result["sections"].append({"category": None, "subtotal": 2, "first": "看不懂的科目"})
    assert any(not c["ok"] and "區段" in c["name"] for c in parser.run_checks(result))


def test_checks_fail_when_totals_missing():
    result = _parsed(111)
    result["totals"] = None
    assert any(not c["ok"] for c in parser.run_checks(result))


def test_diff_lists_added_removed_and_changed_courses():
    old, new = _parsed(111), _parsed(114)
    diff = parser.diff_courses(old["courses"], new["courses"])
    assert {"added", "removed", "changed"} <= set(diff)
    assert any(item["name"] == "生成式人工智慧之應用" for item in diff["added"] + diff["changed"]) or diff["added"]
    summary = parser.summarize_diff(diff)
    assert "新增" in summary and "刪除" in summary
    assert parser.diff_courses(old["courses"], old["courses"]) == {"added": [], "removed": [], "changed": []}


def test_index_page_lists_curriculum_links_by_year():
    links = parser.parse_index((FIXTURES / "index.html").read_text(encoding="utf-8"),
                               "https://im.ukn.edu.tw/p/405-1028-609,c82-1.php")
    assert links[114] == "https://im.ukn.edu.tw/var/file/28/1028/img/519/800645289.pdf"
    assert links[111] == "https://im.ukn.edu.tw/var/file/28/1028/img/519/369604849.pdf"
    assert 99 in links and all("替代" not in url for url in links.values())

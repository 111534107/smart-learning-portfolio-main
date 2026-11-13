import csv
from collections import defaultdict
from pathlib import Path

from app import create_app
from app.extensions import db
from app.models import AdmissionProgram
from app.services.admission_service import import_seed_programs

NATIONAL = Path(__file__).resolve().parents[1] / "app" / "content" / "admission_demo_national_116.csv"


def rows():
    return list(csv.DictReader(open(NATIONAL, encoding="utf-8-sig")))


def test_only_national_schools_and_weights_sum_to_100():
    totals = defaultdict(int)
    for row in rows():
        assert row["學校"].startswith("國立"), row
        totals[row["志願代碼"]] += int(row["加權百分比"])
    assert len(totals) >= 30
    assert set(totals.values()) == {100}


def test_demo_seed_imports_on_top_of_main_seed():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        main = import_seed_programs()
        extra = import_seed_programs(NATIONAL)

        assert main == 4
        assert extra >= 30
        assert AdmissionProgram.query.count() == main + extra
        assert {p.school_name for p in AdmissionProgram.query.all()} >= {"國立臺北商業大學", "國立虎尾科技大學", "國立高雄科技大學"}


DAY_APPLY = Path(__file__).resolve().parents[1] / "app" / "content" / "admission_demo_dayapply_115.csv"


def test_day_apply_seed_imports_and_sums_to_100():
    totals = defaultdict(int)
    for row in csv.DictReader(open(DAY_APPLY, encoding="utf-8-sig")):
        assert row["招生類別"] == "日間部申請入學"
        assert "統測" in row["資料來源"]
        totals[row["志願代碼"]] += int(row["加權百分比"])
    assert set(totals.values()) == {100}

    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        assert import_seed_programs(DAY_APPLY) == len(totals)
        assert AdmissionProgram.query.filter_by(school_name="國立雲林科技大學").one().department_name == "資訊管理系"


PRIVATE = Path(__file__).resolve().parents[1] / "app" / "content" / "admission_demo_private_116.csv"


def test_private_seed_from_same_pdf_sums_to_100_and_imports():
    """2026-11-13：同一份 PDF 附錄裡的私立校系；不能混進國立，也不能跟其他種子撞志願代碼。"""
    totals = defaultdict(int)
    for row in csv.DictReader(open(PRIVATE, encoding="utf-8-sig")):
        assert not row["學校"].startswith("國立"), row
        assert row["原始項目名稱"] == row["原始項目名稱"].strip()
        assert row["對應狀態"] in ("確定", "待確認")
        totals[row["志願代碼"]] += int(row["加權百分比"])
    assert len(totals) >= 40 and set(totals.values()) == {100}
    national = {row["志願代碼"] for row in rows()}
    assert not national & set(totals)

    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        import_seed_programs()
        assert import_seed_programs(PRIVATE) == len(totals)
        names = {p.school_name for p in AdmissionProgram.query.all()}
        assert {"致理科技大學", "長庚科技大學", "輔英科技大學"} <= names

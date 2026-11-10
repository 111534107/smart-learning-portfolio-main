"""校系備審要求：把種子資料（CSV）匯入資料庫。

這是「二技招生資料 Agent」的第一階段：先由管理者手動建立資料。
之後 Agent 擷取的資料會寫進同一組資料表，只是 data_origin 改為 agent、status 先是 candidate。
"""

import csv
from pathlib import Path

from app.extensions import db
from app.models import AdmissionProgram, AdmissionRequirementItem
from app.services.admission_sample import SEED_FILE

# CSV「對應資料類別」欄的中文名稱 → 系統類別代碼
CATEGORY_NAME_TO_KEY = {
    "成績與學分": "grades",
    "證照": "credential",
    "活動": "activity",
    "競賽": "competition",
    "服務學習": "service",
    "幹部經歷": "leadership",
    "自傳與讀書計畫": "autobiography",
    "專題作品": "project",
}

MAPPING_STATUS = {"確定": "confirmed", "待確認": "pending"}


def _category_keys(text):
    names = [name.strip() for name in (text or "").replace("、", "；").split("；") if name.strip()]
    unknown = [name for name in names if name not in CATEGORY_NAME_TO_KEY]
    if unknown:
        raise ValueError(f"無法辨識的資料類別：{'、'.join(unknown)}")
    return ",".join(CATEGORY_NAME_TO_KEY[name] for name in names)


def import_seed_programs(path=SEED_FILE, status="published"):
    """匯入 CSV；已存在的志願（同代碼、同學年度）會略過。回傳新增的志願數。"""
    rows = []
    with open(Path(path), encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    created = 0
    programs = {}
    for row in rows:
        key = (row["志願代碼"], int(row["學年度"]))
        if key not in programs:
            existing = AdmissionProgram.query.filter_by(program_code=key[0], admission_year=key[1]).first()
            if existing:
                programs[key] = None
                continue
            program = AdmissionProgram(
                program_code=key[0],
                admission_year=key[1],
                school_name=row["學校"],
                department_name=row["科系"],
                admission_category=row["招生類別"] or None,
                source_note=row["資料來源"] or None,
                source_url=row.get("來源網址") or None,
                status=status,
                data_origin="manual",
            )
            db.session.add(program)
            programs[key] = program
            created += 1
        program = programs[key]
        if program is None:
            continue
        program.items.append(AdmissionRequirementItem(
            source_item_name=row["原始項目名稱"],
            weight_percent=int(row["加權百分比"]),
            mapped_categories=_category_keys(row["對應資料類別"]),
            mapping_status=MAPPING_STATUS.get(row["對應狀態"], "pending"),
            requirement=row.get("要求說明") or None,
            sort_order=len(program.items),
        ))
    db.session.commit()
    return created


def refresh_seed_details(path=SEED_FILE):
    """種子資料核對過官方簡章後，更新已經匯入的人工校系（2026-11-10）。

    只做「補」與「升級」：補上空白的說明與來源網址；CSV 標「確定」而資料庫還是「待確認」的項目，
    改成 CSV 的資料類別並標為確定。管理員已經標確定的項目不動。回傳更新的項目數。
    """
    with open(Path(path), encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    updated = 0
    for row in rows:
        program = AdmissionProgram.query.filter_by(program_code=row["志願代碼"], admission_year=int(row["學年度"]),
                                                   data_origin="manual").first()
        if program is None:
            continue
        item = next((i for i in program.items if i.source_item_name == row["原始項目名稱"]), None)
        if item is None:
            continue
        touched = False
        if row.get("來源網址") and not program.source_url:
            program.source_url = row["來源網址"]
            program.source_note = row["資料來源"] or program.source_note
        if row.get("要求說明") and not item.requirement:
            item.requirement = row["要求說明"]
            touched = True
        if row["對應狀態"] == "確定" and item.mapping_status != "confirmed":
            item.mapped_categories = _category_keys(row["對應資料類別"])
            item.mapping_status = "confirmed"
            touched = True
        updated += touched
    db.session.commit()
    return updated


def published_programs():
    """學生可以選的校系：同一個志願代碼只顯示最新學年度的正式版。"""
    programs = (AdmissionProgram.query.filter_by(status="published")
                .order_by(AdmissionProgram.admission_year.desc(), AdmissionProgram.program_code).all())
    newest = {}
    for program in programs:
        newest.setdefault(program.program_code, program)
    return sorted(newest.values(), key=lambda p: (-p.admission_year, p.program_code))

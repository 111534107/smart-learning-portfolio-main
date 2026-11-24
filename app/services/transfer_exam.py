"""插大（大學轉學考）：示範校系資料的匯入與讀取。

資料放在 app/content/admission_transfer_demo.csv，每一列附官方簡章網址、頁碼與查詢日期；查不到的寫「待確認」。
- 校系本身沿用 AdmissionProgram：招生類別寫「插大（轉學考）」，志願代碼用 TRF- 開頭（不是 6 位數字，
  避免被當成二技技優甄審）。
- 只考筆試的校系沒有備審加權，不建立評分項目；有書面審查的（例如臺大資工）才建一個項目，可以算契合度。
- 考科、報考資格、報名費、日期等說明不進資料庫（本輪不加資料庫遷移），畫面要用時由 load_transfer_details 讀 CSV。
"""

import csv
from datetime import date
from pathlib import Path

from app.extensions import db
from app.models import AdmissionProgram, AdmissionRequirementItem
from app.services.admission_service import MAPPING_STATUS, _category_keys

TRANSFER_FILE = Path(__file__).resolve().parents[1] / "content" / "admission_transfer_demo.csv"
TRANSFER_CATEGORY = "插大（轉學考）"


def is_transfer(program):
    return program.admission_category == TRANSFER_CATEGORY


def _rows(path):
    with open(Path(path), encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_transfer_details(path=None):
    """回傳 {志願代碼: {grade, quota, eligibility, subjects, fee, apply_dates, exam_date, admission_url,
    brochure_url, source, checked_on}}。檔案不存在時回傳空的。"""
    path = path or TRANSFER_FILE
    if not Path(path).is_file():
        return {}
    return {
        row["志願代碼"].strip(): {
            "grade": row["插入年級"].strip(),
            "quota": row["名額"].strip(),
            "eligibility": row["報考資格"].strip(),
            "subjects": row["考試科目"].strip(),
            "fee": row["報名費"].strip(),
            "apply_dates": row["報名日期"].strip(),
            "exam_date": row["考試日期"].strip(),
            "admission_url": row["招生網址"].strip(),
            "brochure_url": row["簡章網址"].strip(),
            "source": row["出處"].strip(),
            "checked_on": row["查詢日期"].strip(),
        }
        for row in _rows(path)
    }


def import_transfer_programs(path=None, status="published"):
    """匯入插大示範校系；已存在的（同代碼、同學年度）會略過。回傳新增的校系數。"""
    created = 0
    for row in _rows(path or TRANSFER_FILE):
        code, year = row["志願代碼"].strip(), int(row["學年度"])
        if AdmissionProgram.query.filter_by(program_code=code, admission_year=year).first():
            continue
        program = AdmissionProgram(
            program_code=code,
            admission_year=year,
            school_name=row["學校"],
            department_name=row["科系"],
            admission_category=row["招生類別"] or TRANSFER_CATEGORY,
            source_url=row["簡章網址"] or None,
            source_note=row["出處"] or None,
            checked_at=date.fromisoformat(row["查詢日期"]) if row["查詢日期"] else None,
            status=status,
            data_origin="manual",
        )
        if row["原始項目名稱"].strip():
            program.items.append(AdmissionRequirementItem(
                source_item_name=row["原始項目名稱"].strip(),
                weight_percent=int(row["加權百分比"]),
                mapped_categories=_category_keys(row["對應資料類別"]),
                mapping_status=MAPPING_STATUS.get(row["對應狀態"], "pending"),
                sort_order=0,
            ))
        db.session.add(program)
        created += 1
    db.session.commit()
    return created

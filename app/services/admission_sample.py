"""讀取二技校系備審加權的種子資料（app/content/admission_seed_115.csv）。

目前用於首頁展示；下一階段會用同一份檔案建立校系資料表。
"""

import csv
from pathlib import Path

SEED_FILE = Path(__file__).resolve().parents[1] / "content" / "admission_seed_115.csv"


def load_sample_programs(path=SEED_FILE):
    """依志願代碼分組，回傳 [{code, school, department, items:[{name, weight}]}]。"""
    if not Path(path).is_file():
        return []
    programs = {}
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            program = programs.setdefault(row["志願代碼"], {
                "code": row["志願代碼"],
                "year": row["學年度"],
                "school": row["學校"],
                "department": row["科系"],
                "items": [],
            })
            program["items"].append({"name": row["原始項目名稱"], "weight": int(row["加權百分比"])})
    return list(programs.values())

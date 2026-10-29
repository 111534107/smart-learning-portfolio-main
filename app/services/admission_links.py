"""各校系的招生連結：學校招生網站、二技技優的聯合招生入口，以及 Agent 擷取時記下的簡章網址。

學校招生網址放在 app/content/admission_school_links.csv（只收各校官方網域，附確認日期）。
找不到學校時不自己猜網址，只列出確定的連結。
"""

import csv
from pathlib import Path

SCHOOL_LINKS_FILE = Path(__file__).resolve().parents[1] / "content" / "admission_school_links.csv"

# 技專校院招生委員會聯合會：二技技優保送、技優甄審共用的入口
JOINT_SKILL_ENTRY = "https://www.jctv.ntut.edu.tw/enter/"


def load_school_links(path=None):
    """回傳 {學校名稱: 招生網址}。檔案不存在時回傳空的。"""
    path = path or SCHOOL_LINKS_FILE
    if not Path(path).is_file():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return {row["學校"].strip(): row["招生網址"].strip() for row in csv.DictReader(handle)}


def admission_links(program, school_links=None):
    """回傳 [{label, url}]：簡章原始來源（有的話）→ 學校招生網站 → 二技技優聯合招生入口。"""
    school_links = load_school_links() if school_links is None else school_links
    links = []
    if program.source_url:
        links.append({"label": "簡章原始來源", "url": program.source_url})
    if program.school_name in school_links:
        links.append({"label": f"{program.school_name}招生網站", "url": school_links[program.school_name]})
    if program.program_code.isdigit():  # 6 位數志願代碼＝二技技優甄審
        links.append({"label": "二技技優甄審報名入口（技專校院招生委員會聯合會）", "url": JOINT_SKILL_ENTRY})
    return links

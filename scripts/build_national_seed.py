"""從《116 二技技優甄審 時程與備審加權》PDF 的附錄總表，整理出國立大學校系的備審加權 CSV。

用法（在專案根目錄）：
    python scripts/build_national_seed.py

只讀 PDF 裡寫的內容，不自己補學校或加權；PDF 沒有的學校（例如北科大）不會出現。
「對應資料類別」是依項目名稱關鍵字推測的，除了純成績類，其餘一律標「待確認」，由管理者核對。
輸出：app/content/admission_demo_national_116.csv（不含主種子檔已有的志願代碼）。
"""

import csv
import re
import sys
from pathlib import Path

import pypdf

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "school" / "Documents" / "116二技技優甄審_時程與備審加權_修訂版.pdf"
SEED = ROOT / "app" / "content" / "admission_seed_115.csv"
OUT = ROOT / "app" / "content" / "admission_demo_national_116.csv"
SOURCE = "116二技技優甄審_時程與備審加權_修訂版.pdf（整理自115學年度簡章附錄）"

# 依序比對；一個項目可以對應多個類別
RULES = [
    (r"成績|學業|在學|在校|學習能力|學習技能", "成績與學分"),
    (r"證照|證書|證明|檢定|英檢|語文|外語", "證照"),
    (r"競賽", "競賽"),
    (r"自傳|讀書計畫|學習計畫|履歷|學習規劃|學習潛力", "自傳與讀書計畫"),
    (r"專題|作品|專業成果|特殊表現|特殊事蹟", "專題作品"),
    (r"活動|領導|幹部|社團|服務|優良事蹟|其他|佐審|選繳", "活動；服務學習；幹部經歷"),
]
# 以上都沒對到（例如「專業能力」「技能及經歷」）才用這一組
FALLBACK = "證照；競賽；專題作品"


def categories(name):
    found = []
    for pattern, cats in RULES:
        if re.search(pattern, name):
            found.extend(c for c in cats.split("；") if c not in found)
    return "；".join(found) if found else FALLBACK


def main():
    text = "\n".join((page.extract_text() or "") for page in pypdf.PdfReader(PDF).pages)
    seeded = {row["志願代碼"] for row in csv.DictReader(open(SEED, encoding="utf-8-sig"))}
    rows, problems = [], []
    for line in text.splitlines():
        m = re.match(r"^(\d{6}) (國立\S+) (\S+) (\S+) (.+)$", line.strip())
        if not m or m.group(1) in seeded:
            continue
        code, school, dept, kind, weights = m.groups()
        items = [re.match(r"(.+?)(\d+)%$", part.strip()) for part in weights.split("｜")]
        if not all(items) or sum(int(i.group(2)) for i in items) != 100:
            problems.append(line)
            continue
        for item in items:
            name, pct = item.group(1), int(item.group(2))
            cats = categories(name)
            pure_grade = cats == "成績與學分" and re.search(r"歷年|成績", name)
            rows.append([code, 115, school, dept, kind, name, pct, cats, "確定" if pure_grade else "待確認", SOURCE])
    with open(OUT, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["志願代碼", "學年度", "學校", "科系", "招生類別", "原始項目名稱", "加權百分比", "對應資料類別", "對應狀態", "資料來源"])
        writer.writerows(rows)
    print(f"{len({r[0] for r in rows})} 個志願、{len(rows)} 列 → {OUT}")
    for line in problems:
        print("略過（加總不是 100 或格式不符）：", line, file=sys.stderr)


if __name__ == "__main__":
    main()

"""從《116 二技技優甄審 時程與備審加權》PDF 的附錄總表，整理出「私立」學校校系的備審加權 CSV。

2026-11-13：國立的已由 scripts/build_national_seed.py 整理；這支補上同一份附錄裡的私立校系。
用法（在專案根目錄）：
    python scripts/build_private_seed.py

規則與國立相同：只讀 PDF 裡寫的內容，不自己補學校或加權；加總不是 100 的志願略過並列出。
「對應資料類別」依項目名稱關鍵字推測，除了純成績類，其餘一律標「待確認」。
PDF 表格有些校名或系名太長會斷成兩行，這裡會接回去。
讀 PDF 用 pypdf；沒有的話改用 pypdfium2。
輸出：app/content/admission_demo_private_116.csv
"""

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_national_seed import PDF, SEED, SOURCE, categories  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app" / "content" / "admission_demo_private_116.csv"
COLUMNS = ["志願代碼", "學年度", "學校", "科系", "招生類別", "原始項目名稱", "加權百分比", "對應資料類別", "對應狀態",
           "資料來源", "要求說明", "來源網址", "重點提醒"]
ROW = re.compile(r"^(\d{6}) (\S+) (\S+) (\S+) (.+%)$")


def pdf_text():
    try:
        import pypdf
        return "\n".join((page.extract_text() or "") for page in pypdf.PdfReader(PDF).pages)
    except ImportError:
        import pypdfium2
        document = pypdfium2.PdfDocument(str(PDF))
        return "\n".join(document[i].get_textpage().get_text_bounded() for i in range(len(document)))


def table_lines(text):
    """附錄的每一列；斷成兩、三行的列接回同一行（「（桃園」＋「）」→「（桃園）」）。"""
    lines = [l.strip() for l in text.splitlines()]
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\d{6} ", line):
            joined, j = line, i
            while not ROW.match(joined) and j + 1 < len(lines) and j - i < 3 and not re.match(r"^\d{6} ", lines[j + 1]):
                j += 1
                unclosed = joined.count("（") > joined.count("）")
                joined += ("" if unclosed else " ") + lines[j]
            yield joined, line
            i = j + 1
        else:
            i += 1


def main():
    seeded = {row["志願代碼"] for row in csv.DictReader(open(SEED, encoding="utf-8-sig"))}
    rows, problems = [], []
    for line, first in table_lines(pdf_text()):
        m = ROW.match(line)
        if not m:
            if " 國立" not in first:
                problems.append(first)
            continue
        code, school, dept, kind, weights = m.groups()
        if school.startswith("國立") or code in seeded:
            continue
        items = [re.match(r"(.+?)(\d+)%$", part.strip()) for part in weights.split("｜")]
        if not all(items) or sum(int(i.group(2)) for i in items) != 100:
            problems.append(line)
            continue
        for item in items:
            name, pct = item.group(1).strip(), int(item.group(2))
            cats = categories(name)
            pure_grade = cats == "成績與學分" and re.search(r"歷年|成績", name)
            rows.append([code, 115, school, dept, kind, name, pct, cats, "確定" if pure_grade else "待確認", SOURCE,
                         "", "", ""])
    with open(OUT, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    print(f"{len({r[0] for r in rows})} 個志願、{len(rows)} 列 → {OUT}")
    for line in problems:
        print("略過（加總不是 100 或格式不符）：", line, file=sys.stderr)


if __name__ == "__main__":
    main()

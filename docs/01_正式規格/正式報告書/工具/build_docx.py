"""以原專題報告書的封面為基礎，用精簡版 V2 報告書內容產生新的 Word 檔（不覆蓋原檔）。"""
import copy
import os
import re
import shutil
import sys

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Inches, Pt
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")
DIR = "D:/democase/ai/docs/01_正式規格/正式報告書"
SRC = f"{DIR}/資管科智慧學習歷程系統_專題報告書.docx"
OUT = f"{DIR}/資管科智慧學習歷程系統_專題報告書_V2_2026-10-16.docx"
MD = f"{DIR}/資管科智慧學習歷程系統_報告書_精簡版_V2_2026-10-16.md"
assert not os.path.exists(OUT), "目標檔已存在，不覆蓋"
shutil.copyfile(SRC, OUT)

doc = Document(OUT)
body = doc.element.body
children = list(body)
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# 封面：到「中 華 民 國 … 年 … 月」那一段為止
cover_end = next(i for i, el in enumerate(children)
                 if el.tag == W + "p" and "中 華 民 國" in "".join(t.text or "" for t in el.iter(W + "t")))
first_sect_p = next(el for el in children if el.tag == W + "p" and el.find(".//" + W + "sectPr") is not None)
sect0 = copy.deepcopy(first_sect_p.find(".//" + W + "sectPr"))
body_sect = body.find(W + "sectPr")
for el in children[cover_end + 1:]:
    if el is not body_sect:
        body.remove(el)
# 全文使用封面那一節的版面與頁尾（第 X 頁）
body.remove(body_sect)
body.append(sect0)

PAGE_W = Inches(6.2)
PAGE_H = Inches(8.4)
CN = "一二三四五六七八九十"
FIG = [0]
from docx.enum.style import WD_STYLE_TYPE
CAP = "圖說"
if CAP not in [s.name for s in doc.styles]:
    _st = doc.styles.add_style(CAP, WD_STYLE_TYPE.PARAGRAPH)
    _st.base_style = doc.styles["Caption"]


def page_break():
    p = doc.add_paragraph()
    p.add_run().add_break(WD_BREAK.PAGE)


def add_field(paragraph, instr, placeholder="（請在 Word 中更新功能變數）"):
    r = paragraph.add_run()
    b = OxmlElement("w:fldChar"); b.set(qn("w:fldCharType"), "begin"); r._r.append(b)
    r2 = paragraph.add_run()
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = f" {instr} "; r2._r.append(it)
    r3 = paragraph.add_run()
    s = OxmlElement("w:fldChar"); s.set(qn("w:fldCharType"), "separate"); r3._r.append(s)
    paragraph.add_run(placeholder)
    r5 = paragraph.add_run()
    e = OxmlElement("w:fldChar"); e.set(qn("w:fldCharType"), "end"); r5._r.append(e)


def title(text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text); run.bold = True; run.font.size = Pt(18)


def add_inline(p, text):
    text = text.replace("`", "")
    parts = re.split(r"(\*\*[^*]+\*\*)", text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            p.add_run(part[2:-2]).bold = True
        else:
            p.add_run(part)


def add_table(rows):
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    cells = [r for r in cells if not all(re.fullmatch(r":?-{2,}:?", c) for c in r)]
    ncol = len(cells[0])
    t = doc.add_table(rows=len(cells), cols=ncol)
    t.style = "Table Grid"
    for i, r in enumerate(cells):
        for j in range(ncol):
            c = t.cell(i, j)
            c.paragraphs[0].text = ""
            add_inline(c.paragraphs[0], r[j] if j < len(r) else "")
            for run in c.paragraphs[0].runs:
                run.font.size = Pt(10)
                if i == 0:
                    run.bold = True
    doc.add_paragraph()


def add_figure(path, caption):
    w, h = Image.open(path).size
    scale = min(PAGE_W / w, PAGE_H / h)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(path, width=Emu(int(w * scale)), height=Emu(int(h * scale)))
    FIG[0] += 1
    c = doc.add_paragraph(style=CAP); c.alignment = WD_ALIGN_PARAGRAPH.CENTER
    c.add_run(f"圖 {FIG[0]}　{caption}")


# 目錄與圖目錄
page_break()
title("目錄")
add_field(doc.add_paragraph(), 'TOC \\o "1-2" \\h \\z \\u')
page_break()
title("圖目錄")
add_field(doc.add_paragraph(), 'TOC \\h \\z \\t "圖說,1"')

# 內文：從「摘要」到附錄二之前
md = open(MD, encoding="utf-8").read()
md = md[md.index("## 摘要"):md.index("## 附錄一")]
# 給老師的正式版：拿掉內部檔案路徑
for old, new in [
    ("環境設定與移除清單記錄在 `docs/03_開發紀錄/01_參考與環境設定/`（以實際資料夾為準）。\n", ""),
    ("資料表的完整欄位與關聯以 ERD 為準，請見 `docs/04_圖表與介面/01_資料模型/`（以實際檔案為準）。", "資料表的完整欄位與關聯以第二節的 ERD 為準。"),
    ("圖檔統一放在 `docs/images/`，索引見 `docs/04_圖表與介面/diagrams.md`。虛線框表示尚未實機驗收或待學校政策決定的項目。", "圖中的虛線框表示尚未實機驗收或待學校政策決定的項目。"),
    ("提案內容見 `01_正式規格/資管科智慧學習歷程系統-系統規格設計書-開發閱讀版_v2.md`，", ""),
]:
    assert old in md, old[:20]
    md = md.replace(old, new)
lines = md.splitlines()
i = 0
pending_caption = None
in_code = False
while i < len(lines):
    line = lines[i]
    s = line.strip()
    if s.startswith("```"):
        in_code = not in_code; i += 1; continue
    if in_code:
        p = doc.add_paragraph(); r = p.add_run(line); r.font.name = "Consolas"; r.font.size = Pt(9); i += 1; continue
    if not s or s == "---":
        i += 1; continue
    if s.startswith("|"):
        rows = []
        while i < len(lines) and lines[i].strip().startswith("|"):
            rows.append(lines[i]); i += 1
        add_table(rows); continue
    m = re.match(r"^(#{2,4})\s+(.*)$", s)
    if m:
        level = len(m.group(1)) - 1
        text = m.group(2).replace("`", "")
        cm = re.match(r"^第([一二三四五六七八九十]+)章\s*(.*)$", text)
        if cm:
            text = f"{cm.group(1)}、{cm.group(2)}"
        if level == 1:
            page_break()
        doc.add_paragraph(text, style=f"Heading {level}")
        i += 1; continue
    fm = re.match(r"^\*\*圖\s*\d+　(.+)\*\*$", s)
    if fm:
        pending_caption = fm.group(1); i += 1; continue
    im = re.match(r"^!\[[^\]]*\]\(([^)]+)\)$", s)
    if im:
        path = os.path.normpath(os.path.join(DIR, im.group(1)))
        add_figure(path, pending_caption or "")
        pending_caption = None; i += 1; continue
    if s.startswith(">"):
        p = doc.add_paragraph(); add_inline(p, s.lstrip("> ").strip()); i += 1; continue
    if s.startswith("- "):
        p = doc.add_paragraph(style="List Bullet"); add_inline(p, s[2:]); i += 1; continue
    nm = re.match(r"^(\d+)\.\s+(.*)$", s)
    if nm:
        p = doc.add_paragraph(); p.paragraph_format.left_indent = Inches(0.25)
        add_inline(p, f"{nm.group(1)}. {nm.group(2)}"); i += 1; continue
    p = doc.add_paragraph(); add_inline(p, s); i += 1

doc.save(OUT)
print("saved", OUT, os.path.getsize(OUT))

"""把專題書面報告（精簡版 V2，正式 Word 2026-10-28 的文字來源）轉成 11/4 報告簡報。

用法：D:\\democase\\ai\\.venv\\Scripts\\python.exe build_slides.py 輸出.pptx（目標檔已存在就停下，不覆蓋）
圖檔取自 D:\\democase\\ai\\docs\\images（10-28 校正後版本）；
系統畫面取自 docs\\08_簡報\\系統畫面截圖_2026-11-03（本機展示站合成資料，2026-11-03 截圖）。
長流程圖會在空白列切段，切好的圖暫存在系統暫存資料夾。
"""
import sys
import tempfile
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

OUT = Path(sys.argv[1])
SHOTS = Path(r"D:\democase\ai\docs\08_簡報\系統畫面截圖_2026-11-03")
CROPS = Path(tempfile.gettempdir()) / "build_slides_crops"
CROPS.mkdir(exist_ok=True)
IMG = Path(r"D:\democase\ai\docs\images")

FONT = "微軟正黑體"
INK = RGBColor(0x1F, 0x24, 0x30)
MUTED = RGBColor(0x5B, 0x63, 0x70)
BLUE = RGBColor(0x2B, 0x47, 0xC9)      # 系統主色（展示站導覽列同色）
BLUE_TINT = RGBColor(0xE8, 0xEC, 0xFA)
GRAY_TINT = RGBColor(0xF3, 0xF4, 0xF6)
LINE = RGBColor(0xD5, 0xD9, 0xE0)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
# 五個年級的顏色（展示站「我的五年」路線同色），當作整份簡報的記號
YEAR = [RGBColor(0x2B, 0x47, 0xC9), RGBColor(0x1E, 0x8C, 0x76), RGBColor(0xE0, 0xA1, 0x1B),
        RGBColor(0xD9, 0x53, 0x3A), RGBColor(0x6B, 0x4B, 0xC8)]
OK = RGBColor(0x1E, 0x8C, 0x76)
WARN = RGBColor(0xC9, 0x7A, 0x00)
TODO = RGBColor(0x8A, 0x91, 0x9C)

CHAPTERS = ["緒論", "系統規格", "系統設計", "實作現況", "系統展示", "決議與規劃"]
SHOT_NOTE = "畫面為本機展示站，資料皆為合成測試資料（2026-11-03 截圖）"

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]
SW, SH = 13.333, 7.5
page_no = 0


# ---------- 基本元件 ----------
def set_east_asian(run):
    """中文字要寫在 a:ea，PowerPoint 才會用微軟正黑體顯示中文。"""
    rpr = run._r.get_or_add_rPr()
    rpr.set("lang", "zh-TW")
    if rpr.find(qn("a:ea")) is None:
        rpr.append(rpr.makeelement(qn("a:ea"), {"typeface": FONT}))

def text(slide, x, y, w, h, content, size=16, bold=False, color=INK, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, name=None, spacing=None):
    """content 可以是字串，或段落清單；段落可以是 (文字, {選項}) 或 [(文字, {選項}), ...] 多段文字。"""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        box.name = name
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.04)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    tf.vertical_anchor = anchor
    paras = content if isinstance(content, list) else [content]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if spacing:
            p.space_after = Pt(spacing)
        runs = para if isinstance(para, list) else [para]
        for run_spec in runs:
            if isinstance(run_spec, tuple):
                t, opt = run_spec
            else:
                t, opt = run_spec, {}
            r = p.add_run()
            r.text = t
            f = r.font
            f.name = FONT
            f.size = Pt(opt.get("size", size))
            f.bold = opt.get("bold", bold)
            f.color.rgb = opt.get("color", color)
            set_east_asian(r)
    return box


def shape(slide, kind, x, y, w, h, fill=None, line=None, radius=None, shadow=False):
    s = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(1)
    if radius is not None and kind == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    if not shadow:
        sp_pr = s._element.spPr
        sp_pr.append(sp_pr.makeelement(qn("a:effectLst"), {}))
    s.text_frame.text = ""
    return s


def circle_num(slide, x, y, d, label, fill, size=16):
    c = shape(slide, MSO_SHAPE.OVAL, x, y, d, d, fill=fill)
    tf = c.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    r = p.add_run()
    r.text = label
    r.font.name = FONT
    r.font.size = Pt(size)
    r.font.bold = True
    r.font.color.rgb = WHITE
    set_east_asian(r)
    return c


def new_slide(chapter=None, notes=None):
    global page_no
    page_no += 1
    s = prs.slides.add_slide(BLANK)
    if chapter is not None:
        # 頂端章節標籤：目前章節用主色膠囊，其他灰字（學長姐「智慧實習」簡報的導覽做法）
        x = 0.6
        for i, name in enumerate(CHAPTERS):
            w = 0.32 + 0.2 * len(name)
            if name == chapter:
                tab = shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 0.28, w, 0.36, fill=BLUE, radius=0.5)
                text(s, x, 0.28, w, 0.36, name, size=12, bold=True, color=WHITE,
                     align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
            else:
                text(s, x, 0.28, w, 0.36, name, size=12, color=TODO, align=PP_ALIGN.CENTER,
                     anchor=MSO_ANCHOR.MIDDLE)
            x += w + 0.08
        # 右上角五年色點
        for i, col in enumerate(YEAR):
            shape(s, MSO_SHAPE.OVAL, 11.86 + i * 0.18, 0.4, 0.12, 0.12, fill=col)
        text(s, 12.2, 7.0, 0.6, 0.3, str(page_no), size=11, color=TODO, align=PP_ALIGN.RIGHT)
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def title(slide, t, sub=None):
    text(slide, 0.6, 0.82, 12.1, 0.7, t, size=30, bold=True, name="Title")
    if sub:
        text(slide, 0.6, 1.47, 12.1, 0.4, sub, size=14, color=MUTED)


def table(slide, rows, x, y, w, col_w, size=14, header_size=14, row_h=0.42, first_col_bold=False,
          cell_colors=None):
    n_rows, n_cols = len(rows), len(rows[0])
    gt = slide.shapes.add_table(n_rows, n_cols, Inches(x), Inches(y), Inches(w), Inches(row_h * n_rows))
    tbl = gt.table
    tbl.first_row = True
    for j, cw in enumerate(col_w):
        tbl.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        tbl.rows[i].height = Inches(row_h)
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.margin_left = cell.margin_right = Inches(0.1)
            cell.margin_top = cell.margin_bottom = Inches(0.05)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            if i == 0:
                cell.fill.fore_color.rgb = INK
            else:
                cell.fill.fore_color.rgb = WHITE if i % 2 else GRAY_TINT
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            r = p.add_run()
            r.text = val
            r.font.name = FONT
            r.font.size = Pt(header_size if i == 0 else size)
            r.font.bold = i == 0 or (first_col_bold and j == 0)
            color = WHITE if i == 0 else INK
            if cell_colors and i > 0 and (i, j) in cell_colors:
                color = cell_colors[(i, j)]
                r.font.bold = True
            r.font.color.rgb = color
            set_east_asian(r)
    return gt


def picture_fit(slide, path, x, y, w, h, border=False):
    im = Image.open(path)
    iw, ih = im.size
    scale = min(w / iw, h / ih)
    pw, ph = iw * scale, ih * scale
    px, py = x + (w - pw) / 2, y + (h - ph) / 2
    if border:
        shape(slide, MSO_SHAPE.RECTANGLE, px - 0.02, py - 0.02, pw + 0.04, ph + 0.04, line=LINE)
    slide.shapes.add_picture(str(path), Inches(px), Inches(py), Inches(pw), Inches(ph))
    return px, py, pw, ph


def caption(slide, t, y=6.98):
    text(slide, 0.6, y, 11.2, 0.32, t, size=12, color=MUTED)


# ---------- 長圖切段：在空白列切開，避免切到方框或文字 ----------
def split_tall(path, n):
    im = Image.open(path).convert("L")
    w, h = im.size
    px = im.load()
    ink = []
    for yy in range(h):
        ink.append(sum(1 for xx in range(0, w, 2) if px[xx, yy] < 235))
    cuts = [0]
    for k in range(1, n):
        target = h * k // n
        lo, hi = int(target - h / n * 0.18), int(target + h / n * 0.18)
        best = min(range(lo, hi), key=lambda yy: (ink[yy], abs(yy - target)))
        cuts.append(best)
    cuts.append(h)
    src = Image.open(path)
    parts = []
    for k in range(n):
        part = src.crop((0, cuts[k], w, cuts[k + 1]))
        out = CROPS / f"{path.stem}_part{k + 1}.png"
        part.save(out)
        parts.append(out)
    return parts


def figure_slide(chapter, t, fig, cap, notes, side=None, side_w=4.1):
    """單張圖：有 side 時圖在左、說明在右；沒有時圖佔滿內容區。"""
    s = new_slide(chapter, notes)
    title(s, t)
    if side:
        picture_fit(s, fig, 0.6, 1.6, 12.13 - side_w - 0.4, 5.25)
        side_panel(s, 12.73 - side_w, 1.75, side_w, side)
    else:
        picture_fit(s, fig, 0.6, 1.6, 12.13, 5.25)
    caption(s, cap)
    return s


def side_panel(s, x, y, w, items):
    """右側重點：小色點＋粗體標題＋說明。items = [(標題, 說明), ...]"""
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, 0.2 + 0.95 * len(items), fill=GRAY_TINT, radius=0.06)
    yy = y + 0.2
    for i, (head, body) in enumerate(items):
        shape(s, MSO_SHAPE.OVAL, x + 0.25, yy + 0.1, 0.16, 0.16, fill=YEAR[i % 5])
        text(s, x + 0.5, yy, w - 0.7, 0.36, head, size=15, bold=True)
        text(s, x + 0.5, yy + 0.36, w - 0.7, 0.55, body, size=13, color=MUTED)
        yy += 0.95


def split_slides(chapter, t, fig, cap, notes, slides, per_slide):
    """長圖切成 slides × per_slide 段，每頁並排 per_slide 段，段上標①②③方便照順序讀。"""
    n = slides * per_slide
    parts = split_tall(IMG / fig, n)
    gap = 0.35
    col_w = (12.13 - gap * (per_slide - 1)) / per_slide
    for si in range(slides):
        label = f"（{si + 1}/{slides}）" if slides > 1 else ""
        s = new_slide(chapter, notes if si == 0 else f"{t} 續。照圓圈編號由左而右讀。")
        title(s, t + label)
        for c in range(per_slide):
            k = si * per_slide + c
            x = 0.6 + c * (col_w + gap)
            picture_fit(s, parts[k], x, 1.62, col_w, 5.25)
            circle_num(s, x, 1.62, 0.36, str(k + 1), YEAR[k % 5], size=13)
        caption(s, cap + ("　｜　依編號順序閱讀" if n > 1 else ""))


def shot_slide(t, role, shot, points, notes, crop=None):
    s = new_slide("系統展示", notes)
    title(s, f"系統展示－{t}")
    path = SHOTS / shot
    px, py, pw, ph = picture_fit(s, path, 0.6, 1.62, 8.75, 5.15, border=True)
    x = 9.75
    chip = shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 1.7, 0.3 + 0.2 * len(role), 0.4, fill=BLUE_TINT, radius=0.5)
    text(s, x, 1.7, 0.3 + 0.2 * len(role), 0.4, role, size=13, bold=True, color=BLUE,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    yy = 2.35
    for i, (head, body) in enumerate(points):
        circle_num(s, x, yy + 0.02, 0.32, str(i + 1), YEAR[i % 5], size=12)
        text(s, x + 0.45, yy - 0.02, 2.55, 0.4, head, size=15, bold=True)
        text(s, x + 0.45, yy + 0.36, 2.55, 0.9, body, size=13, color=MUTED)
        yy += 1.3
    caption(s, SHOT_NOTE)
    return s


# ======================== 投影片 ========================
# 1 封面
s = new_slide(notes="開場：組員自我介紹，說明今天依書面報告（2026-10-28 正式版）報告系統目的、設計、現況與展示。")
for i, col in enumerate(YEAR):
    shape(s, MSO_SHAPE.OVAL, 0.9 + i * 0.42, 1.25, 0.26, 0.26, fill=col)
text(s, 0.9, 1.75, 11, 0.5, "康寧大學 資訊管理科　專題報告", size=18, color=MUTED)
text(s, 0.9, 2.3, 11.5, 1.2, "資管科智慧學習歷程系統", size=48, bold=True)
text(s, 0.9, 3.45, 11, 0.6, "把五年，拼成下一站", size=24, color=BLUE, bold=True)
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.9, 4.6, 7.75, 1.75, fill=GRAY_TINT, radius=0.08)
text(s, 1.15, 4.78, 7.4, 1.5, [
    [("專題生　", {"bold": True}), ("111534105 田心于　111534107 張馨羽　111534124 林承諺", {})],
    [("指導老師　", {"bold": True}), ("李栢松 老師", {})],
    [("報告日期　", {"bold": True}), ("中華民國 115 年 11 月 04 日", {})],
], size=15, spacing=8)
picture_fit(s, SHOTS / "00_index.png", 8.95, 4.45, 3.75, 2.1, border=True)

# 2 目錄
s = new_slide(notes="目錄：依書面報告章節，緒論、系統規格、系統設計、實作現況、系統展示，最後是決議與規劃。")
text(s, 0.6, 0.82, 12, 0.7, "目錄", size=30, bold=True)
toc = [("緒論", "開發背景、動機、目的、與既有做法的差異、開發工具"),
       ("系統規格", "使用者角色、功能需求、登入者權限"),
       ("系統設計", "使用案例圖、系統架構、流程圖、資料庫關聯圖"),
       ("實作現況", "資料生命週期、驗收方式與目前狀態、主要限制"),
       ("系統展示", "學生、班導師、科辦、管理員的實際畫面"),
       ("決議與規劃", "V2 決議事項、時程、分工、結論")]
for i, (h, b) in enumerate(toc):
    col, row = i % 2, i // 2
    x, y = 0.6 + col * 6.15, 1.85 + row * 1.6
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, 5.95, 1.35, fill=GRAY_TINT, radius=0.08)
    circle_num(s, x + 0.3, y + 0.38, 0.6, str(i + 1), YEAR[i % 5] if i < 5 else INK, size=20)
    text(s, x + 1.15, y + 0.22, 4.6, 0.45, h, size=20, bold=True)
    text(s, x + 1.15, y + 0.7, 4.6, 0.5, b, size=13, color=MUTED)

# 3 系統特色
s = new_slide("緒論", "摘要的三個設計重點。強調：OCR 與 AI 只給候選，正式資料一律由人確認。")
title(s, "一套陪學生走五年的學習歷程系統",
      "學生依年級看進度、上傳證明，經辨識與本人確認成為學習證據，再寫成有依據的自傳，最後由班導師確認送審版本")
cards = [("責任分工", "檔案儲存、文件協作交給成熟的雲端服務；本系統專注五年脈絡、資料結構化、證據引用、缺件規則與教師確認。"),
         ("人工確認", "OCR 與 AI 只提供候選結果與建議；正式資料與送審內容，一律由學生或教師確認。"),
         ("最小資料", "送往外部 AI 前，先移除姓名、學號、證號等非必要識別資訊。")]
for i, (h, b) in enumerate(cards):
    x = 0.6 + i * 4.1
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 2.4, 3.85, 3.6, fill=GRAY_TINT, radius=0.06)
    circle_num(s, x + 0.35, 2.75, 0.7, str(i + 1), YEAR[i], size=22)
    text(s, x + 0.35, 3.65, 3.2, 0.5, h, size=22, bold=True)
    text(s, x + 0.35, 4.25, 3.2, 1.6, b, size=16, color=MUTED)
caption(s, "資料來源：書面報告「摘要」")

# 4 背景與動機
s = new_slide("緒論", "背景：資料多在升學前才整理。動機三點，對應學生、升學、導師三方的困擾。")
title(s, "開發背景與動機")
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.6, 1.7, 12.13, 1.3, fill=BLUE_TINT, radius=0.08)
text(s, 0.95, 1.85, 11.5, 1.05,
     "資管科學生在學期間會累積成績、證照、競賽、實習與專題等資料，但多數人在升學或求職前才開始整理；"
     "資料散在不同檔案與時間點，難以回頭證明某項成就和目標學校、科系的關係。", size=16, anchor=MSO_ANCHOR.MIDDLE)
pains = [("新生不知道從哪裡開始", "五年要做什麼、先做什麼，沒有人一步一步告訴他。"),
         ("升學條件要自己比對", "想申請二技等管道時，要在大量公告與資料夾中自行比對條件，過程混亂。"),
         ("導師沒有固定的送審版本", "導師要審自傳與資料，卻難以確認內容是否與證據一致。")]
for i, (h, b) in enumerate(pains):
    x = 0.6 + i * 4.1
    circle_num(s, x, 3.45, 0.55, str(i + 1), YEAR[i + 2], size=18)
    text(s, x + 0.7, 3.45, 3.25, 0.55, h, size=18, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    text(s, x + 0.7, 4.1, 3.25, 1.6, b, size=15, color=MUTED)

# 5 開發目的
s = new_slide("緒論", "五個目的，第 5 點是設計底線：AI 不決定資格、不給分、不發布規則。")
title(s, "開發目的")
goals = ["建立五年學習路線，依年級顯示「現在該做什麼」",
         "把證明文件轉成結構化資料，並保留可回查的來源",
         "讓自傳的每一段都能指出它依據哪一筆證據",
         "讓導師審閱固定的送審版本，而不是不斷變動的草稿",
         "把 AI 限制在輔助角色，不決定資格、不給分、不發布規則"]
for i, g in enumerate(goals):
    y = 1.75 + i * 1.0
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.6, y, 12.13, 0.82, fill=GRAY_TINT if i < 4 else BLUE_TINT, radius=0.2)
    circle_num(s, 0.8, y + 0.16, 0.5, str(i + 1), YEAR[i], size=16)
    text(s, 1.55, y, 11, 0.82, g, size=18, bold=i == 4, anchor=MSO_ANCHOR.MIDDLE)

# 6 與既有做法的差異
s = new_slide("緒論", "和現在的做法比較。重點是「證據編號」與「送審快照」兩個機制。")
title(s, "與既有做法的差異")
rows = [["既有做法", "本系統的做法"],
        ["證明文件分散保存，靠學生自行整理", "上傳後形成學習證據，每筆證據有固定編號"],
        ["自傳由學生自行撰寫，無法確認依據", "自傳段落標示引用的證據編號，學生可檢查"],
        ["導師看到的是不斷修改的文件", "導師審閱送審當時的快照，之後修改另存新版"],
        ["升學條件查詢要逐份比對", "缺件檢查與目標校系條件以規則列出，並標示來源"]]
table(s, rows, 0.6, 1.8, 12.13, [5.6, 6.53], size=17, header_size=16, row_h=0.95,
      cell_colors={(i, 1): BLUE for i in range(1, 5)})

# 7 開發環境與工具
s = new_slide("緒論", "開發工具照實際使用：主要用 Antigravity IDE。資料庫正式設定 MySQL 8.0，自動測試用 SQLite 記憶體資料庫。")
title(s, "開發環境與工具")
tools = [("後端", "Python 3、Flask 3\nFlask-SQLAlchemy、Flask-Migrate"),
         ("資料庫", "MySQL 8.0（正式設定）\n自動測試用 SQLite 記憶體資料庫"),
         ("前端", "Jinja2 模板\n純 HTML／CSS、少量 JavaScript"),
         ("文字辨識", "RapidOCR（PP-OCRv5）\n在本機辨識，原檔不送外部"),
         ("AI（選用）", "Google Gemini API\n自傳建議、資料整理"),
         ("文件匯出", "python-docx\n備審資料 Word 檔"),
         ("測試", "pytest 自動化測試"),
         ("開發工具", "Antigravity IDE、Git、VS Code")]
for i, (h, b) in enumerate(tools):
    col, row = i % 4, i // 4
    x, y = 0.6 + col * 3.07, 1.8 + row * 2.55
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, 2.87, 2.3, fill=GRAY_TINT, radius=0.06)
    shape(s, MSO_SHAPE.OVAL, x + 0.3, y + 0.35, 0.22, 0.22, fill=YEAR[i % 5])
    text(s, x + 0.65, y + 0.22, 2.1, 0.5, h, size=18, bold=True)
    text(s, x + 0.3, y + 0.85, 2.45, 1.35, b.split("\n"), size=14, color=MUTED, spacing=4)
caption(s, "OCR 套件依程式現況補列（書面報告第五章：已改用本機 RapidOCR）")

# 8 使用者角色
s = new_slide("系統規格", "四種登入角色。教師端只做班導師（決議 D1）；專任與指導老師不建立登入角色，資料庫保留關係欄位。")
title(s, "使用者角色")
roles = [("學生", "查看五年路線、上傳證明、確認辨識結果、查看缺件、撰寫自傳、送審", "只能操作本人資料；AI 草稿須由學生確認"),
         ("班導師", "查看本班進度、在自傳段落留言、確認送審版本", "只能存取指派班級；只確認學生實際送審的版本"),
         ("科辦／行政", "電子證明、公告、表單", "不因角色存在而取得備審內容審查權"),
         ("系統管理員", "帳號、規則、資料來源、AI 與 Google 設定、稽核", "管理操作需留紀錄；不代替學生或教師確認內容")]
for i, (h, work, bound) in enumerate(roles):
    x = 0.6 + i * 3.07
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 1.75, 2.87, 4.6, fill=GRAY_TINT, radius=0.05)
    circle_num(s, x + 0.3, 2.0, 0.62, h[0], YEAR[i], size=18)
    text(s, x + 1.05, 2.05, 1.75, 0.55, h, size=20, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    text(s, x + 0.3, 2.85, 2.35, 0.35, "主要工作", size=13, bold=True, color=BLUE)
    text(s, x + 0.3, 3.2, 2.35, 1.5, work, size=14)
    text(s, x + 0.3, 4.75, 2.35, 0.35, "界線", size=13, bold=True, color=YEAR[3])
    text(s, x + 0.3, 5.1, 2.35, 1.2, bound, size=14, color=MUTED)
caption(s, "專任教師與專題指導教師本階段不建立登入角色，資料庫保留關係欄位（決議 D1）")

# 9 功能需求
s = new_slide("系統規格", "M1～M14 的狀態以書面報告為準（2026-10-16 填寫，M4 於 10-28 更新）。綠色完成、橘色部分完成或待決定、灰色規劃中。")
title(s, "功能需求與目前狀態", "狀態以正式書面報告（2026-10-28 版）為準；「本機」表示在本機展示版完成，尚未正式環境驗收")
feats = [("M1", "登入與四種角色權限", "本機完成，正式帳號待驗收", WARN),
         ("M2", "五年學習路線首頁", "本機完成", OK),
         ("M3", "上傳證明文件", "介面完成；先存本機", WARN),
         ("M4", "OCR 辨識", "本機 RapidOCR 實際辨識，須學生確認", OK),
         ("M5", "欄位規則檢查", "規劃中", TODO),
         ("M6", "學生確認", "完成（本機）", OK),
         ("M7", "學習證據", "完成（本機）", OK),
         ("M8", "有依據的自傳草稿", "完成（本機）；AI 為選用", OK),
         ("M9", "導師確認送審版", "完成（本機）", OK),
         ("M10", "刪除與保留", "保存期限待學校政策決定", WARN),
         ("M11", "操作紀錄", "部分完成", WARN),
         ("M12", "失敗時回到人工流程", "部分完成", WARN),
         ("M13", "自傳歷史版本", "存版完成；列表畫面待做", WARN),
         ("M14", "送 AI 前去識別化", "規劃中，需測試證明", TODO)]
for half in range(2):
    sub = feats[half * 7:(half + 1) * 7]
    rows = [["編號", "功能", "狀態"]] + [[a, b, c] for a, b, c, _ in sub]
    colors = {(i + 1, 2): col for i, (_, _, _, col) in enumerate(sub)}
    table(s, rows, 0.6 + half * 6.2, 2.1, 5.93, [0.75, 2.38, 2.8], size=13, header_size=13, row_h=0.58,
          first_col_bold=True, cell_colors=colors)

# 10 登入者權限
s = new_slide("系統規格", "權限以後端檢查為準，畫面隱藏按鈕不算權限控制。每次存取檢查三件事。")
title(s, "登入者權限（表 3-1）", "權限以後端檢查為準：已登入？角色允許？資料屬於本人或指派班級？")
rows = [["登入者", "可以做的事", "不能做的事"],
        ["學生", "讀寫與確認自己的資料；建立與重新送審；讀取公告、資訊、表單", "看別人的資料；確認自己的送審版本"],
        ["班導師", "讀取本班學生資料；送審版本段落註解；修改自傳；確認送審版本；查看本班缺曠合計", "看別班學生；審核成績單、證照與競賽證明"],
        ["科辦／行政", "電子獎狀核准或退回；表單下載區上架、改版、下架；讀取公告", "審查備審內容"],
        ["系統管理員", "維護帳號、角色、班級；核對與發布規則、來源、分類、公告；查詢操作紀錄", "代替學生或教師確認內容"]]
table(s, rows, 0.6, 2.1, 12.13, [1.8, 6.6, 3.73], size=14, header_size=14, row_h=0.9, first_col_bold=True)

# 11-14 使用案例圖
uc = [("D-01-use-case-student.png", "學生使用案例圖", "圖 1",
       [("五年路線與下一步", "依年級看進度，首頁提示今天先做哪一步"),
        ("上傳與核對辨識結果", "成績單、證照上傳後，本人確認才寫入"),
        ("認識二技與校系排行", "準備度是建議值，目標校系由學生自己決定"),
        ("有依據的自傳與送審", "段落引用證據編號，送出後由班導師確認")]),
      ("D-01-use-case-teacher.png", "班導師使用案例圖", "圖 2",
       [("查看本班進度", "只能看指派班級的學生"),
        ("段落留言與修改", "針對送審版本的段落給意見"),
        ("確認送審版本", "確認的是送審當時的快照"),
        ("班級統計", "虛線表示後續功能")]),
      ("D-01-use-case-staff.png", "科辦／科助使用案例圖", "圖 3",
       [("電子獎狀", "核准或退回學生申請"),
        ("表單下載區", "上架、改版、下架表單"),
        ("公告", "讀取與發布公告"),
        ("界線", "不審查備審內容")]),
      ("D-01-use-case-admin.png", "系統管理者使用案例圖", "圖 4",
       [("帳號與班級", "維護帳號、角色、班級"),
        ("規則與資料來源", "核對後才發布招生規則與來源"),
        ("排行篩選選項", "維護校系排行的篩選選項"),
        ("操作紀錄", "查詢登入、確認、送審等紀錄")])]
for fig, name, no, side in uc:
    figure_slide("系統設計", name, IMG / fig, f"{no}　{name}",
                 f"{no} {name}。右側是這個角色最重要的四件事。", side=side, side_w=4.4)

# 15 系統架構
s = new_slide("系統設計", "四層架構。後端是唯一的權限邊界；外部服務不直接取得整個雲端空間的存取權。")
title(s, "系統架構")
picture_fit(s, IMG / "D-05-system-architecture.png", 0.6, 1.6, 12.13, 3.4)
layers = [("瀏覽器介面", "四種角色依權限操作"),
          ("Flask 後端", "身分、權限、規則、服務調度與稽核；唯一的權限邊界"),
          ("資料與檔案", "MySQL 存業務資料與檔案索引；附件先存本機"),
          ("外部服務", "OCR 在本機；Gemini 選用；Google 服務尚未實機驗收")]
for i, (h, b) in enumerate(layers):
    x = 0.6 + i * 3.07
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 5.2, 2.87, 1.65, fill=GRAY_TINT, radius=0.08)
    circle_num(s, x + 0.2, 5.35, 0.4, str(i + 1), YEAR[i], size=13)
    text(s, x + 0.7, 5.33, 2.1, 0.45, h, size=16, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    text(s, x + 0.2, 5.85, 2.5, 0.95, b, size=13, color=MUTED)
caption(s, "圖 5　系統架構圖")

# 16 登入導頁
figure_slide("系統設計", "登入與角色導頁流程", IMG / "D-02-login-role-routing.png", "圖 6　登入與角色導頁流程圖",
             "登入後依角色導向各自的首頁；權限一律由後端檢查。",
             side=[("同一個登入頁", "四種角色共用，學生用學號登入"),
                   ("依角色導頁", "學生、導師、科辦、管理員各有首頁"),
                   ("後端檢查權限", "隱藏按鈕不算權限控制")], side_w=4.6)

# 17-18 學生主線（拆兩頁）
split_slides("系統設計", "學生主線流程", "D-10-main-line-flow.png", "圖 7　學生主線流程圖",
             "學生主線是整個系統的核心：上傳 → OCR → 本人確認 → 學習證據 → 自傳 → 送導師確認。選校不限數量，"
             "報名時依各管道當年度簡章提醒規定。圖很長，拆成兩頁、四段，照編號讀。", slides=2, per_slide=2)

# 19 上傳與確認
split_slides("系統設計", "資料上傳、OCR 擷取與本人確認", "D-26-student-upload-flow.png",
             "圖 8　學生資料上傳、擷取與本人確認流程圖",
             "OCR 在本機做，加規則整理；學生在核對頁確認後才寫入。確認過的資料要給 AI 時才先去識別化。",
             slides=1, per_slide=3)

# 20-22 其他流程
figure_slide("系統設計", "學校資料匯入流程", IMG / "D-21-school-data-import-flow.png", "圖 9　學校資料匯入流程圖",
             "學校資料（名單、課程規則等）由管理員匯入，核對後才生效。",
             side=[("管理員匯入", "名單、課程規則等學校資料"),
                   ("核對後生效", "匯入結果先檢查再寫入"),
                   ("留紀錄", "匯入動作寫入操作紀錄")], side_w=4.3)
figure_slide("系統設計", "導師確認流程", IMG / "D-16-teacher-confirm-flow.png", "圖 10　導師確認流程圖",
             "導師看到的是送審快照；學生再修改時，導師版本不變。",
             side=[("學生送審", "送出時建立快照"),
                   ("導師留言或確認", "針對快照的段落"),
                   ("學生再修改", "另存新版，舊快照不變")], side_w=4.3)
figure_slide("系統設計", "科辦核准電子獎狀流程", IMG / "D-18-staff-service-record-flow.png", "圖 11　科辦核准電子獎狀流程圖",
             "圖中「科辦找指導老師」是描述現行人工流程，刻意保留，不是系統角色。",
             side=[("學生申請", "上傳活動或服務佐證"),
                   ("科辦核准或退回", "核准後成為電子證明"),
                   ("現行人工流程", "圖中找指導老師的步驟，是描述現況")], side_w=4.3)

# 23 表單下載
split_slides("系統設計", "科辦表單下載區流程", "D-20-form-download-flow.png", "圖 12　科辦表單下載區流程圖",
             "科辦上架、改版、下架表單；學生讀取。", slides=1, per_slide=2)
# 24-25 招生資料更新
split_slides("系統設計", "招生資料更新流程", "D-13-admission-rule-update-flow.png", "圖 13　招生資料更新流程圖",
             "招生規則由管理員核對來源後才發布；AI 不得自行發布招生規則。", slides=2, per_slide=2)
# 26 維護校系備審要求
split_slides("系統設計", "管理者維護校系備審要求流程", "D-17-admin-maintain-requirements.png",
             "圖 14　系統管理者維護校系備審要求流程圖",
             "各校系的備審要求由管理員維護，標示來源。", slides=1, per_slide=2)

# 27-29 ERD
erd = [("D-09-erd-part1-learning.png", "ERD－帳號、學習資料與學校資料匯入", "圖 15"),
       ("D-09-erd-part2-review.png", "ERD－校系、目標校系、導師確認與自傳", "圖 16"),
       ("D-09-erd-part3-sources.png", "ERD－資料來源、公告、表單與操作紀錄", "圖 17")]
for fig, name, no in erd:
    figure_slide("系統設計", name, IMG / fig, f"{no}　{name}",
                 f"{no}。資料表完整欄位以 ERD 為準。")

# 30 資料與檔案生命週期
s = new_slide("實作現況", "檔案與業務資料分開管理。送審建立快照，之後修改另存新版，舊快照不變。")
title(s, "資料與檔案生命週期", "「檔案」與「業務資料」分開管理")
steps = [("上傳", "接收附件", "檔案識別碼、類別、年級、所屬學生、狀態"),
         ("索引", "寫入資料庫", "業務關聯與中繼資料"),
         ("確認", "學生確認候選欄位", "正式資料與證據編號"),
         ("送審", "建立快照", "送審當時的內容與證據清單"),
         ("修改", "草稿變動", "另存新版，舊快照不變")]
for i, (h, act, keep) in enumerate(steps):
    x = 0.6 + i * 2.46
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 2.3, 2.2, 3.9, fill=GRAY_TINT, radius=0.06)
    circle_num(s, x + 0.75, 2.55, 0.7, str(i + 1), YEAR[i], size=22)
    text(s, x + 0.15, 3.4, 1.9, 0.5, h, size=22, bold=True, align=PP_ALIGN.CENTER)
    text(s, x + 0.15, 3.95, 1.9, 0.5, act, size=14, bold=True, color=BLUE, align=PP_ALIGN.CENTER)
    text(s, x + 0.2, 4.55, 1.8, 1.5, keep, size=13, color=MUTED)
    if i < 4:
        arrow = shape(s, MSO_SHAPE.RIGHT_ARROW, x + 2.22, 4.05, 0.22, 0.3, fill=LINE)

# 31 驗收方式與目前狀態
s = new_slide("實作現況", "「有程式」不等於「已完成」。六類驗收分開記錄；真實 MySQL、Google 服務、老師與組員確認都還沒完成，要照實說。")
title(s, "驗收方式與目前狀態", "「有程式」不等於「已完成」，六類驗收分開記錄")
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.6, 2.1, 3.6, 4.7, fill=BLUE_TINT, radius=0.06)
text(s, 0.85, 2.35, 3.2, 0.4, "自動測試", size=16, bold=True, color=BLUE)
text(s, 0.85, 2.85, 3.2, 1.2, "926", size=66, bold=True, color=BLUE)
text(s, 0.85, 4.1, 3.2, 0.5, "項通過、0 項失敗", size=18, bold=True)
text(s, 0.85, 4.7, 3.2, 2.0, "2026-10-28，提交 04f7cdd，SQLite 記憶體資料庫；另有 9 項需要本機 OCR 模型或 Node 的測試略過",
     size=12, color=MUTED)
rows = [["驗收類別", "狀態"],
        ["本機展示", "四種角色的主要流程可操作；合成資料，重啟即清空"],
        ["真實 MySQL", "未完成"],
        ["瀏覽器實操", "桌機展示與部分鍵盤操作已驗收；手機寬度與減少動態效果待測"],
        ["Google 服務實機", "未完成；僅有單一檔案選取的原型，未連接正式帳號"],
        ["老師與組員確認", "未完成"]]
colors = {(1, 1): OK, (2, 1): YEAR[3], (3, 1): WARN, (4, 1): YEAR[3], (5, 1): YEAR[3]}
table(s, rows, 4.5, 2.1, 8.23, [2.3, 5.93], size=14, header_size=14, row_h=0.78, first_col_bold=True,
      cell_colors=colors)

# 32 主要限制
s = new_slide("實作現況", "主要限制照實說，特別是 Google 服務和資料保存政策。")
title(s, "主要限制")
limits = [("OCR 結果只是候選", "已改用本機 RapidOCR 讀取真實檔案，原始檔不送外部服務；結果須學生在核對頁確認。"),
          ("外部 AI 為選用", "未設定金鑰時，系統回到人工流程。"),
          ("Google 服務未驗證", "權限、撤銷與錯誤回復尚未驗證。"),
          ("保存政策未定", "學校的資料保存政策尚未決定，不能宣稱永久刪除流程已完成。")]
for i, (h, b) in enumerate(limits):
    col, row = i % 2, i // 2
    x, y = 0.6 + col * 6.15, 1.8 + row * 2.5
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, 5.95, 2.2, fill=GRAY_TINT, radius=0.06)
    circle_num(s, x + 0.3, y + 0.32, 0.55, "!", YEAR[3] if i else YEAR[2], size=18)
    text(s, x + 1.05, y + 0.32, 4.7, 0.55, h, size=20, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    text(s, x + 1.05, y + 1.0, 4.7, 1.1, b, size=15, color=MUTED)

# 33-47 系統展示
shots = [
    ("系統首頁", "訪客", "00_index.png",
     [("把五年，拼成下一站", "散落的資料夾代表五年累積的經歷"),
      ("登入後開始整理", "右上角進入登入頁")],
     "首頁主題：散落的每一件事，都能成為出發的線索。"),
    ("登入", "四種角色", "00_login.png",
     [("同一個登入頁", "學生、導師、科辦、管理員共用"),
      ("展示站快速登入", "只提供合成帳號，僅為測試資料")],
     "登入頁。展示時用合成帳號，不使用真實帳密。"),
    ("我的五年", "學生", "student_student_dashboard.png",
     [("五年路線", "專一探索到專五出發，標出目前位置"),
      ("四類資料", "成績與證照、活動與經歷、目標校系、備審資料"),
      ("今天先完成哪一步", "累積比例只是比例，不是錄取機率")],
     "學生首頁：五年路線與下一步。強調累積比例不是錄取機率。"),
    ("上傳成績單", "學生", "ocr_1_upload.png",
     [("成績單與證照分開傳", "避免傳錯地方"),
      ("PDF、PNG、JPG", "可旋轉預覽後再上傳"),
      ("不存學校帳密", "上傳後要逐筆確認")],
     "上傳頁。這裡用的是合成的假成績單。"),
    ("本機辨識中", "學生", "ocr_2_after_submit.png",
     [("原檔不送外部", "在本機用 RapidOCR 辨識"),
      ("逐步顯示進度", "收到檔案、辨識文字、整理成清單"),
      ("讀完自動跳轉", "直接進入核對頁")],
     "辨識中畫面。OCR 在本機執行，原檔不會傳到外部服務。"),
    ("核對辨識結果", "學生", "ocr_3_review_crop.png",
     [("左圖右表", "左邊原始文件，右邊辨識到的課程"),
      ("本例辨識 19 門", "合成成績單，真實本機 OCR"),
      ("確認後才寫入", "可修改科目、學分、成績、學期")],
     "核對頁：學生逐筆核對、修正後確認才寫入正式資料（決議 D5）。本例是真實本機 OCR 辨識合成成績單的結果。"),
    ("成績與學分", "學生", "student_student_learning-profile.png",
     [("我上傳的文件", "每份文件都可回查來源"),
      ("已確認的成績", "確認後狀態顯示「已確認」")],
     "確認後的成績進入成績與學分表。"),
    ("活動與經歷", "學生", "student_student_portfolio.png",
     [("對準目標校系", "提示這些活動最能用在哪一間"),
      ("逐筆標示", "年級、類別與待補的來源")],
     "活動與經歷：依目標校系提示用途。"),
    ("校系排行", "學生", "student_student_matching.png",
     [("能不能報＋準備度", "每間都寫理由，不能報也說明原因"),
      ("只是找方向", "準備度是建議值，不是錄取機率"),
      ("可切換", "二技／插大、橫條／長條")],
     "校系排行：系統只幫忙找方向，目標校系由學生自己決定。"),
    ("目標校系", "學生", "student_student_targets.png",
     [("不限數量", "想去的學校隨時可換"),
      ("依簡章提醒", "報名時依各管道當年度規定提醒")],
     "目標校系：選校不限數量（2026-10-21 指導老師意見）。"),
    ("招生時程", "學生", "student_student_schedule.png",
     [("依簡章列日程", "每項附來源"),
      ("標示查詢日期", "新一屆未公告時會提醒")],
     "招生時程：依官方簡章整理，標示查詢日期。"),
    ("小助手寫自傳", "學生", "student_student_autobiography.png",
     [("先說 AI 不能做的事", "給分、退件、核定資格、發布招生規則"),
      ("逐題回答", "想不到可以跳過，AI 不替你編"),
      ("只用已確認資料", "右側列出證據編號 F1、F2…")],
     "自傳：AI 只用學生已確認的資料，並標出證據編號。"),
    ("導師工作台", "班導師", "teacher_teacher_dashboard.png",
     [("本班學生", "各類資料筆數與目標校系"),
      ("待確認件數", "只看指派班級")],
     "班導師首頁：只看本班。"),
    ("待處理件", "科辦", "staff_staff_dashboard.png",
     [("電子獎狀", "待核准件數"),
      ("已送審成果", "填寫共同結論與說明")],
     "科辦首頁：處理電子獎狀與成果。"),
    ("操作紀錄", "系統管理員", "admin_admin_audit-logs.png",
     [("每個動作都留紀錄", "登入、確認、送審、刪除、上傳"),
      ("可依動作篩選", "管理員也不能代替學生確認")],
     "操作紀錄：只記動作與對象，不記內容。"),
]
for t, role, shot, pts, note in shots:
    shot_slide(t, role, shot, pts, note + "（畫面取自 2026-11-03 開發分支本機展示站，合成資料）")

# 48 決議事項
s = new_slide("決議與規劃", "V2 六項決議，2026-10-16 經指導老師與組員同意。另有保存政策的衝突待學校決定。")
title(s, "V2 架構調整與決議事項", "2026-10-16 經指導老師與組員同意")
rows = [["編號", "問題", "決議"],
        ["D1", "教師端 V1 是否只做班導？", "只做班導，其他教師關係不納入"],
        ["D2", "是否使用 Google Drive 與 Docs，不自行重做？", "同意"],
        ["D3", "沒有學校管理員權限時，是否先用個人測試帳號驗證 API？", "先用個人雲端硬碟"],
        ["D4", "自傳是否定位為「證據＋學生反思的可追溯草稿」？", "同意，並可查看歷史版本"],
        ["D5", "OCR 與 AI 結果是否都必須人工確認？", "AI 先抓出欄位，學生確認正確後才送出"],
        ["D6", "下一階段是否優先跑通「上傳 → OCR → 證據 → 自傳 → 送審」？", "同意"]]
table(s, rows, 0.6, 2.05, 12.13, [0.9, 6.9, 4.33], size=14, header_size=14, row_h=0.6, first_col_bold=True)
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.6, 6.4, 12.13, 0.5, fill=BLUE_TINT, radius=0.3)
text(s, 0.85, 6.4, 11.7, 0.5, "待學校決定：歷史版本不實體刪除 vs. 軟刪除後依政策永久清理，須先取得學校的保存政策",
     size=14, bold=True, color=BLUE, anchor=MSO_ANCHOR.MIDDLE)

# 49 V1 與 V2 範圍
s = new_slide("決議與規劃", "本階段只驗收 V1；V2 項目不在本階段驗收範圍。")
title(s, "V1 與 V2 範圍", "V2 項目不在本階段驗收範圍內")
for i, (h, items, fill) in enumerate([
        ("V1　本階段", ["四種角色", "五年學習歷程", "上傳與 OCR 至學生確認", "學習證據", "可追溯自傳", "班導送審", "基本稽核"], BLUE_TINT),
        ("V2　之後", ["學校 Workspace 與共用雲端硬碟", "Google Docs 正式協作", "表單與試算統計", "其他教師關係", "背景工作佇列", "正式備份與監控"], GRAY_TINT)]):
    x = 0.6 + i * 6.15
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 2.05, 5.95, 4.8, fill=fill, radius=0.05)
    text(s, x + 0.4, 2.3, 5.2, 0.55, h, size=22, bold=True, color=BLUE if i == 0 else INK)
    for k, it in enumerate(items):
        shape(s, MSO_SHAPE.OVAL, x + 0.45, 3.1 + k * 0.52 + 0.12, 0.16, 0.16, fill=YEAR[k % 5] if i == 0 else TODO)
        text(s, x + 0.8, 3.1 + k * 0.52, 4.9, 0.42, it, size=16)

# 50 時程
s = new_slide("決議與規劃", "時程以指導老師回饋為準。今天 11/4 交投影片；11 月中 70%；12 月初審核。")
title(s, "開發時程", "以指導老師的回饋為準，必要時調整")
rows = [["日期", "目標"],
        ["2026-10-20", "統一附件儲存位置，完成刪除與保留的決議前置作業"],
        ["2026-10-25", "離線 OCR 與去識別化，規則檢查"],
        ["2026-10-28", "主線串接與自動測試，自傳歷史版本列表"],
        ["2026-10-31", "瀏覽器實操驗收（桌機、手機、鍵盤、減少動態效果）"],
        ["2026-11-04", "投影片交給指導老師"],
        ["2026-11 月中", "完成度 70% 以上"],
        ["2026-12 月初", "專題審核"]]
table(s, rows, 0.6, 2.05, 12.13, [2.6, 9.53], size=15, header_size=15, row_h=0.6, first_col_bold=True,
      cell_colors={(5, 0): BLUE, (5, 1): BLUE})

# 50-1 甘特圖
figure_slide("決議與規劃", "2026 年開發甘特圖", IMG / "D-24-gantt-2026.png", "圖 18　2026 年開發甘特圖",
             "甘特圖為 V2 對照版（2026-10-16 製），與書面報告圖 18 相同。")

# 51 分工
s = new_slide("決議與規劃", "工作分配規劃；實際完成項目以開發與測試紀錄為準。")
title(s, "分工", "本表為工作分配規劃，實際完成項目以開發與測試紀錄為準")
members = [("田心于", "111534105", "需求分析、學生端介面、文件整理、簡報與展示規劃"),
           ("張馨羽", "111534107", "資料庫設計、後端功能、登入與權限、招生規則維護"),
           ("林承諺", "111534124", "AI 模組封裝（Gemini API）、文件辨識與資料整理、系統測試")]
for i, (n, sid, work) in enumerate(members):
    x = 0.6 + i * 4.1
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 2.2, 3.85, 3.1, fill=GRAY_TINT, radius=0.06)
    circle_num(s, x + 0.35, 2.5, 0.8, n[0], YEAR[i], size=24)
    text(s, x + 1.35, 2.52, 2.4, 0.45, n, size=22, bold=True)
    text(s, x + 1.35, 2.98, 2.4, 0.35, sid, size=13, color=MUTED)
    text(s, x + 0.35, 3.65, 3.2, 1.5, work, size=17)
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.6, 5.65, 12.13, 0.7, fill=BLUE_TINT, radius=0.3)
text(s, 0.9, 5.65, 11.6, 0.7,"全體組員：架構討論、功能整合、使用者測試、成果展示", size=16, bold=True, color=BLUE,
     anchor=MSO_ANCHOR.MIDDLE)

# 52 結論與限制
s = new_slide("決議與規劃", "結論：兩個核心機制。限制四點照實說。後續依決議進行，不擴大範圍。")
title(s, "結論與限制")
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.6, 1.75, 5.6, 5.0, fill=BLUE_TINT, radius=0.05)
text(s, 0.95, 2.0, 5.0, 0.5, "完成了什麼", size=20, bold=True, color=BLUE)
text(s, 0.95, 2.6, 5.0, 1.3, "學生五年學習歷程的主要流程展示，並建立兩個核心機制，讓自傳與送審內容可以被檢查：", size=15)
for k, (h, b) in enumerate([("證據編號", "已確認的資料都有固定編號，自傳段落引用它"),
                            ("送審快照", "導師確認的是送審當時的版本")]):
    y = 4.0 + k * 1.25
    circle_num(s, 0.95, y, 0.5, str(k + 1), YEAR[k], size=16)
    text(s, 1.6, y - 0.03, 4.4, 0.45, h, size=17, bold=True)
    text(s, 1.6, y + 0.4, 4.4, 0.7, b, size=14, color=MUTED)
text(s, 6.65, 1.95, 6.0, 0.5, "目前的限制", size=20, bold=True)
lims = ["OCR 已用本機檔案實測（一份成績單 85 門課的課名全部讀對），但測試的版面與份數有限，辨識率尚未系統性評估",
        "Google 服務與 MySQL 尚未實機驗收",
        "資料保存期限與永久刪除政策，待學校決定",
        "系統未經真實學生長期使用，成效有待後續評估"]
for k, l in enumerate(lims):
    y = 2.6 + k * 1.05
    circle_num(s, 6.65, y, 0.42, str(k + 1), TODO, size=13)
    text(s, 7.25, y - 0.05, 5.45, 1.0, l, size=15)
caption(s, "後續工作依第七章的決議進行，不擴大範圍")

# 53 參考資料
s = new_slide("決議與規劃", "參考資料同書面報告。")
title(s, "參考資料")
refs = ["康寧大學資訊管理科資訊軟體開發組專題規定", "康寧大學資訊管理科近五年畢業專題成果報告",
        "Google Gemini API 官方文件", "Flask 官方文件", "Flask-SQLAlchemy 官方文件", "MySQL 8.0 Reference Manual",
        "python-docx 官方文件", "Google Workspace 與 Google Drive API 官方文件",
        "各校二技招生及技優甄審官方招生簡章與公開資料", "116 二技技優甄審時程與備審加權（修訂版）PDF",
        "111 學年度康寧大學資管科畢業門檻 PDF", "專題審查學習目標與評量對照表 PDF"]
for i, r in enumerate(refs):
    col, row = i // 6, i % 6
    x, y = 0.6 + col * 6.15, 1.8 + row * 0.82
    text(s, x, y, 0.55, 0.5, f"{i + 1}.", size=15, bold=True, color=BLUE)
    text(s, x + 0.55, y, 5.5, 0.75, r, size=15)

# 54 謝謝
s = new_slide(notes="結束，開放提問。可能被問的問題見 導師討論_2026-11-04_準備稿.md。")
for i, col in enumerate(YEAR):
    shape(s, MSO_SHAPE.OVAL, 5.62 + i * 0.42, 2.3, 0.26, 0.26, fill=col)
text(s, 0.6, 2.85, 12.13, 1.1, "謝謝聆聽", size=48, bold=True, align=PP_ALIGN.CENTER)
text(s, 0.6, 3.95, 12.13, 0.6, "敬請指導", size=24, color=BLUE, bold=True, align=PP_ALIGN.CENTER)
text(s, 0.6, 5.0, 12.13, 0.9, ["專題生：田心于、張馨羽、林承諺　｜　指導老師：李栢松 老師",
                                "資管科智慧學習歷程系統"], size=15, color=MUTED, align=PP_ALIGN.CENTER, spacing=6)

prs.core_properties.title = "資管科智慧學習歷程系統 專題報告"
prs.core_properties.author = "田心于、張馨羽、林承諺"
if OUT.exists():
    raise SystemExit(f"目標檔已存在，不覆蓋：{OUT}")
prs.save(OUT)
print("slides:", len(prs.slides), "->", OUT)

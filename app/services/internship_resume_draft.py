"""實習履歷草稿：學生在頁面上自己貼資料、拖進格子、貼圖，存起來（老師可以看），再下載學校格式的 Word。

- 不新增資料表：存成 LearningProfileOutput（output_type="internship_resume_draft"），每次儲存新增一筆，舊的保留。
- 系統有的資料（證照、經歷、自傳段落）只當「素材卡」給學生拖進去；沒有的（出生日期、電話、地址、操行、語文能力、
  缺曠、證照圖片、競賽圖片、成績單圖片）由學生自己填、自己貼。缺曠是學生自己輸入的數字，系統不自動帶入。
- 圖片沿用自傳貼圖的存放（autobiography_images）：本人與負責該班的導師看得到，不送 AI。
"""

from copy import deepcopy
from io import BytesIO

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.shared import Cm

from app.extensions import db
from app.models import LearningProfileOutput
from app.services import autobiography_images, internship_resume as resume

OUTPUT_TYPE = "internship_resume_draft"
CONDUCT = ["優", "甲", "乙", "丙", "丁"]
LANGUAGES = [("lang_en", "英語"), ("lang_ja", "日語"), ("lang_tw", "台語"), ("lang_hk", "客語")]
LEVELS = ["精通", "中等", "略懂"]
ABSENCE_ROWS = ["曠課", "遲到", "事假", "病假", "生理假", "公假", "喪假", "總計"]
CERT_IMAGE_SLOTS = 8   # 最少顯示幾格
CONTEST_SLOTS = 8
CERT_COLUMNS = ["labor", "international", "domestic", "other"]
CERT_ROWS = 6          # 學校格式「相關證照」每欄的列數（學生可以增減）
MAX_CERT_ROWS = 9           # 再多履歷表會被擠到第二頁
MAX_GRID = 40         # 證照、競賽各最多幾格
TRANSCRIPT_MAX = 4
ADDRESS_KINDS = (("縣", "市"), ("區", "鄉", "鎮", "市"))
FIELD_LIMIT = 120


def empty():
    return {
        "period": "", "email": "", "birth": ["", "", ""], "gender": "", "phone": "", "address": ["", "", ""], "photo": "",
        "address_kinds": ["", ""],
        "conduct": "", "langs": {key: "" for key, _ in LANGUAGES},
        "certimg": [{"name": "", "image": ""} for _ in range(CERT_IMAGE_SLOTS)],
        "contest": [{"caption": "", "image": ""} for _ in range(CONTEST_SLOTS)],
        "transcript": [], "absence": {"range": "", "rows": ["" for _ in ABSENCE_ROWS], "image": ""},
        "certcells": None,   # {欄: [6 格文字]}；None＝學生還沒自己編輯過，依勾選的證照預填
        "include": {"transcript": True, "cert": True, "contest": True, "absence": True},  # 這一頁要不要放進履歷
    }


def latest_row(student):
    return (LearningProfileOutput.query.filter_by(student_id=student.id, output_type=OUTPUT_TYPE)
            .order_by(LearningProfileOutput.id.desc()).first())


def load(student):
    """最新草稿；沒有就是空白。缺的欄位補預設值，舊草稿改版後也不會壞。"""
    row = latest_row(student)
    base = empty()
    if row:
        for key, value in (row.content_json or {}).items():
            if key in base:
                base[key] = value
        base["include"] = {**empty()["include"], **(base.get("include") or {})}
    return base


def saved_choices(student):
    """上次儲存的證照、經歷、自傳文字選擇；沒有存過回傳 None。"""
    row = latest_row(student)
    return (row.content_json or {}).get("choices") if row else None


def _text(value):
    return (value or "").strip()[:FIELD_LIMIT]


def _image(student, ref):
    ref = (ref or "").strip()
    return ref if ref and autobiography_images.image_path(student.id, ref) else ""


def _count(form, name, default, low=0, high=None):
    """證照、競賽的格子數（學生可以增加，也可以一格一格拿掉，拿光就等於整張表不放）；
    欄位沒送（舊頁面）用預設，不合理的數字夾在範圍內。"""
    try:
        value = int(form.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(value, high or MAX_GRID))


def parse(form, student):
    """把表單整理成乾淨的草稿；圖片編號一律檢查是這位學生自己的。"""
    draft = empty()
    draft["period"] = _text(form.get("period"))
    draft["email"] = _text(form.get("email"))[:80]
    draft["birth"] = [_text(form.get(f"birth_{i}"))[:4] for i in range(3)]
    draft["gender"] = form.get("gender") if form.get("gender") in ("男", "女") else ""
    draft["phone"] = _text(form.get("phone"))
    draft["address"] = [_text(form.get(f"addr_{i}")) for i in range(3)]
    draft["address_kinds"] = [
        form.get(f"addr_kind_{i}") if form.get(f"addr_kind_{i}") in allowed else ""
        for i, allowed in enumerate(ADDRESS_KINDS)
    ]
    draft["photo"] = _image(student, form.get("photo"))
    draft["conduct"] = form.get("conduct") if form.get("conduct") in CONDUCT else ""
    draft["langs"] = {key: (form.get(key) if form.get(key) in LEVELS else "") for key, _ in LANGUAGES}
    cert_count = _count(form, "certimg_count", CERT_IMAGE_SLOTS)
    contest_count = _count(form, "contest_count", CONTEST_SLOTS)
    draft["certimg"] = [{"name": _text(form.get(f"certimg_name_{i}")), "image": _image(student, form.get(f"certimg_image_{i}"))}
                        for i in range(cert_count)]
    draft["contest"] = [{"caption": _text(form.get(f"contest_caption_{i}")), "image": _image(student, form.get(f"contest_image_{i}"))}
                        for i in range(contest_count)]
    draft["transcript"] = autobiography_images.clean_ids(student.id, form.getlist("transcript_image"))[:TRANSCRIPT_MAX]
    if "certcells_present" in form:
        rows = _count(form, "certrows", CERT_ROWS, low=1, high=MAX_CERT_ROWS)
        draft["certcells"] = {key: [_text(form.get(f"cert_{key}_{n}")) for n in range(rows)] for key in CERT_COLUMNS}
    if "inc_present" in form:
        draft["include"] = {key: bool(form.get(f"inc_{key}")) for key in draft["include"]}
    draft["absence"] = {
        "range": _text(form.get("abs_range")),
        "rows": [_text(form.get(f"abs_{i}"))[:6] for i in range(len(ABSENCE_ROWS))],
        "image": _image(student, form.get("abs_image")),
    }
    return draft


def save(student, draft, choices=None):
    """存成新的一筆；choices 是證照與自傳的選擇（internship_resume.read_choices 的結果）。"""
    content = dict(draft)
    if choices is not None:
        content["choices"] = {
            "credentials": [{"id": c["id"], "column": c["column"]} for c in choices["credentials"]],
            "experiences": [{"id": e["id"], "section": e["section"]} for e in choices["experiences"]],
            "texts": choices["texts"],
            "bio_mode": choices.get("bio_mode", "guided"),
        }
    row = LearningProfileOutput(student_id=student.id, output_type=OUTPUT_TYPE, content_json=content, source_snapshot_json={})
    db.session.add(row)
    return row


FAMILY_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}


def family_paragraph(student, raw):
    """小助手把學生說的家庭生活整理成履歷用的一段。只用學生說的內容，不編；AI 不能用時原文整理後放進去。
    回傳 (文字, 說明)。送出前先遮蔽學號、電話等個資（ai_gateway 會做）。"""
    from app.services import ai_gateway
    raw = (raw or "").strip()[:1200]
    if not raw:
        raise ValueError("請先說說你的家庭生活。")
    prompt = ("你是資管科的自傳小助手。請把學生說的家庭生活整理成一段自傳文字（第一人稱、約 100 到 200 字、語氣自然誠懇）。"
              "只能使用學生說的內容，不可以編造事實、數字或人物；不要加標題。只輸出 JSON：{\"text\": \"...\"}。\n學生說的：" + raw)
    try:
        result, provider = ai_gateway.generate_json(prompt, FAMILY_SCHEMA, known=[(student.display_name or "", "〔姓名〕")] if student.display_name else [])
        text = str(result.get("text", "")).strip()
        if text:
            return text[:3000], "小助手已整理，請看過再改成你自己的話。"
    except Exception:  # noqa: BLE001  AI 沒開、沒金鑰或失敗都退回原文
        pass
    return raw, "AI 目前沒有開啟，先把你說的原文放進去，請自己再修。"


def has_content(draft):
    return any([draft["period"], any(draft["birth"]), draft["gender"], draft["phone"], any(draft["address"]),
                draft["photo"], draft["conduct"], any(draft["langs"].values()),
                any(c["name"] or c["image"] for c in draft["certimg"]),
                any(c["caption"] or c["image"] for c in draft["contest"]), draft["transcript"],
                draft["absence"]["range"], any(draft["absence"]["rows"]), draft["absence"]["image"]])


def address_text(draft):
    city, district, rest = draft["address"]
    kinds = draft.get("address_kinds", ["", ""])
    parts = []
    for value, kind in zip((city, district), kinds):
        if value:
            suffix = "" if kind and value.endswith(kind) else kind or " "
            parts.append(value + suffix)
    return ("".join(parts) + rest).strip()


# ---------- Word ----------

def _mark(options, chosen):
    return "　".join(("■" if item == chosen else "□") + item for item in options)


def _set_text(paragraph, text):
    for run in paragraph.runs[1:]:
        run.text = ""
    if paragraph.runs:
        paragraph.runs[0].text = text
    else:
        paragraph.add_run(text)


def _picture(cell, student, ref, width_cm):
    path = autobiography_images.image_path(student.id, ref) if ref else None
    if not path:
        return False
    first = cell.paragraphs[0]
    paragraph = first if not first.text.strip() else cell.add_paragraph()
    paragraph.add_run().add_picture(str(path), width=Cm(width_cm))
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER          # 圖片在格子裡置中（和學校 PDF 一樣）
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    return True


def _hide_borders(cell, *sides):
    """把格子的某幾條邊線設成不畫（學校 PDF 照片周圍沒有這幾條線）；tcBorders 的子項照結構定義的順序排。"""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    properties = cell._tc.get_or_add_tcPr()
    borders = properties.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        properties.insert_element_before(borders, "w:shd", "w:noWrap", "w:tcMar", "w:textDirection", "w:tcFitText",
                                         "w:vAlign", "w:hideMark")
    found = {tag: borders.find(qn(f"w:{tag}")) for tag in ("top", "left", "bottom", "right")}
    for tag in sides:
        if found[tag] is None:
            found[tag] = OxmlElement(f"w:{tag}")
        found[tag].set(qn("w:val"), "nil")
    for child in list(borders):
        borders.remove(child)
    for tag in ("top", "left", "bottom", "right"):
        if found[tag] is not None:
            borders.append(found[tag])


def _drop(element):
    """拿掉一個區塊；它前面如果是只有換頁的空段落也一起拿掉，免得多出空白頁。"""
    previous = element.getprevious()
    parent = element.getparent()
    if parent is None:
        return
    parent.remove(element)
    if previous is not None and previous.tag.endswith("}p") and not "".join(previous.itertext()).strip() \
            and previous.xpath('.//w:br[@w:type="page"]'):
        previous.getparent().remove(previous)


def _remove_unwanted_pages(document, include, transcript_table, cert_table, cert_heading, absence_anchor):
    """學生選「這一頁不放」的成績單、證照、缺曠記錄，從 Word 裡整頁拿掉（學校格式的空白表格也不留）。"""
    if not include.get("transcript", True) and transcript_table is not None:
        _drop(transcript_table)
    if not include.get("cert", True):
        for element in (cert_table, cert_heading):
            if element is not None:
                _drop(element)
    if not include.get("absence", True) and absence_anchor is not None:
        for sibling in list(absence_anchor.itersiblings()):
            if not sibling.tag.endswith("}sectPr"):
                sibling.getparent().remove(sibling)
        _drop(absence_anchor)


WPS_NS = "{http://schemas.microsoft.com/office/word/2010/wordprocessingShape}"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _fill_photo_box(document, cell, student, ref):
    """學校格式的「照片」是一個畫在格子裡的方框（沒有文字框）：把照片當成方框的填滿圖，照方框比例從中間裁。
    找不到方框回傳 False，由呼叫端改放在格子裡。"""
    from docx.oxml import parse_xml
    from PIL import Image
    path = autobiography_images.image_path(student.id, ref) if ref else None
    shape = next(cell._tc.iter(WPS_NS + "wsp"), None)
    if path is None or shape is None:
        return False
    properties = shape.find(WPS_NS + "spPr")
    fill = properties.find(f"{{{A_NS}}}noFill") if properties is not None else None
    if fill is None:
        return False
    extent = next(cell._tc.iter("{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent"), None)
    ratio = (int(extent.get("cx")) / int(extent.get("cy"))) if extent is not None else 3.33 / 3.76
    with Image.open(path) as source:
        image = source.convert("RGB")
    width, height = image.size
    if width / height > ratio:
        new_width = int(height * ratio)
        left = (width - new_width) // 2
        image = image.crop((left, 0, left + new_width, height))
    else:
        new_height = int(width / ratio)
        top = (height - new_height) // 2
        image = image.crop((0, top, width, top + new_height))
    data = BytesIO()
    image.save(data, "JPEG", quality=88)
    data.seek(0)
    rel_id, _ = document.part.get_or_add_image(data)
    blip = parse_xml(f'<a:blipFill xmlns:a="{A_NS}" xmlns:r="{R_NS}"><a:blip r:embed="{rel_id}"/>'
                     f'<a:stretch><a:fillRect/></a:stretch></a:blipFill>')
    properties.replace(fill, blip)
    return True


def _fill_grid(table, entries, student, image_width_cm=6.5):
    """證照圖片與競賽共用：兩格一組（圖片列＋名稱列）。格數不夠整組複製、多的整組拿掉；
    有名稱時把學校印的「證照名稱」字樣換成名稱本身（和學校 PDF 一樣只寫名稱）；單數時最後空的那格不留字樣。"""
    cells = resume._unique_cells
    kept = len(entries)
    while len(table.rows) // 2 * 2 < kept:
        last_two = [table.rows[-2]._tr, table.rows[-1]._tr]
        copies = [deepcopy(row) for row in last_two]
        table.rows[-1]._tr.addnext(copies[0])
        copies[0].addnext(copies[1])
    while kept and len(table.rows) // 2 > (kept + 1) // 2:
        for row in (table.rows[-1], table.rows[-2]):
            table._tbl.remove(row._tr)
    slots = []
    rows = table.rows
    for index in range(0, len(rows) - 1, 2):
        for column in range(len(cells(rows[index]))):
            slots.append((cells(rows[index])[column], cells(rows[index + 1])[column]))
    if kept and kept % 2 == 1 and slots:
        for cell in slots[-1]:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.text = ""
    for (image_cell, name_cell), entry in zip(slots, entries):
        if entry["image"]:
            for paragraph in image_cell.paragraphs:
                for run in paragraph.runs:
                    run.text = ""
            _picture(image_cell, student, entry["image"], image_width_cm)
        if entry["text"]:
            _set_text(name_cell.paragraphs[0], entry["text"])
            name_cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            name_cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER


def _page_break(document):
    paragraph = document.add_paragraph()
    paragraph.add_run().add_break(WD_BREAK.PAGE)
    return paragraph._p


def _place_absence_screenshot(document, student, ref):
    """缺曠記錄：學校空白檔在「查詢區間」下面放了一張別人的範例截圖。學生貼了自己的就換掉它（放在同一個位置、同樣寬度）；
    沒貼就把範例拿掉，免得履歷上出現不是自己的缺曠資料。"""
    caption = next((i for i, p in enumerate(document.paragraphs) if "查詢區間" in p.text), None)
    sample = None
    if caption is not None:
        sample = next((p for p in document.paragraphs[caption:] if p._p.xpath(".//wp:inline")), None)
    path = autobiography_images.image_path(student.id, ref) if ref else None
    if sample is None:
        if path:
            sample = document.add_paragraph()
        else:
            return
    for run in list(sample.runs):
        if run._r.xpath(".//w:drawing"):
            run._r.getparent().remove(run._r)
    if path:
        sample.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sample.add_run().add_picture(str(path), width=Cm(16.5))


def _finish_layout(document):
    """拿掉最後面多餘的空段落（含只有換頁的），再補一個極小的段落收尾：Word 規定表格後面要有段落，
    太大會把空白擠成多出來的一頁。"""
    from docx.oxml import parse_xml
    body = document.element.body
    children = [c for c in body if not c.tag.endswith("}sectPr")]
    while children:
        last = children[-1]
        has_drawing = any(el.tag.endswith(("}drawing", "}pict", "}AlternateContent")) for el in last.iter())
        if last.tag.endswith("}p") and not "".join(last.itertext()).strip() and not has_drawing:
            body.remove(last)
            children.pop()
            continue
        break
    tiny = parse_xml('<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:pPr>'
                     '<w:spacing w:before="0" w:after="0" w:line="20" w:lineRule="exact"/>'
                     '<w:rPr><w:sz w:val="2"/></w:rPr></w:pPr></w:p>')
    body.sectPr.addprevious(tiny)


def _fit_picture(cell, student, ref, max_width_cm, max_height_cm):
    """整頁圖（成績單）：照原比例縮到放得進指定的寬高，不超出 A4。"""
    size = autobiography_images.size_of(student.id, ref) if ref else None
    if not size:
        return False
    width_cm = min(max_width_cm, max_height_cm * size[0] / size[1])
    return _picture(cell, student, ref, round(width_cm, 2))


def build_docx(student, options, choices, draft):
    """先用既有的填字（核心科目、證照欄、自傳），再補學生自己填的欄位與圖片。"""
    include = draft.get("include") or {}
    if draft.get("email"):
        options = {**options, "email": draft["email"]}   # 學生在履歷頁自己填、改的信箱
    if draft.get("certcells"):
        options = {**options, "cert_rows": len(draft["certcells"].get("labor") or []) or CERT_ROWS}
    if draft.get("certcells"):  # 學生自己在「相關證照」格子打的字（或拖進去的）才算數，不再看勾選的卡片
        choices = {**choices, "credentials": [{"id": None, "name": name, "column": column}
                                              for column in CERT_COLUMNS for name in draft["certcells"].get(column, []) if name]}
    # 學生在「證照圖片」格子自己放了名稱或圖片才取代預設的名稱欄；沒放就沿用舊做法（依勾選的證照填名稱）
    if any(entry["name"] or entry["image"] for entry in draft["certimg"]):
        options = {**options, "skip_cert_slots": True}
    document = Document(resume.build_docx(options, choices))
    sheet = document.tables[0]
    cells = resume._unique_cells
    transcript_table = document.tables[2]._tbl
    cert_table_element = document.tables[3]._tbl
    cert_heading = next((p._p for p in document.paragraphs if p.text.strip() == "證照"), None)
    absence_paragraph = resume._find_paragraph(document.paragraphs, "缺曠記錄")
    absence_anchor = absence_paragraph._p if absence_paragraph is not None else None

    period = resume._find_paragraph(document.paragraphs, "實習期間")
    if period is not None and draft["period"]:
        _set_text(period, f"實習期間：{draft['period']}")
    first = cells(sheet.rows[0])
    year, month, day = draft["birth"]
    if any((year, month, day)):
        _set_text(first[2].paragraphs[0], f"出生日期： {year or '　'} 年 {month or '　'} 月 {day or '　'} 日")
    if draft["gender"]:
        _set_text(first[3].paragraphs[0], "性別：" + _mark(["男", "女"], draft["gender"]))
    contact = cells(sheet.rows[1])
    _hide_borders(contact[0], "right", "bottom")
    if len(contact) > 1:
        _hide_borders(contact[1], "left", "bottom")
    _hide_borders(cells(sheet.rows[2])[0], "top")
    if draft["phone"]:
        phone = resume._find_paragraph(contact[0].paragraphs, "連絡電話")
        if phone is not None:
            resume._append(phone, draft["phone"])
    if draft["photo"] and len(contact) > 1:
        if not _fill_photo_box(document, contact[1], student, draft["photo"]):
            _picture(contact[1], student, draft["photo"], 3.2)
    address = address_text(draft)
    if address:
        _set_text(cells(sheet.rows[2])[0].paragraphs[0], f"地址： {address}")
    for row in sheet.rows:
        row_cells = cells(row)
        if not row_cells:
            continue
        label = row_cells[0].text.strip()
        if label == "操行平均成績" and draft["conduct"] and len(row_cells) > 1:
            _set_text(row_cells[1].paragraphs[0], _mark(CONDUCT, draft["conduct"]))
        if label == "語文能力" and any(draft["langs"].values()):
            for cell in row_cells[1:]:
                for paragraph in cell.paragraphs:
                    for key, name in LANGUAGES:
                        if paragraph.text.strip().startswith(name):
                            level = draft["langs"][key]
                            _set_text(paragraph, f"{name} " + (_mark(LEVELS, level) if level else "□精通　□中等　□略懂"))

    if draft["transcript"]:
        cell = cells(document.tables[2].rows[0])[0]
        for ref in draft["transcript"]:
            _fit_picture(cell, student, ref, 17.0, 23.0)

    kept = len(draft["certimg"])                    # 學生留下幾格（一格一格拿掉的不算）
    if kept == 0:
        include = {**include, "cert": False}        # 一格都沒留＝整張證照圖片表不放
    cert_table = document.tables[3]
    pristine = Document(str(resume.TEMPLATE))        # 競賽頁照學校證照頁的樣子做：從沒動過的格式檔複製表格與標題
    contest_pattern = deepcopy(pristine.tables[3]._tbl)
    heading_source = next((p._p for p in pristine.paragraphs if p.text.strip() == "證照"), None)
    heading_pattern = deepcopy(heading_source) if heading_source is not None else None
    _fill_grid(cert_table, [{"image": c["image"], "text": c["name"]} for c in draft["certimg"]], student)

    if draft["absence"]["range"]:
        for paragraph in document.paragraphs:
            if "查詢區間" in paragraph.text:
                _set_text(paragraph, f"（查詢區間：{draft['absence']['range']}）")
    table = document.tables[4]
    for index, value in enumerate(draft["absence"]["rows"]):
        if value and index + 1 < len(table.rows):
            row_cells = cells(table.rows[index + 1])
            if len(row_cells) > 1:
                row_cells[1].paragraphs[0].add_run(value if value.endswith("節") else value + "節")
    _place_absence_screenshot(document, student, draft["absence"]["image"])

    entries = [{"image": c["image"], "text": c["caption"]} for c in draft["contest"] if c["image"] or c["caption"]] \
        if include.get("contest", True) else []
    if entries and heading_pattern is not None:
        from docx.table import Table
        from docx.text.paragraph import Paragraph
        contest_table = Table(contest_pattern, document._body)
        _fill_grid(contest_table, entries, student)
        contest_heading = Paragraph(heading_pattern, document._body)
        _set_text(contest_heading, "競賽")
        anchor = absence_anchor
        before = [_page_break(document), contest_heading._p, contest_table._tbl, _page_break(document)]
        for element in before:
            if anchor is not None:
                anchor.addprevious(element)
            else:
                document.element.body.sectPr.addprevious(element)
    _remove_unwanted_pages(document, include, transcript_table, cert_table_element, cert_heading, absence_anchor)
    _finish_layout(document)
    stream = BytesIO()
    document.save(stream)
    stream.seek(0)
    return stream

"""產出完整備審資料（Word，正式排版）。

版面參考學長姐的備審與學校的實習履歷格式（只參考版面，不引用內容）：
封面 → 目錄（章節名稱＋頁碼，頁碼是 PAGEREF 欄位，Word 開檔時更新）→ 依目標校系加權排序的章節（佔分高的在前）。
證照章節開頭有「課程與證照對照」表；各章節附已確認的資料與佐證圖片（兩欄圖片格）。
內容只用學生已確認的資料；導師還沒確認時，封面、每頁頁首與每章開頭都會註明。
"""

from datetime import date
from io import BytesIO

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from app.models import (CourseRule, CredentialRecord, CurriculumCourse, CurriculumVersion, LearningCourseRecord,
                        PackageReview, Portfolio)
from app.services import package_exclusion, storage_service
from app.services.autobiography_service import CONFIRMED_PORTFOLIO_STATUSES, latest_draft
from app.services.file_preview import preview_kind
from app.services.gap_service import analyze_gap, chapter_order

REVIEW_TEXT = {
    "confirmed": "導師已確認",
    "pending": "等待導師確認中",
    "needs_revision": "導師建議修改後再送出",
}
UNCONFIRMED_NOTE = "本文件尚未經導師確認，內容僅供學生自行檢查，送出前請先請導師確認。"
UNCONFIRMED_HEADER = "【尚未經導師確認】"

BODY_FONT = "標楷體"  # 學校公文與學長姐範例都用標楷體
LATIN_FONT = "Times New Roman"

# 課程名稱關鍵字 → （學到的能力, 可對應的證照與成果關鍵字）。
# 只是通用的資管科課程常識；有管理員確認的修業科目表時，再加上表上「備註」寫的對應證照，
# 管理員在課程規則填的「能力領域」優先於這裡的說明。
COURSE_SKILLS = [
    ("計算機概論", "電腦基本操作、文書與試算表處理", ["電腦軟體應用", "文書處理", "MOS", "數位素養"]),
    ("程式設計", "程式邏輯與問題解決", ["程式", "APCS", "Python", "C++", "Java", "軟體設計"]),
    ("網頁", "網頁版面設計與前端程式", ["網頁設計", "網頁"]),
    ("資料庫", "資料庫設計與 SQL 查詢", ["資料庫", "SQL"]),
    ("網路", "網路架設與管理", ["網路架設"]),
    ("硬體", "電腦硬體組裝與維修", ["硬體裝修"]),
    ("管理資訊系統", "資訊系統規劃與企業應用", ["ERP", "資訊管理"]),
    ("系統分析", "需求訪談與系統設計", ["系統分析"]),
    ("會計", "會計帳務處理", ["會計"]),
    ("多媒體", "影像與多媒體編輯", ["多媒體", "影像處理"]),
    ("英文", "英語溝通", ["英檢", "多益", "TOEIC"]),
]


def latest_review(student, program):
    return (PackageReview.query.filter_by(student_id=student.id, rule_version_id=program.id)
            .order_by(PackageReview.requested_at.desc(), PackageReview.id.desc()).first())


def _semester_text(year, semester):
    parts = []
    if year:
        parts.append(f"專{'一二三四五'[year - 1]}" if 1 <= year <= 5 else f"{year} 學年度")
    if semester:
        parts.append({1: "上學期", 2: "下學期"}.get(semester, str(semester)))
    return " ".join(parts)


# ---------- 版面工具 ----------

def _font(run, size=None, bold=None, color=None):
    run.font.name = LATIN_FONT
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), BODY_FONT)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color:
        run.font.color.rgb = color
    return run


RED = RGBColor(0xB0, 0x2A, 0x2A)


def _setup_styles(document):
    for name in ("Normal", "Title", "Heading 1", "Heading 2", "List Bullet"):
        style = document.styles[name]
        style.font.name = LATIN_FONT
        fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
        for theme_attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
            fonts.attrib.pop(qn(theme_attr), None)
        fonts.set(qn("w:eastAsia"), BODY_FONT)
        if name != "Normal":
            style.font.color.rgb = RGBColor(0, 0, 0)
    normal = document.styles["Normal"]
    normal.font.size = Pt(12)
    normal.paragraph_format.line_spacing = 1.25
    document.styles["Heading 1"].font.size = Pt(18)
    document.styles["Heading 2"].font.size = Pt(14)


def _add_field(paragraph, instruction, placeholder="", size=None):
    """插入 Word 欄位（PAGE、PAGEREF）。文件設定了開檔更新欄位，Word 會換成實際頁碼。"""
    def char(kind):
        element = OxmlElement("w:fldChar")
        element.set(qn("w:fldCharType"), kind)
        if kind == "begin":
            element.set(qn("w:dirty"), "true")
        paragraph.add_run()._r.append(element)

    char("begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {instruction} "
    paragraph.add_run()._r.append(instr)
    char("separate")
    _font(paragraph.add_run(placeholder or " "), size=size)
    char("end")


def _update_fields_on_open(document):
    element = OxmlElement("w:updateFields")
    element.set(qn("w:val"), "true")
    document.settings.element.append(element)


def _bookmark(paragraph, name, bookmark_id):
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(bookmark_id))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(bookmark_id))
    paragraph._p.insert(1 if paragraph._p.pPr is not None else 0, start)
    paragraph._p.append(end)


def _centered(document, text, size, bold=False, space_after=6, color=None):
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_after = Pt(space_after)
    _font(paragraph.add_run(text), size=size, bold=bold, color=color)
    return paragraph


def _note(document, text):
    """醒目的提醒文字（未確認、缺資料）。"""
    paragraph = document.add_paragraph()
    _font(paragraph.add_run(text), size=11, bold=True, color=RED)
    return paragraph


def _page_break(document):
    document.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def _table(document, headers, rows, widths=None):
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for cell, text in zip(table.rows[0].cells, headers):
        _font(cell.paragraphs[0].add_run(text), size=11, bold=True)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        shading = OxmlElement("w:shd")
        shading.set(qn("w:val"), "clear")
        shading.set(qn("w:fill"), "E7E6E6")
        cell._tc.get_or_add_tcPr().append(shading)
    for values in rows:
        for cell, text in zip(table.add_row().cells, values):
            _font(cell.paragraphs[0].add_run(str(text)), size=11)
    if widths:
        for row in table.rows:
            for cell, width in zip(row.cells, widths):
                cell.width = Cm(width)
    document.add_paragraph()
    return table


def _image_grid(document, images):
    """兩欄圖片格，每格下方寫名稱（學校履歷格式的證照／競賽頁）。images：[(路徑, 說明)]，路徑是 None 的略過。"""
    images = [(path, caption) for path, caption in images if path]
    if not images:
        return
    table = document.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for start in range(0, len(images), 2):
        cells = table.add_row().cells
        for cell, (path, caption) in zip(cells, images[start:start + 2]):
            picture = cell.paragraphs[0]
            picture.alignment = WD_ALIGN_PARAGRAPH.CENTER
            try:
                picture.add_run().add_picture(str(path), width=Cm(7.2))
            except Exception:  # 圖檔壞掉或格式不支援：留文字，不讓整份文件失敗
                _font(picture.add_run("（佐證圖片無法放入，請另附）"), size=10)
            label = cell.add_paragraph()
            label.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _font(label.add_run(caption), size=10)
    document.add_paragraph()


def _image_path(file_path, display_name):
    if not file_path or preview_kind(display_name) != "image":
        return None
    return storage_service.local_path_or_none(file_path)


# ---------- 資料（都只取已確認的） ----------

def _confirmed_courses(student, required=None):
    """required 有給（required_keys(program)）就拿掉學生選擇不放的；簡章必備的類別除外。"""
    courses = LearningCourseRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed").order_by(
        LearningCourseRecord.school_year, LearningCourseRecord.semester, LearningCourseRecord.id).all()
    return courses if required is None else package_exclusion.keep_courses(courses, required)


def _confirmed_credentials(student, required=None):
    credentials = CredentialRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed").order_by(
        CredentialRecord.issue_date, CredentialRecord.id).all()
    return credentials if required is None else package_exclusion.keep_credentials(credentials, required)


def _confirmed_records(student, categories=None, required=None):
    query = Portfolio.active().filter(Portfolio.student_id == student.id,
                                      Portfolio.status.in_(CONFIRMED_PORTFOLIO_STATUSES))
    if categories is not None:
        query = query.filter(Portfolio.category.in_(categories))
    records = query.order_by(Portfolio.school_year, Portfolio.semester, Portfolio.id).all()
    return records if required is None else package_exclusion.keep_portfolios(records, required)


def _unconfirmed_count(student, categories):
    return Portfolio.active().filter(Portfolio.student_id == student.id, Portfolio.category.in_(categories),
                                     ~Portfolio.status.in_(CONFIRMED_PORTFOLIO_STATUSES)).count()


def _curriculum_notes(student):
    """管理員確認過的修業科目表：科目名 → 備註（常寫對應證照，例如「會計丙級」）。"""
    profile = student.student_profile
    if not profile or not profile.admission_year:
        return {}
    version = CurriculumVersion.query.filter_by(admission_year=profile.admission_year, status="published").first()
    if not version:
        return {}
    return {"".join(course.name.split()): course.note
            for course in CurriculumCourse.query.filter_by(version_id=version.id) if course.note}


def course_credential_rows(student, required=None):
    """課程與證照對照：哪些課程學到的能力，對應到哪些證照與成果。只列有對應的課程。"""
    notes = _curriculum_notes(student)
    abilities = {rule.normalized_course_name: rule.ability_domain for rule in
                 CourseRule.query.filter(CourseRule.ability_domain.isnot(None), CourseRule.is_active.is_(True))}
    credentials = _confirmed_credentials(student, required)
    records = _confirmed_records(student, required=required)
    rows = []
    for course in _confirmed_courses(student, required):
        key = course.normalized_course_name
        skill, keywords = next(((ability, list(words)) for word, ability, words in COURSE_SKILLS
                                if word in course.course_name), (None, []))
        if notes.get(key):
            keywords += [part for part in notes[key].replace("、", " ").split() if len(part) >= 2]
        skill = abilities.get(key) or skill
        matched_credentials = [c.credential_name for c in credentials if any(word in c.credential_name for word in keywords)]
        matched_records = [r.title for r in records
                           if (r.course_name and "".join(r.course_name.split()) == key)
                           or any(word in f"{r.title}{r.description or ''}" for word in keywords)]
        if not (matched_credentials or matched_records):
            continue
        score = course.score if course.score is not None else course.status_mark
        rows.append({
            "course": course.course_name,
            "detail": "、".join(part for part in (
                _semester_text(course.school_year, None),
                f"{course.credits} 學分" if course.credits else "",
                f"{score} 分" if isinstance(score, int) else (score or "")) if part),
            "skill": skill or "（請補充）",
            "credentials": "、".join(dict.fromkeys(matched_credentials)) or "—",
            "records": "、".join(dict.fromkeys(matched_records)) or "—",
        })
    return rows


# ---------- 章節內容 ----------

def _records_body(document, student, codes, required=None):
    records = _confirmed_records(student, codes, required)
    images = []
    for record in records:
        when = _semester_text(record.school_year, record.semester)
        title = document.add_paragraph(style="List Bullet")
        _font(title.add_run(record.title), bold=True)
        if when:
            _font(title.add_run(f"（{when}）"))
        for label, value in (("說明", record.description), ("我負責的部分", record.role),
                             ("成果", record.achievement), ("學到什麼", record.learned)):
            if value:
                paragraph = document.add_paragraph()
                paragraph.paragraph_format.left_indent = Cm(0.8)
                _font(paragraph.add_run(f"{label}："), bold=True)
                _font(paragraph.add_run(value))
        for link in record.evidence_items:
            if link.external_url and link.is_available:
                paragraph = document.add_paragraph()
                paragraph.paragraph_format.left_indent = Cm(0.8)
                _font(paragraph.add_run("作品連結："), bold=True)
                _font(paragraph.add_run(f"{link.display_name}　{link.external_url}"
                                        if link.display_name != link.external_url else link.external_url))
        images +=[(_image_path(e.file_path, e.display_name), record.title) for e in record.evidence_items]
    if not records:
        document.add_paragraph("（尚未提供已確認的資料）")
    _image_grid(document, images)
    pending = _unconfirmed_count(student, codes)
    if pending:
        _note(document, f"另有 {pending} 筆資料尚未確認，未放入本文件。")


def _credential_body(document, student, required=None):
    document.add_heading("課程與證照對照", level=2)
    rows = course_credential_rows(student, required)
    if rows:
        _table(document, ["課程", "修課資訊", "學到的能力", "對應證照", "相關成果"],
               [(r["course"], r["detail"], r["skill"], r["credentials"], r["records"]) for r in rows],
               widths=[3, 3.2, 3.6, 3.2, 3.6])
    else:
        document.add_paragraph("（目前沒有能對應到證照或成果的已確認課程）")
    document.add_heading("證照清單", level=2)
    credentials = _confirmed_credentials(student, required)
    if credentials:
        _table(document, ["證照名稱", "級別", "發證單位", "取得日期"],
               [(c.credential_name, c.level or "", c.issuing_organization or "",
                 c.issue_date.isoformat() if c.issue_date else "") for c in credentials],
               widths=[6, 2.2, 4, 3])
        _image_grid(document, [(_image_path(c.source_document.file_path, c.source_document.display_name),
                                c.credential_name) for c in credentials if c.source_document])
    else:
        document.add_paragraph("（尚未提供證照資料）")
    pending = CredentialRecord.query.filter(CredentialRecord.student_id == student.id,
                                            CredentialRecord.confirmation_status != "confirmed").count()
    if pending:
        _note(document, f"另有 {pending} 張證照尚未確認，未放入本文件。")


PLAN_WORDS = ("未來", "規劃", "讀書計畫", "入學後")


def _draft_parts(student, program):
    """自傳草稿的段落分成（自傳, 讀書計畫）：標題含「未來、規劃」的算讀書計畫（老師版型 04 自傳、05 讀書計畫分開）。"""
    draft = latest_draft(student, program)
    paragraphs = (draft.content_json.get("paragraphs", []) if draft else [])
    heading = lambda p: (p.get("title") or p.get("heading") or "").strip()  # noqa: E731
    plan = [p for p in paragraphs if p.get("text") and any(w in heading(p) for w in PLAN_WORDS)]
    bio = [p for p in paragraphs if p.get("text") and p not in plan]
    return bio, plan, heading


def chapter_evidence(student, chapter, program):
    """這一章要列在目錄底下的具體佐證名稱（老師：每章列具體佐證，例如「證照：電腦軟體應用丙級」）。"""
    required = package_exclusion.required_keys(program)
    codes, code = chapter["keys"], chapter["code"]
    if code == "04":
        bio, _plan, heading = _draft_parts(student, program)
        return [heading(p) for p in bio if heading(p)]
    if code == "05":
        _bio, plan, heading = _draft_parts(student, program)
        return [heading(p) for p in plan if heading(p)]
    if "credential" in codes:
        return [c.credential_name + (f"（{c.level}）" if c.level else "") for c in _confirmed_credentials(student, required)]
    if code in ("06", "07", "08", "09", "10"):
        return [r.title for r in _confirmed_records(student, codes, required)]
    return []


def _chapter_body(document, student, chapter, program):
    codes = chapter["keys"]
    required = package_exclusion.required_keys(program)  # 學生選擇不放的資料不印；簡章必備的類別除外
    if chapter["code"] == "02":
        document.add_paragraph("請附上報名資格證明（依當年度簡章規定）。")
        return
    if "grades" in codes:
        courses = _confirmed_courses(student, required)
        if not courses:
            document.add_paragraph("（尚未提供成績資料）")
            return
        _table(document, ["年級", "學期", "課程", "學分", "成績"],
               [(_semester_text(c.school_year, None) or c.grade_level or "", c.semester or "", c.course_name,
                 "" if c.credits is None else c.credits,
                 c.score if c.score is not None else (c.status_mark or "")) for c in courses],
               widths=[2.2, 1.8, 7, 1.8, 2])
        scored = [c.score for c in courses if c.score is not None]
        if scored:
            document.add_paragraph(f"已確認課程 {len(courses)} 門，平均 {sum(scored) / len(scored):.1f} 分。")
        document.add_paragraph("另附學校核發之歷年成績單正本。")
        return
    if "credential" in codes:
        _credential_body(document, student, required)
        return
    if chapter["code"] == "04":
        # 自傳：有學生儲存過的「自傳小幫手」版本就放進來（標題用段落標題），沒有就留撰寫提示
        bio, _plan, heading = _draft_parts(student, program)
        if bio:
            for paragraph in bio:
                if heading(paragraph):
                    document.add_heading(heading(paragraph), level=2)
                document.add_paragraph(paragraph["text"]).paragraph_format.first_line_indent = Pt(24)
            return
        document.add_paragraph("請在此撰寫。可用系統的「小助手寫自傳」產生草稿，或參考「我的五年」中的活動、證照與競賽整理自己的經歷。")
        return
    if "autobiography" in codes:
        _bio, plan, heading = _draft_parts(student, program)
        if plan:
            for paragraph in plan:
                if heading(paragraph):
                    document.add_heading(heading(paragraph), level=2)
                document.add_paragraph(paragraph["text"]).paragraph_format.first_line_indent = Pt(24)
            return
        document.add_paragraph("請在此撰寫讀書計畫：進二技後的學習目標、想修的課程與畢業後規劃。")
        return
    if "project" in codes and not _confirmed_records(student, codes, required):
        document.add_paragraph("請附上專題或作品集，說明個人負責的部分與成果。")
        return
    _records_body(document, student, codes, required)


# ---------- 封面、目錄、頁首頁尾 ----------

def _cover(document, student, program, review, confirmed):
    profile = student.student_profile
    for _ in range(3):
        document.add_paragraph()
    _centered(document, f"{program.admission_year} 學年度", 16)
    _centered(document, program.school_name, 26, bold=True)
    _centered(document, program.department_name, 22, bold=True)
    _centered(document, "備 審 資 料", 30, bold=True, space_after=48)
    table = document.add_table(rows=0, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for column, width in zip(table.columns, (Cm(3.8), Cm(11))):
        column.width = width
    for label, value in (
        ("申請校系", f"{program.school_name} {program.department_name}"),
        ("志願代碼", program.program_code or ""),
        ("學生姓名", student.display_name or ""),
        ("學　　號", profile.student_no if profile else ""),
        ("班　　級", (profile.class_name or "") if profile else ""),
        ("日　　期", date.today().strftime("%Y 年 %m 月 %d 日")),
    ):
        cells = table.add_row().cells
        cells[0].width, cells[1].width = Cm(3.8), Cm(11)
        cells[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _font(cells[0].paragraphs[0].add_run(f"{label}："), size=16, bold=True)
        _font(cells[1].paragraphs[0].add_run(value), size=16)
    document.add_paragraph()
    status = REVIEW_TEXT.get(review.status, "尚未送導師確認") if review else "尚未送導師確認"
    _centered(document, f"導師確認：{status}", 12)
    if not confirmed:
        _centered(document, UNCONFIRMED_NOTE, 11, bold=True, color=RED)


def _toc(document, chapters, evidence=None, optional=()):
    """目錄：章節依校系加權排序；每章底下列具體佐證（沒有佐證的章不列）；簡章沒有要求的章標「（選放）」。"""
    evidence = evidence or {}
    _centered(document, "目　錄", 20, bold=True, space_after=18)
    for position, chapter in enumerate(chapters, start=1):
        line = document.add_paragraph()
        line.paragraph_format.tab_stops.add_tab_stop(Cm(16.4), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
        line.paragraph_format.space_after = Pt(4)
        suffix = "（選放）" if chapter["code"] in optional else ""
        _font(line.add_run(f"{position:02d}　{chapter['title']}{suffix}"), size=14)
        line.add_run(chr(9))
        _add_field(line, f"PAGEREF _Toc_ch{position:02d} \\h", "#", size=14)
        for index, name in enumerate(evidence.get(chapter["code"], [])[:12], start=1):
            sub = document.add_paragraph()
            sub.paragraph_format.left_indent = Cm(1.2)
            sub.paragraph_format.space_after = Pt(1)
            _font(sub.add_run(f"{position}.{index}　{name}"), size=11)
        document.paragraphs[-1].paragraph_format.space_after = Pt(8)
    weights = "、".join(f"{c['title']} {c['weight']}%" for c in chapters if c["weight"])
    if weights:
        document.add_paragraph()
        _font(document.add_paragraph().add_run(f"章節依本校系備審項目加權排序，佔分高的在前（{weights}）。"), size=10)


def _header_footer(section, confirmed):
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_field(footer, "PAGE", "1", size=10)
    if not confirmed:
        header = section.header.paragraphs[0]
        header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _font(header.add_run(UNCONFIRMED_HEADER), size=10, bold=True, color=RED)


def build_package_docx(student, program):
    review = latest_review(student, program)
    confirmed = bool(review and review.status == "confirmed")
    gap = analyze_gap(student, program)
    # 01 封面與目錄就是下面的封面頁與目錄頁；其餘章節依校系加權排序
    chapters = [chapter for chapter in chapter_order(program) if chapter["code"] != "01"]

    document = Document()
    _setup_styles(document)
    _update_fields_on_open(document)
    section = document.sections[0]
    section.page_height, section.page_width = Cm(29.7), Cm(21)
    section.left_margin = section.right_margin = Cm(2.2)
    section.top_margin = section.bottom_margin = Cm(2.2)
    section.different_first_page_header_footer = True  # 封面不印頁碼與頁首
    _header_footer(section, confirmed)

    _cover(document, student, program, review, confirmed)
    _page_break(document)
    evidence = {chapter["code"]: chapter_evidence(student, chapter, program) for chapter in chapters}
    optional = {chapter["code"] for chapter in chapters
                if program.items and not chapter["weight"] and chapter["code"] not in ("02", "03", "10")}  # 10 其他有利資料老師說不可空白，不標選放
    _toc(document, chapters, evidence, optional)

    requirements = [item for item in program.items if item.requirement]
    if requirements or program.highlights:
        document.add_heading("簡章要求", level=2)
        if gap["readiness"] is not None:
            document.add_paragraph(f"資料準備度：{gap['readiness']}%（依校系加權計算，僅供參考）")
        for item in requirements:
            document.add_paragraph(f"{item.source_item_name}（{item.weight_percent}%）：{item.requirement}", style="List Bullet")
        if program.highlights:
            document.add_heading("重點提醒", level=2)
        for highlight in program.highlights or []:
            page = f"（{highlight['page']}）" if highlight.get("page") else ""
            document.add_paragraph(f"{highlight['text']}{page}", style="List Bullet")
        if program.source_note:
            document.add_paragraph(f"來源：{program.source_note}" + (f"　{program.source_url}" if program.source_url else ""))

    for position, chapter in enumerate(chapters, start=1):
        _page_break(document)
        # 印出來的章節編號依實際順序 01、02、03…，不保留原始編號
        suffix = "（選放）" if chapter["code"] in optional else ""  # 和目錄上的標示一致
        heading = document.add_heading(f"{position:02d}　{chapter['title']}{suffix}", level=1)
        _bookmark(heading, f"_Toc_ch{position:02d}", position)
        if not confirmed:
            _note(document, "（本章內容尚未經導師確認）")
        _chapter_body(document, student, chapter, program)

    document.add_paragraph("本文件內容皆為學生確認之資料；正式規定以當年度招生簡章與各校系分則為準。")
    stream = BytesIO()
    document.save(stream)
    stream.seek(0)
    return stream

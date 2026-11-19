"""專四上學期的實習履歷：把學生已確認的資料填進學校規定的格式檔。

格式檔：app/content/internship_resume_template.docx，是資管科發的「02_學生實習履歷.docx」原檔
（來源 D:\\democase\\實習表格_康寧資管科\\），這裡只往空格裡填字，不改版面。

- 系統有的才填：學號、姓名、電子信箱、相關證照（四欄）、自傳、證照名稱。
- 已修習專業核心科目：照資管科「實習申請表填寫說明」第 2 點（https://im.ukn.edu.tw/p/405-1028-2626,c1193.php）——
  及格的填該科學分、不及格的把科目直接刪除、上下學期只有一學期及格的視同不及格。系統依學生已確認的成績判斷；
  系統裡沒有成績的科目，學分留白、在頁面上列出來請學生自己核對（不替學生假設及格）。
- 系統沒有的留空給學生手填：出生日期、性別、電話、地址、操行、語文能力、成績單、證照圖片、缺曠記錄。
  缺曠只存合計、只給本人與班導看（AGENTS.md 第 8 節），不自動寫進會交到校外的履歷。
- 自傳四段是學校格式上列的四項；學生選的經歷只是一行一行列在對應的段落下面，
  不呼叫 AI，學生在頁面上看過、改過、按下載才算數。
"""

from io import BytesIO
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ROW_HEIGHT_RULE

from app.extensions import db
from app.models import CredentialRecord, LearningCourseRecord, LearningProfileOutput, Portfolio
from app.services.eligibility_service import normalize_course_name
from app.services.journey_service import EXPERIENCE_CATEGORIES, GRADE_LABELS

TEMPLATE = Path(__file__).resolve().parent.parent / "content" / "internship_resume_template.docx"
OPEN_FROM_GRADE = 4
OUTPUT_TYPE = "internship_resume"

# 學校格式「相關證照」的四欄
COLUMNS = [("labor", "勞動部"), ("international", "國際證照"), ("domestic", "國內證照"), ("other", "其他證照")]
COLUMN_KEYS = [key for key, _ in COLUMNS]
CERT_ROWS = 6      # 格式檔每欄 6 列
CERT_PHOTOS = 8    # 格式檔後面的證照圖片與名稱 8 格

# 學校格式「自傳」頁列的四項（照原檔文字）
SECTIONS = [
    ("family", "家庭生活"),
    ("study", "求學經過、社團活動"),
    ("skill", "個人專長、簡要經歷"),
    ("future", "未來生涯規劃"),
]
# 哪一類資料列在哪一段下面
SECTION_OF = {"activity": "study", "service": "study", "leadership": "study", "competition": "skill", "credential": "skill"}
KIND_LABELS = {"activity": "活動", "service": "服務學習", "leadership": "幹部", "competition": "競賽", "credential": "證照"}
TEXT_LIMIT = 3000  # 每段自傳最多幾個字（避免貼進整本書）

_LABOR = ("勞動部", "技術士", "丙級", "乙級", "甲級", "勞動力發展署")
_INTERNATIONAL = ("國際", "ITS", "MOS", "TOEIC", "TOEFL", "IELTS", "Microsoft", "Adobe", "ACP", "ACA", "Oracle",
                  "Cisco", "CCNA", "CompTIA", "IC3", "AWS", "Google", "JLPT", "PMP", "Autodesk", "Certiport")
_DOMESTIC = ("TQC", "電腦技能基金會", "全民英檢", "GEPT", "ITE", "經濟部", "iPAS", "MOCC", "中華民國", "金融研訓院", "APCS")


CORE_ROWS = range(5, 15)        # 格式檔表一第 6～15 列是核心科目（每列三組「科目名稱｜學分」）
PASS_MARKS = ("抵免", "免修", "通過")


def template_courses():
    """格式檔上印好的核心科目：[(列, 組, 科目名稱, 學分字樣)]。學分有斜線（3/3）的是上下學期各一次。"""
    document = Document(str(TEMPLATE))
    out = []
    for row_index in CORE_ROWS:
        cells = _unique_cells(document.tables[0].rows[row_index])
        for pair in range(3):
            if 2 * pair + 1 < len(cells):
                name, credit = cells[2 * pair].text.strip(), cells[2 * pair + 1].text.strip()
                if name:
                    out.append((row_index, pair, name, credit))
    return out


def core_course_status(student):
    """每門核心科目：pass（及格，填學分）、fail（不及格，整科刪掉）、unknown（系統沒有成績，學分留白請學生核對）。"""
    records = {}
    for record in LearningCourseRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed").all():
        records.setdefault(normalize_course_name(record.normalized_course_name or record.course_name), []).append(record)
    result = []
    for row_index, pair, name, credit in template_courses():
        needed = 2 if "/" in credit else 1
        found = records.get(normalize_course_name(name), [])
        passed = sum(1 for r in found if (r.score is not None and r.score >= 60) or (r.status_mark or "") in PASS_MARKS)
        failed = any(r.score is not None and r.score < 60 for r in found)
        status = "pass" if passed >= needed else ("fail" if failed else "unknown")
        result.append({"row": row_index, "pair": pair, "name": name, "credit": credit, "status": status})
    return result


def is_open(grade):
    """專四上學期起才有這個按鈕。"""
    return bool(grade) and grade >= OPEN_FROM_GRADE


def guess_column(credential):
    """猜這張證照該填在哪一欄；只是先幫學生分好，頁面上可以改。"""
    text = " ".join(part for part in (credential.credential_name, credential.level, credential.issuing_organization,
                                      credential.category) if part)
    upper = text.upper()
    if any(word in text for word in _LABOR):
        return "labor"
    if any(word.upper() in upper for word in _INTERNATIONAL):
        return "international"
    if any(word.upper() in upper for word in _DOMESTIC):
        return "domestic"
    return "other"


def credential_label(credential):
    level = credential.level or ""
    return credential.credential_name if not level or level in credential.credential_name else f"{credential.credential_name} {level}"


def latest_autobiography(student):
    """學生在系統裡最新一版自傳（任何校系）；沒有就回傳 None。"""
    from app.services.autobiography_service import OUTPUT_TYPE, version_of
    output = (LearningProfileOutput.query.filter_by(student_id=student.id, output_type=OUTPUT_TYPE)
              .order_by(LearningProfileOutput.id.desc()).first())
    if not output:
        return None
    text = "\n".join(str(p.get("text", "")).strip() for p in output.content_json.get("paragraphs", []) if p.get("text"))
    return {"version": version_of(output), "text": text} if text else None


def build_options(student, journey):
    """實習履歷頁要給學生勾選的東西：證照（含建議的欄位）、經歷、自傳四段的預填文字。"""
    profile = student.student_profile
    credentials = [{
        "id": record.id, "name": credential_label(record), "column": guess_column(record),
    } for record in CredentialRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed").order_by(CredentialRecord.id).all()]

    confirmed_ids = {f"portfolio-{record.id}" for record in Portfolio.active().filter_by(
        student_id=student.id, status="confirmed").all()}
    experiences = []
    for year in journey["years"]:
        for key in EXPERIENCE_CATEGORIES:
            for item in year["categories"].get(key, []):
                if item["id"] not in confirmed_ids:
                    continue
                experiences.append({
                    "id": item["id"], "key": key, "kind": KIND_LABELS[key], "section": SECTION_OF[key],
                    "grade_label": GRADE_LABELS[year["grade"]], "title": item["title"],
                    "line": f"{GRADE_LABELS[year['grade']]}{KIND_LABELS[key]}：{item['title']}",
                })

    bio = latest_autobiography(student)
    sections = [{
        "key": key, "title": title,
        "text": bio["text"] if bio and key == "study" else "",
        "picks": [item for item in experiences if item["section"] == key],
        "credentials": credentials if key == "skill" else [],
    } for key, title in SECTIONS]
    return {
        "courses": core_course_status(student),
        "student_no": profile.student_no if profile else student.username,
        "name": student.display_name,
        "email": student.email or "",
        "credentials": credentials,
        "experiences": experiences,
        "sections": sections,
        "bio": bio,
        "columns": COLUMNS,
        "cert_rows": CERT_ROWS,
    }


def read_choices(form, options):
    """把表單送來的勾選整理成乾淨的選擇；只接受這位學生自己的資料編號。"""
    picked_credentials = set(form.getlist("cred"))
    picked_experiences = set(form.getlist("exp"))
    credentials = []
    for item in options["credentials"]:
        if str(item["id"]) in picked_credentials:
            column = form.get(f"col_{item['id']}", item["column"])
            credentials.append({**item, "column": column if column in COLUMN_KEYS else item["column"]})
    experiences = [item for item in options["experiences"] if item["id"] in picked_experiences]
    texts = {key: (form.get(f"text_{key}") or "").strip()[:TEXT_LIMIT] for key, _ in SECTIONS}
    return {"credentials": credentials, "experiences": experiences, "texts": texts}


def autobiography_blocks(choices):
    """自傳四段：每段是（標題, 學生寫的文字, 選進來的資料一行一筆）。"""
    blocks = []
    for key, title in SECTIONS:
        lines = [item["line"] for item in choices["experiences"] if item["section"] == key]
        if key == "skill":
            lines = [f"證照：{item['name']}" for item in choices["credentials"]] + lines
        blocks.append((title, choices["texts"].get(key, ""), lines))
    return blocks


def latest_saved(student):
    return (LearningProfileOutput.query.filter_by(student_id=student.id, output_type=OUTPUT_TYPE)
            .order_by(LearningProfileOutput.id.desc()).first())


def save_snapshot(student, options, choices):
    contents = {key: options[key] for key in ("name", "student_no", "email", "courses")}
    db.session.add(LearningProfileOutput(student_id=student.id, output_type=OUTPUT_TYPE,
                                         content_json={**contents, "choices": choices}, source_snapshot_json={}))


def _unique_cells(row):
    seen, cells = [], []
    for cell in row.cells:
        if cell._tc not in seen:
            seen.append(cell._tc)
            cells.append(cell)
    return cells


def _append(paragraph, text):
    """在原本的文字後面接著寫，沿用那一段最後一個字的字型。"""
    if not text:
        return
    runs = [run for run in paragraph.runs if run.text]
    if runs:
        runs[-1].text = runs[-1].text + text
    else:
        paragraph.add_run(text)


def _find_paragraph(paragraphs, start):
    return next((p for p in paragraphs if p.text.strip().startswith(start)), None)


def build_docx(options, choices):
    """照學校格式檔填好，回傳 Word 的位元組串流。"""
    document = Document(str(TEMPLATE))

    # 封面
    for label, value in (("學號：", options["student_no"]), ("姓名：", options["name"])):
        paragraph = _find_paragraph(document.paragraphs, label)
        if paragraph is not None:
            _append(paragraph, value)

    # 舊格式的固定實習日期不代表這次實習安排，留白讓學生依公告填寫。
    period = _find_paragraph(document.paragraphs, "實習期間")
    if period is not None:
        for run in period.runs:
            run.text = ""
        period.add_run("實習期間：中華民國　　年　月　日至　月　日")

    for paragraph in document.paragraphs:
        if "查詢區間：" in paragraph.text:
            for run in paragraph.runs:
                run.text = ""
            paragraph.add_run("（查詢區間：　　至　　學期）")

    # 實習生履歷表
    sheet = document.tables[0]
    # 已修習專業核心科目：及格的保留學分、不及格的整科刪掉、系統沒有成績的學分留白（見檔案開頭說明）
    for course in options.get("courses", []):
        if course["status"] == "pass":
            continue
        cells = _unique_cells(sheet.rows[course["row"]])
        if course["status"] == "fail":
            cells[2 * course["pair"]].text = ""
        cells[2 * course["pair"] + 1].text = ""
    first = _unique_cells(sheet.rows[0])
    _append(first[0].paragraphs[0], options["student_no"])
    _append(first[1].paragraphs[0], options["name"])
    contact = _unique_cells(sheet.rows[1])[0]
    email_line = _find_paragraph(contact.paragraphs, "電子信箱")
    if email_line is not None:
        _append(email_line, options["email"])

    header = next((i for i, row in enumerate(sheet.rows) if _unique_cells(row)[0].text.strip() == "勞動部"), None)
    if header is not None:
        for index, (key, _) in enumerate(COLUMNS):
            names = [item["name"] for item in choices["credentials"] if item["column"] == key]
            # 超過 6 張：多的併在最後一格，不新增列（不改學校的版面）
            if len(names) > CERT_ROWS:
                names = names[:CERT_ROWS - 1] + ["、".join(names[CERT_ROWS - 1:])]
            for offset, name in enumerate(names):
                cells = _unique_cells(sheet.rows[header + 1 + offset])
                if index < len(cells):
                    cells[index].paragraphs[0].add_run(name)

    # 自傳
    blocks = autobiography_blocks(choices)
    if any(text or lines for _, text, lines in blocks):
        row = document.tables[1].rows[0]
        row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST  # 字多時讓格子長高，不被切掉
        cell = row.cells[0]
        label = cell.paragraphs[0]
        for run in label.runs:
            run.text = ""
        first_block = True
        for title, text, lines in blocks:
            if not (text or lines):
                continue
            target = label if first_block else cell.add_paragraph()
            first_block = False
            target.alignment = None
            target.add_run(f"【{title}】").bold = True
            for part in [line for line in text.splitlines() if line.strip()] + lines:
                cell.add_paragraph(part)

    # 後面的證照名稱（圖片請學生自己貼）
    names = [item["name"] for item in choices["credentials"]][:CERT_PHOTOS]
    slots = [cell for row in document.tables[3].rows for cell in _unique_cells(row) if cell.text.strip() == "證照名稱"]
    for slot, name in zip(slots, names):
        _append(slot.paragraphs[0], "：" + name)

    stream = BytesIO()
    document.save(stream)
    stream.seek(0)
    return stream

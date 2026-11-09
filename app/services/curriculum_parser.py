"""修業科目表 PDF 解析與檢查（2026-11-09）。

資管科網頁公開的修業科目表是電子 PDF，文字可以直接取出，不用 OCR，也不讓 AI 讀數字：
- 每一列是「中文科目名 英文名 學分 時數 各學期學分時數… 備註」；備註常寫對應證照（例如「會計丙級」）。
- 第一頁以「小計」列切成必修區段。區段類別印在左欄直書，取出的文字對不上，所以改由區段裡的科目判斷：
  有全民國防教育＝校定必修、有實務專題＝院定必修、有國文＝一般科目必修、全是進階分類通識＝進階分類通識、
  通識選修＝通識選修（110 以前才有）、有程式設計等＝專業必修。認不出來就留空，檢查會失敗，不猜。
- 第二頁起是選修：名稱有「實習」＝校外實習、「微學分」開頭＝微學分，其餘＝專業選修。
- 總學分從「總畢業學分數需修滿 220 學分（必修 181 分，選修 39 學分）」取得。

檢查（run_checks）任一項不過，就不能成為候選版本，只回報原因給管理員。
"""

import html as html_lib
import io
import re
from urllib.parse import urljoin

ROW = re.compile(r"^(?P<head>.*?)\s+(?P<credit>\d+)\s+(?P<hours>\d+)(?P<rest>(?:\s+\d+)*)\s*(?P<note>\D.*)?$")
SUBTOTAL = re.compile(r"^\d+(\s+\d+){10,}$")
CJK = re.compile(r"[一-鿿]")
TOTALS = re.compile(r"總畢業學分數需修滿\s*(\d+)\s*學分\s*[（(]\s*必修\s*(\d+)\s*分\s*[，,]\s*選修\s*(\d+)\s*學分")
INDEX_LINK = re.compile(r'<a[^>]*href="([^"]+\.pdf)"[^>]*>(.*?)</a>', re.S | re.I)
INDEX_TEXT = re.compile(r"^(\d{2,3})年度入學五專修業科目表$")

REQUIRED_CATEGORIES = ("校定必修", "院定必修", "一般科目必修", "進階分類通識", "通識選修", "專業必修")
ELECTIVE_CATEGORIES = ("專業選修", "校外實習", "微學分")
SCHOOL_REQUIRED = {"全民國防教育", "康寧全人教育", "康寧勞作教育", "服務學習與實踐"}
PROFESSIONAL_MARKERS = {"程式設計", "會計概論", "網頁設計", "資料結構", "系統分析與設計"}
MIN_COURSES = 50


def _section_category(names):
    if not names:
        return None
    if SCHOOL_REQUIRED & set(names):
        return "校定必修"
    if "實務專題" in names:
        return "院定必修"
    if "國文" in names:
        return "一般科目必修"
    if all(name.startswith("進階分類通識") for name in names):
        return "進階分類通識"
    if all(name.startswith("通識選修") for name in names):
        return "通識選修"
    if PROFESSIONAL_MARKERS & set(names):
        return "專業必修"
    return None


def _elective_category(name):
    if "實習" in name:
        return "校外實習"
    if name.startswith("微學分"):
        return "微學分"
    return "專業選修"


def _split_head(head):
    """「JAVA程式語言 JAVA Programming Language」→ 中文名、英文名：中文名到最後一個含中文字的詞為止。"""
    tokens = head.split()
    last = max((i for i, token in enumerate(tokens) if CJK.search(token)), default=-1)
    if last < 0 or last == len(tokens) - 1:
        return None, None
    zh_tokens = tokens[: last + 1]
    zh = "".join(zh_tokens) if all(CJK.search(token) for token in zh_tokens) else " ".join(zh_tokens)
    return zh, " ".join(tokens[last + 1:])


def page_texts(content):
    """PDF 每一頁的文字（pypdfium2，已在 requirements）。"""
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(io.BytesIO(content))
    try:
        return [document[index].get_textpage().get_text_bounded() for index in range(len(document))]
    finally:
        document.close()


def parse_text(pages):
    """pages：每頁文字。回傳 {courses, sections, totals, notes}。"""
    courses, sections = [], []
    pending = []  # 第一頁目前區段的科目
    for page_no, text in enumerate(pages, 1):
        buffer = ""
        for raw in (line.strip() for line in text.splitlines()):
            if not raw:
                continue
            if SUBTOTAL.match(raw):
                if page_no == 1:
                    names = [course["name"] for course in pending]
                    category = _section_category(names)
                    for course in pending:
                        course["category"] = category
                    sections.append({"category": category, "subtotal": int(raw.split()[0]),
                                     "first": names[0] if names else ""})
                    pending = []
                buffer = ""
                continue
            line = f"{buffer} {raw}".strip() if buffer else raw
            match = ROW.match(line)
            if match and CJK.search(match["head"]):
                zh, english = _split_head(match["head"])
                if zh:
                    course = {"name": zh, "english": english, "credits": int(match["credit"]),
                              "hours": int(match["hours"]), "note": (match["note"] or "").strip(),
                              "category": None if page_no == 1 else _elective_category(zh)}
                    courses.append(course)
                    if page_no == 1:
                        pending.append(course)
                    buffer = ""
                    continue
            # 科目列被換行切開（英文名太長）：先暫存，和下一行接起來再試
            if not buffer and CJK.search(raw) and re.search(r"[A-Za-z]", raw) and len(raw) < 80:
                buffer = raw
            elif buffer and re.match(r"^[A-Za-z(0-9]", raw):
                buffer = line
            else:
                buffer = ""
    if pending:  # 第一頁最後一段沒有小計
        sections.append({"category": None, "subtotal": None, "first": pending[0]["name"]})
    flat = re.sub(r"\s+", " ", " ".join(pages))
    found = TOTALS.search(flat)
    totals = ({"total": int(found[1]), "required": int(found[2]), "elective": int(found[3])} if found else None)
    notes = [re.sub(r"\s+", " ", note).strip() for note in re.findall(r"\d\.\s*([^※\n]{6,60}?學分[^※\n]{0,20})", "\n".join(pages))]
    return {"courses": courses, "sections": sections, "totals": totals, "notes": notes}


def parse_pdf(content):
    return parse_text(page_texts(content))


def required_sum(result):
    return sum(course["credits"] for course in result["courses"] if course["category"] in REQUIRED_CATEGORIES)


def run_checks(result):
    """回傳 [{name, ok, detail}]。全部 ok 才能成為候選版本。"""
    checks = []
    unknown = [section["first"] for section in result["sections"] if not section["category"]]
    checks.append({"name": "必修區段類別都認得", "ok": not unknown,
                   "detail": "全部認得" if not unknown else f"認不出這些區段（第一個科目）：{'、'.join(unknown)}"})
    wrong = []
    for section in result["sections"]:
        if not section["category"] or section["subtotal"] is None:
            continue
        got = sum(course["credits"] for course in result["courses"]
                  if course["category"] == section["category"])
        if got != section["subtotal"]:
            wrong.append(f"{section['category']} 加總 {got}，小計 {section['subtotal']}")
    checks.append({"name": "各區段學分加總等於小計", "ok": not wrong, "detail": "；".join(wrong) or "全部相符"})
    totals = result.get("totals")
    checks.append({"name": "讀到總畢業學分說明", "ok": bool(totals),
                   "detail": (f"總 {totals['total']}、必修 {totals['required']}、選修 {totals['elective']}"
                              if totals else "找不到「總畢業學分數需修滿…」這句")})
    if totals:
        got = required_sum(result)
        checks.append({"name": "必修科目加總等於必修學分", "ok": got == totals["required"],
                       "detail": f"科目加總 {got}，規定 {totals['required']}"})
        checks.append({"name": "必修加選修等於總畢業學分",
                       "ok": totals["required"] + totals["elective"] == totals["total"],
                       "detail": f"{totals['required']} + {totals['elective']} = {totals['total']}"})
    count = len(result["courses"])
    checks.append({"name": "科目數量合理", "ok": count >= MIN_COURSES, "detail": f"共 {count} 門"})
    return checks


def diff_courses(old, new):
    """以（類別, 科目名）比對。回傳 {added, removed, changed}，changed 是學分或備註不同。"""
    def key(course):
        return (course["category"], course["name"])
    before = {key(course): course for course in old}
    after = {key(course): course for course in new}
    added = [after[k] for k in after if k not in before]
    removed = [before[k] for k in before if k not in after]
    changed = [{"category": k[0], "name": k[1], "before": before[k]["credits"], "after": after[k]["credits"]}
               for k in after if k in before and before[k]["credits"] != after[k]["credits"]]
    return {"added": added, "removed": removed, "changed": changed}


def summarize_diff(diff, previous_label="前一版"):
    """把差異寫成給管理員看的白話重點（數字全部來自解析結果，不經 AI）。"""
    def names(items):
        return "、".join(f"{item['name']}（{item['category']}）" for item in items[:8]) + ("等" if len(items) > 8 else "")
    parts = [f"和{previous_label}相比：新增 {len(diff['added'])} 門、刪除 {len(diff['removed'])} 門、"
             f"學分變動 {len(diff['changed'])} 門。"]
    if diff["added"]:
        parts.append(f"新增：{names(diff['added'])}。")
    if diff["removed"]:
        parts.append(f"刪除：{names(diff['removed'])}。")
    if diff["changed"]:
        parts.append("學分變動：" + "、".join(f"{item['name']} {item['before']}→{item['after']}"
                                         for item in diff["changed"][:8]) + "。")
    return "".join(parts)


def parse_index(page_html, base_url):
    """資管科「修業科目表」頁面 → {入學年度: PDF 網址}；替代課程對照表等其他連結不收。"""
    links = {}
    for href, inner in INDEX_LINK.findall(page_html):
        text = html_lib.unescape(re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", inner)))
        matched = INDEX_TEXT.match(text)
        if matched:
            links.setdefault(int(matched[1]), urljoin(base_url, href))
    return links

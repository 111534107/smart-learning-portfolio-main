"""學校名錄（2026-11-13 導師建議：選校系要分北中南）：每所學校的地區、縣市、座標與網站。

- 資料在資料庫（schools、school_department_links），管理員在「學校資料」頁維護：逐筆改、匯出改好再匯入、檢查連結。
- 預設資料在 app/content/schools.csv 與 school_department_links.csv（2026-11-13 實際查過、網址都點開過）；
  第一次使用或展示站啟動時匯入。
- 區域劃分依國家發展委員會：北部 基北桃竹宜、中部 苗中彰投雲、南部 嘉南高屏澎、東部 花東、離島 金馬。
- 地圖投影（project）也在這裡：台灣地圖與學校標記用同一個公式，標記一定落在正確位置。
"""
import csv
import io
import math
from datetime import date, datetime, timezone
from pathlib import Path

from app.extensions import db
from app.models import School, SchoolDepartmentLink

CONTENT = Path(__file__).resolve().parents[1] / "content"
SCHOOLS_FILE = CONTENT / "schools.csv"
DEPARTMENT_LINKS_FILE = CONTENT / "school_department_links.csv"
REGIONS = ("北部", "中部", "南部", "東部", "離島")
REGION_OF_COUNTY = {
    **{c: "北部" for c in ("臺北市", "新北市", "基隆市", "桃園市", "桃園縣", "新竹縣", "新竹市", "宜蘭縣")},
    **{c: "中部" for c in ("苗栗縣", "臺中市", "彰化縣", "南投縣", "雲林縣")},
    **{c: "南部" for c in ("嘉義縣", "嘉義市", "臺南市", "高雄市", "屏東縣", "澎湖縣")},
    **{c: "東部" for c in ("花蓮縣", "臺東縣")},
    **{c: "離島" for c in ("金門縣", "連江縣")},
}
CSV_COLUMNS = ("學校", "地區", "縣市", "緯度", "經度", "官網", "招生網站", "確認日期")

# 地圖投影：經緯度 → SVG 座標（viewBox 0 0 360 560）。經度依台灣緯度縮放，形狀不會變寬。
MAP_WIDTH, MAP_HEIGHT = 360, 560
_LON0, _LAT1, _LAT0 = 119.3, 25.35, 21.85
_SCALE = MAP_HEIGHT / (_LAT1 - _LAT0)
_LON_FACTOR = math.cos(math.radians(23.7))


def project(lon, lat):
    return (lon - _LON0) * _LON_FACTOR * _SCALE, (_LAT1 - lat) * _SCALE


def normalize_county(name):
    return (name or "").strip().replace("台", "臺")


class ImportRejected(ValueError):
    """匯入的檔案有問題；訊息給管理員看。"""


def _float(value, label, row_no):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ImportRejected(f"第 {row_no} 列「{label}」要填數字。") from None


def _clean_url(value, label, row_no):
    from app.services.form_library_service import LinkRejected, clean_url
    try:
        return clean_url(value)
    except LinkRejected:
        raise ImportRejected(f"第 {row_no} 列「{label}」不是 http 或 https 網址。") from None


def import_schools(text):
    """匯入學校 CSV（欄位見 CSV_COLUMNS）：同名學校更新，沒有的新增；不刪除沒列到的學校。回傳 (新增, 更新)。不 commit。"""
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    missing = [c for c in CSV_COLUMNS[:7] if rows and c not in rows[0]]
    if not rows or missing:
        raise ImportRejected("檔案的第一列要是欄位名稱：" + "、".join(CSV_COLUMNS) + (f"（缺：{'、'.join(missing)}）" if missing else ""))
    added = updated = 0
    for row_no, row in enumerate(rows, start=2):
        name = (row.get("學校") or "").strip()
        if not name:
            continue
        region = (row.get("地區") or "").strip()
        if region not in REGIONS:
            raise ImportRejected(f"第 {row_no} 列「地區」只能填：{'、'.join(REGIONS)}。")
        lat, lon = _float(row.get("緯度"), "緯度", row_no), _float(row.get("經度"), "經度", row_no)
        if not (21 < lat < 27 and 118 < lon < 123):
            raise ImportRejected(f"第 {row_no} 列的座標不在台灣範圍內，請確認緯度、經度沒有填反。")
        school = School.query.filter_by(name=name).first()
        if school is None:
            school = School(name=name)
            db.session.add(school)
            added += 1
        else:
            updated += 1
        school.region, school.city = region, normalize_county(row.get("縣市"))[:20] or None
        school.latitude, school.longitude = lat, lon
        school.website_url = _clean_url(row.get("官網"), "官網", row_no)
        school.admission_url = _clean_url(row.get("招生網站"), "招生網站", row_no)
        checked = (row.get("確認日期") or "").strip()
        try:
            school.checked_on = date.fromisoformat(checked) if checked else None
        except ValueError:
            raise ImportRejected(f"第 {row_no} 列「確認日期」格式要像 2026-11-13。") from None
    db.session.flush()
    return added, updated


def import_department_links(text):
    """匯入科系網址 CSV（學校,科系,網址）；學校要先存在。回傳筆數。不 commit。"""
    count = 0
    for row_no, row in enumerate(csv.DictReader(io.StringIO(text.lstrip("﻿"))), start=2):
        school = School.query.filter_by(name=(row.get("學校") or "").strip()).first()
        department = (row.get("科系") or "").strip()
        if not school or not department:
            continue
        url = _clean_url(row.get("網址"), "網址", row_no)
        link = SchoolDepartmentLink.query.filter_by(school_id=school.id, department_name=department).first()
        if url is None:
            if link:
                db.session.delete(link)
            continue
        if link is None:
            link = SchoolDepartmentLink(school=school, department_name=department)
            db.session.add(link)
        link.url = url
        count += 1
    db.session.flush()
    return count


def import_defaults():
    """匯入預設資料（展示站啟動、管理員按「載入預設資料」時用）。不 commit。"""
    added, updated = import_schools(SCHOOLS_FILE.read_text(encoding="utf-8-sig"))
    links = import_department_links(DEPARTMENT_LINKS_FILE.read_text(encoding="utf-8-sig"))
    return added, updated, links


def export_schools():
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for school in School.query.order_by(School.region, School.name):
        writer.writerow([school.name, school.region, school.city or "", school.latitude, school.longitude,
                         school.website_url or "", school.admission_url or "",
                         school.checked_on.isoformat() if school.checked_on else ""])
    return "﻿" + out.getvalue()  # 加 BOM，Excel 打開中文不會變亂碼


def export_department_links():
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(("學校", "科系", "網址"))
    for link in SchoolDepartmentLink.query.join(School).order_by(School.name, SchoolDepartmentLink.department_name):
        writer.writerow([link.school.name, link.department_name, link.url])
    return "﻿" + out.getvalue()


def by_name():
    return {school.name: school for school in School.query.all()}


def school_links(program, schools=None):
    """學校卡片的網址：官網、招生網站、科系介紹（沒有就請學生到官網找）。回傳 [{label, url}]。"""
    schools = by_name() if schools is None else schools
    school = schools.get(program.school_name)
    if not school:
        return []
    links = []
    if school.website_url:
        links.append({"label": "學校官網", "url": school.website_url})
    if school.admission_url:
        links.append({"label": "招生網站", "url": school.admission_url})
    department = next((link for link in school.department_links if link.department_name == program.department_name), None)
    if department:
        links.append({"label": "科系介紹", "url": department.url})
    elif school.website_url:
        links.append({"label": "科系介紹（請從官網找科系）", "url": school.website_url})
    return links


def google_maps_url(school):
    from urllib.parse import quote
    return f"https://www.google.com/maps/search/?api=1&query={quote(school.name)}"


def map_points(programs, schools=None):
    """地圖上的學校標記：[{school, x, y, region, programs}]，只放有校系的學校。"""
    schools = by_name() if schools is None else schools
    grouped = {}
    for program in programs:
        school = schools.get(program.school_name)
        if school and school.latitude is not None:
            grouped.setdefault(school.name, {"school": school, "programs": []})["programs"].append(program)
    points = []
    for entry in grouped.values():
        x, y = project(entry["school"].longitude, entry["school"].latitude)
        points.append({**entry, "x": round(x, 1), "y": round(y, 1), "region": entry["school"].region,
                       "maps_url": google_maps_url(entry["school"])})
    return sorted(points, key=lambda p: (REGIONS.index(p["region"]) if p["region"] in REGIONS else 9, p["school"].name))


def check_links():
    """檢查所有學校與科系網址（不 commit）。回傳 [(名稱, 網址, 狀態, 說明)]，只列不正常的。"""
    from concurrent.futures import ThreadPoolExecutor

    from app.services.form_library_service import check_link
    targets = []
    for school in School.query.order_by(School.name):
        for label, url in (("官網", school.website_url), ("招生網站", school.admission_url)):
            if url:
                targets.append((f"{school.name}{label}", url, school))
        for link in school.department_links:
            targets.append((f"{school.name}{link.department_name}", link.url, school))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda t: check_link(t[1]), targets)) if targets else []
    now = datetime.now(timezone.utc)
    problems = {}
    for (name, url, school), (status, detail) in zip(targets, results):
        if status != "ok":
            problems.setdefault(school.id, []).append((name, url, status, detail))
    for school in School.query.all():
        school.links_checked_at = now
        school.link_problems = len(problems.get(school.id, []))
    return [item for items in problems.values() for item in items], len(targets)

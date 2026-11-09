"""修業科目表代理（2026-11-09）。

流程：抓資管科「修業科目表」頁面 → 找出各入學年度 PDF → 下載 → 程式解析（curriculum_parser）→ 檢查數字
→ 存成候選版本（或「檢查不通過」）→ 管理員確認才生效（專題規則：AI 不得自行發布規則）。

- 不用 OCR、不讓 AI 讀數字；差異摘要也由程式產生。
- 同一個檔案（雜湊相同）再抓一次不會產生新版本。
- 確認後，畢業門檻（graduation_check_service）改用這一版的科目與總學分；沒確認的年度沿用 CSV。
"""
import hashlib
from datetime import datetime, timezone

from flask import current_app, has_app_context
from sqlalchemy import inspect

from app.extensions import db
from app.models import CurriculumCourse, CurriculumVersion
from app.services import audit_service
from app.services import curriculum_parser as parser

INDEX_URL = "https://im.ukn.edu.tw/p/405-1028-609,c82-1.php"
MIN_YEAR = 109  # 目前在學的五專生最早是 109 學年度入學（含延畢）


class CurriculumError(Exception):
    pass


def _now():
    return datetime.now(timezone.utc)


def _sha256(content):
    return hashlib.sha256(content).hexdigest()


def _fetch():
    configured = current_app.config.get("CURRICULUM_FETCH") if has_app_context() else None
    if configured:
        return configured
    from app.services.admission_agent_service import fetch_url
    return fetch_url


def _csv_courses(year):
    """人工核對過的 CSV（app/content/curriculum_groups.csv）裡該年度的科目，比對差異用。"""
    from app.services.eligibility_service import CURRICULUM_FILE
    import csv
    with open(CURRICULUM_FILE, encoding="utf-8-sig", newline="") as handle:
        return [{"category": row["科目類別"], "name": row["科目名稱"], "credits": None}
                for row in csv.DictReader(handle) if row["入學年度"] == str(year)]


def _baseline(year):
    """比對對象：同年度（已確認版本 → 人工核對 CSV），沒有就往前找最近的年度。回傳 (科目清單, 說明)。"""
    for candidate_year in range(year, year - 6, -1):
        same = candidate_year == year
        published = CurriculumVersion.query.filter_by(admission_year=candidate_year, status="published").first()
        if published:
            return ([_course_dict(course) for course in published.courses],
                    "目前確認的版本" if same else f"{candidate_year} 學年度確認版")
        rows = _csv_courses(candidate_year)
        if rows:
            return rows, "人工核對的科目表（CSV）" if same else f"{candidate_year} 學年度科目表（人工核對）"
    return None, ""


def _course_dict(course):
    return {"category": course.category, "name": course.name, "credits": course.credits}


def _diff(baseline, courses):
    diff = parser.diff_courses(baseline, courses)
    # CSV 沒有學分欄，不比學分
    diff["changed"] = [item for item in diff["changed"] if item["before"] is not None]
    return {key: [{"category": item["category"], "name": item["name"],
                   **({"before": item["before"], "after": item["after"]} if key == "changed" else {})}
                  for item in value] for key, value in diff.items()}


def _save_version(year, url, content, result, checks):
    totals = result.get("totals") or {}
    baseline, label = _baseline(year)
    if baseline is None:
        diff, summary = None, "沒有可比對的舊版本（第一次匯入這個年度）。"
    else:
        diff = _diff(baseline, result["courses"])
        summary = parser.summarize_diff(diff, label)
    ok = all(check["ok"] for check in checks)
    version = CurriculumVersion(
        admission_year=year, status="candidate" if ok else "check_failed", source_url=url,
        file_sha256=_sha256(content), total_credits=totals.get("total"),
        required_credits=totals.get("required"), elective_credits=totals.get("elective"),
        checks_json=checks, diff_json=diff, notes_json=result.get("notes") or [], summary=summary)
    for order, course in enumerate(result["courses"]):
        version.courses.append(CurriculumCourse(
            category=course["category"], name=course["name"][:100], english_name=(course["english"] or "")[:200],
            credits=course["credits"], hours=course["hours"], note=(course["note"] or "")[:100] or None,
            sort_order=order))
    db.session.add(version)
    return version


def check_updates(requester, fetch=None, years=None):
    """抓網頁、逐年下載解析。回傳 {created, unchanged, failed, errors}（年度清單）。只 flush＋提交一次。"""
    fetch = fetch or _fetch()
    page, _ = fetch(INDEX_URL)
    links = parser.parse_index(page.decode("utf-8", errors="replace"), INDEX_URL)
    wanted = sorted(year for year in links if (years is None and year >= MIN_YEAR) or (years and year in years))
    outcome = {"created": [], "unchanged": [], "failed": [], "errors": []}
    for year in wanted:
        url = links[year]
        try:
            content, _ = fetch(url)
        except Exception as exc:  # 單一年度下載失敗不影響其他年度
            outcome["errors"].append({"year": year, "error": str(exc)[:200]})
            continue
        if CurriculumVersion.query.filter_by(admission_year=year, file_sha256=_sha256(content)).first():
            outcome["unchanged"].append(year)
            continue
        try:
            result = parser.parse_pdf(content)
        except Exception as exc:
            outcome["errors"].append({"year": year, "error": f"PDF 讀不出文字：{str(exc)[:150]}"})
            continue
        checks = parser.run_checks(result)
        version = _save_version(year, url, content, result, checks)
        outcome["created" if version.status == "candidate" else "failed"].append(year)
    audit_service.record(requester, "curriculum.check", "curriculum_version", None, detail=outcome)
    db.session.commit()
    return outcome


def publish(version, admin):
    if version.status != "candidate" or not version.checks_ok:
        raise CurriculumError("只有檢查全部通過的候選版本可以確認。")
    for old in CurriculumVersion.query.filter_by(admission_year=version.admission_year, status="published"):
        old.status = "superseded"
    version.status = "published"
    version.reviewed_by_id = admin.id
    version.reviewed_at = _now()
    audit_service.record(admin, "curriculum.publish", "curriculum_version", version.id,
                         detail={"admission_year": version.admission_year})


def reject(version, admin):
    if version.status not in ("candidate", "check_failed"):
        raise CurriculumError("這一版已經處理過。")
    version.status = "rejected"
    version.reviewed_by_id = admin.id
    version.reviewed_at = _now()
    audit_service.record(admin, "curriculum.reject", "curriculum_version", version.id,
                         detail={"admission_year": version.admission_year})


def _table_ready():
    try:
        # 用目前交易的連線檢查；另開連線在 SQLite 記憶體資料庫會把還沒提交的資料退回
        return has_app_context() and inspect(db.session.connection()).has_table("curriculum_versions")
    except Exception:
        return False


def published_versions():
    """{入學年度: CurriculumVersion}；沒有 app context 或資料表時回傳空的（沿用 CSV）。"""
    if not _table_ready():
        return {}
    return {version.admission_year: version
            for version in CurriculumVersion.query.filter_by(status="published").all()}


def credit_rule(year):
    version = published_versions().get(year)
    if version is None or version.total_credits is None:
        return None
    return {"total": version.total_credits, "required": version.required_credits,
            "elective": version.elective_credits,
            "source": f"{year} 學年度入學五專修業科目表（管理員確認版）"}


def pending_count():
    if not _table_ready():
        return 0
    return CurriculumVersion.query.filter(CurriculumVersion.status.in_(("candidate", "check_failed"))).count()

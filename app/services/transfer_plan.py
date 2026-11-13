"""插大自填目標（B18）：準備度計算、表單解析、範例校帶入。

準備度＝各考科自評進度的平均（0–100）。提醒強度看離考試幾天與準備度：
- 已過考期 → past
- 簡章學年度不是「明年入學」那一屆 → 過期提醒（今天 115 學年度，學生要考的是 116 學年度）
- 30 天內且準備度 < 70 → urgent；90 天內且 < 50 → warn；其他 → ok
這是學生自評，只用來排準備順序，不代表錄取機率。
"""

import re
from datetime import date

from app.services.journey_service import academic_year_of
from app.services.transfer_exam import TRANSFER_FILE, _rows

MAX_SUBJECTS = 8


def target_year(today=None):
    """學生現在準備的是下一學年度的轉學考。"""
    return academic_year_of(today or date.today()) + 1


def readiness(plan, today=None):
    today = today or date.today()
    subjects = list(plan.subjects)
    score = round(sum(s.progress for s in subjects) / len(subjects)) if subjects else 0
    days = (plan.exam_date - today).days if plan.exam_date else None
    apply_days = (plan.apply_end - today).days if plan.apply_end else None
    stale = plan.admission_year < target_year(today)
    if days is not None and days < 0:
        level, message = "past", "考期已過。若要考下一屆，請改成新學年度的簡章。"
    elif days is not None and days <= 30 and score < 70:
        level, message = "urgent", f"離考試只剩 {days} 天，準備度 {score}%，先補進度最低的科目。"
    elif days is not None and days <= 90 and score < 50:
        level, message = "warn", f"離考試 {days} 天，準備度 {score}%，建議每週排固定時間。"
    elif days is None:
        level, message = "nodate", "還沒填考試日期；簡章公告後補上，系統才能倒數。"
    else:
        level, message = "ok", f"離考試 {days} 天，準備度 {score}%。"
    weakest = min(subjects, key=lambda s: s.progress) if subjects else None
    return {
        "score": score,
        "days": days,
        "apply_days": apply_days,
        "level": level,
        "message": message,
        "stale": stale,
        "stale_message": (f"這是 {plan.admission_year} 學年度（已考完的）簡章，只能當格式參考；"
                          f"{target_year(today)} 學年度簡章公告後請更新日期與考科。") if stale else "",
        "weakest": weakest,
    }


def clean_subject(text):
    """「計算機概論×1.5」→「計算機概論」。"""
    text = re.sub(r"[（(].*?[）)]", "", text)
    text = re.sub(r"\s*[×xX＊*]\s*[\d.]+\s*$", "", text)
    return text.strip()


def split_subjects(text):
    if not text or "待確認" in text or "不考筆試" in text:
        return []
    names = [clean_subject(part) for part in re.split(r"[、，,；;\n]", text)]
    return [name for name in names if name][:MAX_SUBJECTS]


def _parse_date(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def example_schools(path=None):
    """B17 少數範例校（115 學年度，只當格式參考），給學生「從範例帶入」。"""
    try:
        rows = _rows(path or TRANSFER_FILE)
    except FileNotFoundError:
        return []
    examples = []
    for row in rows:
        grade_text = row.get("插入年級", "")
        examples.append({
            "code": row["志願代碼"].strip(),
            "school": row["學校"].strip(),
            "department": row["科系"].strip(),
            "entry_grade": 3 if "三" in grade_text else 2 if "二" in grade_text else "",
            "admission_year": row["學年度"].strip(),
            "brochure_url": row.get("簡章網址", "").strip(),
            "subjects": split_subjects(row.get("考試科目", "")),
        })
    return examples


class PlanFormError(ValueError):
    pass


def parse_plan_form(form):
    """回傳可以直接寫進 TransferPlan 的欄位與考科名稱清單；欄位錯誤丟 PlanFormError。"""
    school = (form.get("school_name") or "").strip()[:100]
    department = (form.get("department_name") or "").strip()[:100]
    if not school or not department:
        raise PlanFormError("請填學校與科系。")
    try:
        year = int(form.get("admission_year") or 0)
    except ValueError:
        raise PlanFormError("學年度請填數字，例如 116。")
    if not 100 <= year <= 200:
        raise PlanFormError("學年度請填民國年，例如 116。")
    grade = form.get("entry_grade") or ""
    url = (form.get("brochure_url") or "").strip()[:500]
    if url and not url.startswith(("http://", "https://")):
        raise PlanFormError("簡章網址要用 http:// 或 https:// 開頭。")
    fields = {
        "school_name": school,
        "department_name": department,
        "entry_grade": int(grade) if grade in ("2", "3") else None,
        "admission_year": year,
        "brochure_url": url or None,
        "apply_start": _parse_date(form.get("apply_start")),
        "apply_end": _parse_date(form.get("apply_end")),
        "exam_date": _parse_date(form.get("exam_date")),
        "note": (form.get("note") or "").strip()[:2000] or None,
    }
    if fields["apply_start"] and fields["apply_end"] and fields["apply_start"] > fields["apply_end"]:
        raise PlanFormError("報名開始日不能晚於報名截止日。")
    names = split_subjects(form.get("subjects") or "")
    return fields, names


def apply_subjects(plan, names, progress=None):
    """依名稱清單重建考科；同名的考科保留原本進度。"""
    from app.models import TransferPlanSubject

    old = {s.name: s.progress for s in plan.subjects}
    progress = progress or {}
    plan.subjects = [
        TransferPlanSubject(name=name[:60], progress=progress.get(name, old.get(name, 0)), sort_order=index)
        for index, name in enumerate(dict.fromkeys(names))
    ]


def clamp_progress(value):
    try:
        return min(max(int(value), 0), 100)
    except (TypeError, ValueError):
        return 0

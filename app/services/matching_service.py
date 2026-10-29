"""A3 媒合排序 Agent（最小版）：對全部正式校系判斷能不能報、算契合度、排序，每一間都寫理由。

規則（寫在這裡，方便報告時說明；規格見 AI_設計規格_Agent分工規劃_2026-10-22.md）：
- 契合度 = 缺件比對的準備度（gap_service.analyze_gap），兩邊數字一定相同。不是錄取機率。
- 報考資格條件依類型檢查；看不懂的條件或缺少學生資料時一律「需確認」，不當成符合（D8）。
- 排序：可報 → 需確認 → 不可報；同一組裡學群相關的科系在前、學群待確認的居中，再依契合度高到低。
  不可報的仍然列出來，並寫明原因。
- 相關與否比對「學生主要學群」（A2，eligibility_service 依已確認的成績與課綱算出）和「校系學群」（人工對照表）；
  任一邊待確認時理由會明說，不用系名關鍵字猜（系名有「資訊」「數位」不代表屬資訊學群）。
- 這一版的理由由規則產生；之後再交給 AI 改寫成白話（AI 額度用完時仍顯示規則版）。
- 插大（轉學考）：只考筆試、沒有備審加權的校系不算契合度，改寫「依考試成績，不算契合度」，理由列出考科與報考資格；
  有書面審查加權的（例如臺大資工）照常算契合度。報考資格系統無法自動判斷，一律「需確認」（D8）。

目前支援的條件類型：
- fresh_graduate（C1 應屆）：預計畢業學年度 = 入學學年度 + 5。報考學年度之前就已畢業的，不是應屆。
- transfer_eligibility（插大報考資格）：一律「需確認」，並顯示簡章原文（資料來自 admission_transfer_demo.csv）。
- skill_credential（C5 技優資格）：已確認的證照達到「等級」欄、且在「期限」欄（民國年）以前取得才可報；
  沒有符合的證照或缺日期是「需確認」（可能還沒上傳）；證照都在期限後才取得是「不可報」。
- 其他類型：一律「需確認」，並顯示簡章原文。
"""

import csv
import re
from datetime import date
from pathlib import Path

from app.models import CredentialRecord

from app.services.admission_links import admission_links, load_school_links
from app.services.admission_schedule import channel_label, load_schedule, timeline
from app.services.eligibility_service import department_groups, load_department_groups, summarize_student_groups
from app.services.gap_service import ALL_LABELS, analyze_gap
from app.services.journey_service import build_journey
from app.services.transfer_exam import is_transfer, load_transfer_details

CONDITIONS_FILE = Path(__file__).resolve().parents[1] / "content" / "admission_conditions_demo.csv"

# 學群相關（True）→ 待確認（None）→ 不相關（False）
RELATED_ORDER = {True: 0, None: 1, False: 2}
# 學群待確認（成績還不夠判斷）時，暫依學生科別排序，免得不相關的系排第一（10-27 實測問題 1）。
# 只影響排序與一句說明；related 仍是 None，畫面照樣寫「學群待確認」。
DEPARTMENT_DEFAULT_GROUPS = {"資管科": "資訊"}

STATUS_ORDER = {"eligible": 0, "needs_check": 1, "ineligible": 2}
STATUS_LABELS = {"eligible": "可報", "needs_check": "需確認", "ineligible": "不可報"}
NO_FIT_TRANSFER = "依考試成績，不算契合度"


def load_conditions(path=None):
    """讀報考資格條件 CSV，回傳 {志願代碼: [{type, text, source}]}。檔案不存在時回傳空的。"""
    path = path or CONDITIONS_FILE
    if not Path(path).is_file():
        return {}
    conditions = {}
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            conditions.setdefault(row["志願代碼"], []).append({
                "type": row["條件類型"].strip(),
                "text": row["條件原文"].strip(),
                "source": row["出處"].strip(),
                # C5 技優資格用：證照至少要幾級、幾號以前取得（民國年月日）；其他條件留空
                "level": (row.get("等級") or "").strip() or None,
                "deadline": (row.get("期限") or "").strip() or None,
            })
    return conditions


def _cite(condition):
    return f"（出處：{condition['source']}）" if condition.get("source") else ""


def _check_fresh_graduate(student, program, condition):
    profile = student.student_profile
    admission_year = profile.admission_year if profile else None
    if admission_year is None:
        return "needs_check", f"這個志願限應屆畢業生{_cite(condition)}，系統沒有你的入學年度，請確認。"
    graduation_year = admission_year + 5
    if graduation_year < program.admission_year:
        return "ineligible", (f"這個志願限應屆畢業生{_cite(condition)}。依入學年度推算你在 {graduation_year} 年畢業，"
                              f"報考 {program.admission_year} 學年度時已不是應屆；如果你延畢還沒畢業，請告訴導師更正。")
    return "eligible", (f"這個志願限應屆畢業生，依入學年度推算你在 {graduation_year} 年畢業，"
                        f"報考那一年是應屆；如有延畢或休學請告訴導師。")


def _check_transfer_eligibility(student, program, condition):
    return "needs_check", f"插大報考資格系統無法自動判斷，請對照你的學歷自己核對：「{condition['text']}」{_cite(condition)}"


LEVEL_RANK = {"丙級": 1, "乙級": 2, "甲級": 3}


def _level_of(credential):
    text = f"{credential.level or ''}{credential.credential_name or ''}"
    return max((rank for name, rank in LEVEL_RANK.items() if name in text), default=0)


def _roc_date(text):
    """「115/04/13」→ date(2026, 4, 13)；看不懂回傳 None。"""
    parts = re.findall(r"\d+", text or "")
    if len(parts) != 3:
        return None
    try:
        return date(int(parts[0]) + 1911, int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def _check_skill_credential(student, program, condition):
    """C5：已確認的證照裡，有沒有達到等級、且在期限內取得的。系統沒有資料時是「需確認」，不是「不可報」。"""
    required, deadline = condition.get("level"), _roc_date(condition.get("deadline"))
    if required not in LEVEL_RANK:
        return "needs_check", f"簡章要求技優資格，系統無法自動判斷，請自己核對：「{condition['text']}」{_cite(condition)}"
    rule = f"這個志願要{required}以上證照" + (f"、{deadline:%Y-%m-%d} 以前取得" if deadline else "") + _cite(condition)
    qualified = [c for c in CredentialRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed")
                 if _level_of(c) >= LEVEL_RANK[required]]
    if not qualified:
        return "needs_check", f"{rule}。系統裡沒有你已確認的{required}以上證照；如果你有，請上傳並確認。"
    if deadline is None:
        best = qualified[0]
        return "eligible", f"{rule}；你有「{best.credential_name}」。"
    in_time = [c for c in qualified if c.issue_date and c.issue_date <= deadline]
    if in_time:
        best = min(in_time, key=lambda c: c.issue_date)
        return "eligible", f"{rule}；你的「{best.credential_name}」在 {best.issue_date:%Y-%m-%d} 取得，符合。"
    if any(c.issue_date is None for c in qualified):
        return "needs_check", f"{rule}；你的{required}以上證照沒有取得日期，請補上日期確認。"
    latest = max(qualified, key=lambda c: c.issue_date)
    return "ineligible", (f"{rule}；你的「{latest.credential_name}」在 {latest.issue_date:%Y-%m-%d} 才取得，"
                          f"晚於期限 {deadline:%Y-%m-%d}。日期有誤請更正證照資料。")


CHECKS = {"fresh_graduate": _check_fresh_graduate, "transfer_eligibility": _check_transfer_eligibility,
          "skill_credential": _check_skill_credential}


def _check_conditions(student, program, conditions):
    status, reasons = "eligible", []
    for condition in conditions:
        check = CHECKS.get(condition["type"])
        if check:
            result, reason = check(student, program, condition)
        else:
            result, reason = "needs_check", f"簡章還有這項條件，系統無法自動判斷，請自己核對：「{condition['text']}」{_cite(condition)}"
        reasons.append(reason)
        if STATUS_ORDER[result] > STATUS_ORDER[status]:
            status = result
    return status, reasons


def _labels(keys):
    return "、".join(ALL_LABELS.get(key, key) for key in keys)


def _fit_reasons(gap):
    counted = [item for item in gap["items"] if item["fraction"] is not None]
    if not counted:
        return ["這個校系的評分項目都要自己準備（例如自傳、專題），系統還算不出契合度。"]
    reasons = []
    for item in sorted(counted, key=lambda item: -item["weight"]):
        if item["status"] == "complete":
            reasons.append(f"「{item['name']}」占 {item['weight']}%，你已有{_labels(item['have'])}資料。")
        elif item["status"] == "partial":
            reasons.append(f"「{item['name']}」占 {item['weight']}%，你已有{_labels(item['have'])}，"
                           f"還缺{_labels(item['missing'])}。")
        else:
            reasons.append(f"「{item['name']}」占 {item['weight']}%，你還沒有{_labels(item['missing'])}資料。")
    return reasons


def _department_default(student):
    """學生科別的預設學群：(科別, 學群)；看不出科別時回傳 None。"""
    class_name = student.student_profile.class_name if student.student_profile else ""
    return next(((dept, group) for dept, group in DEPARTMENT_DEFAULT_GROUPS.items() if dept in (class_name or "")), None)


def is_related(program, student_groups, department_table=None):
    """學生主要學群是否屬於這個校系的學群；任一邊待確認時回傳 None（排在相關與不相關中間）。"""
    department = department_groups(program, department_table)
    if student_groups["main_group"] is None or department is None:
        return None
    return student_groups["main_group"] in department["groups"]


def _relation_reason(related, student_groups, program, department_table=None):
    if student_groups["main_group"] is None:
        return f"和你的背景是否相關：{student_groups['reason']}"
    department = department_groups(program, department_table)
    if department is None:
        return "這個系的學群待確認：對照表還沒有這個系（或依據不足），請自己看簡章的報考資格與課程。"
    main = student_groups["main_group"]
    basis = (f"你修過的{main}類專業科目 {student_groups['group_counts'][main]} 科，"
             f"這個系屬{'、'.join(group + '學群' for group in department['groups'])}（依據：{department['basis']}）")
    if related:
        return f"{basis}，和你的背景相關。"
    return f"{basis}，和你的{main}學群關聯較低，可以參考，但排在相關科系後面。"


def _transfer_reasons(program, details):
    return [
        f"插大{details['grade']}，考試科目：{details['subjects']}。",
        f"報名費 {details['fee']}；報名 {details['apply_dates']}；{details['exam_date']}"
        f"（{program.admission_year} 學年度簡章，{details['checked_on']} 查詢；出處：{details['source']}）。",
    ]


def _transfer_links(links, details):
    if details and details["admission_url"] and all(link["url"] != details["admission_url"] for link in links):
        links.append({"label": "轉學考招生網站", "url": details["admission_url"]})
    return links


def rank_programs(student, programs, journey=None, conditions=None, transfer=None):
    """回傳排序好的 [{program, status, status_label, channel_label, fit, fit_note, related, reasons, gap,
    transfer, links, schedule}]。"""
    journey = journey or build_journey(student)
    conditions = load_conditions() if conditions is None else conditions
    transfer = load_transfer_details() if transfer is None else transfer
    school_links = load_school_links()
    schedule = load_schedule()
    student_groups = summarize_student_groups(student)
    department_table = load_department_groups()
    fallback = None if student_groups["main_group"] else _department_default(student)
    rows = []
    for program in programs:
        gap = analyze_gap(student, program, journey)
        details = transfer.get(program.program_code) if is_transfer(program) else None
        program_conditions = list(conditions.get(program.program_code, []))
        if details:
            program_conditions.append({"type": "transfer_eligibility", "text": details["eligibility"],
                                       "source": details["source"]})
        status, condition_reasons = _check_conditions(student, program, program_conditions)
        related = is_related(program, student_groups, department_table)
        exam_only = is_transfer(program) and not program.items
        relation = [_relation_reason(related, student_groups, program, department_table)]
        tentative = None
        if fallback:
            groups = (department_groups(program, department_table) or {}).get("groups") or []
            tentative = fallback[1] in groups
            relation.append(f"暫依你的科別（{fallback[0]}）把{fallback[1]}學群的科系排前面；確認成績單後會改用你修過的課判斷。")
        rows.append({
            "program": program,
            "status": status,
            "status_label": STATUS_LABELS[status],
            "channel_label": channel_label(program),
            "fit": gap["readiness"],
            "fit_note": NO_FIT_TRANSFER if exam_only else None,
            "related": related,
            "tentative_related": tentative,
            "reasons": (condition_reasons + relation
                        + (_transfer_reasons(program, details) if details else [])
                        + ([] if exam_only else _fit_reasons(gap))),
            "gap": gap,
            "transfer": details,
            "links": _transfer_links(admission_links(program, school_links), details),
            "schedule": timeline(program, schedule),
        })
    rows.sort(key=lambda row: (STATUS_ORDER[row["status"]], RELATED_ORDER[row["related"]],
                               row["tentative_related"] is False, row["fit"] is None, -(row["fit"] or 0)))
    return rows

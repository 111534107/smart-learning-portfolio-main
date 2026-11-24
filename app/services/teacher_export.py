"""導師班級總覽資料整理與 Excel 匯出服務。

依需求產出班級總覽資料（支援網頁總覽表與 Excel 匯出）：
- 工作表「班級總覽」：學號、姓名、班級、送審校系、自傳狀態、自傳字數、學分缺口或畢業門檻狀態、證照數、待確認送審數。
- 工作表「統計」：以 Excel 公式計算總人數、已送審人數、平均自傳字數、自傳字數標準差、尚未起稿人數。
- 專案個資規則：不放自傳全文、不放缺曠資料、不放電話地址。
"""

from io import BytesIO
import openpyxl
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from app.models import LearningProfileOutput, StudentTarget
from app.services import graduation_case_service, graduation_check_service
from app.services.autobiography_service import OUTPUT_TYPE, latest_draft
from app.services.journey_service import build_journey
from app.services.package_service import latest_review


def _target_progress(student, journey, targets):
    """計算目標校系準備度與待補類別。"""
    from app.routes.teacher import gap_needs
    from app.services.gap_service import analyze_gap, student_evidence
    if not targets:
        return []
    evidence = student_evidence(student, journey)
    rows = []
    for target in targets:
        gap = analyze_gap(student, target.program, journey, evidence)
        rows.append({
            "program": target.program,
            "readiness": gap["readiness"],
            "needs": gap_needs(gap),
            "pending_mapping": any(item["mapping_pending"] or item["fraction"] is None for item in gap["items"]),
        })
    return rows


def _clean_word_count(output):
    """計算自傳草稿之純字元數（排除空白字元與換行）。"""
    if not output or not output.content_json:
        return 0
    paragraphs = output.content_json.get("paragraphs", [])
    total = 0
    for p in paragraphs:
        text = str(p.get("text") or "").strip()
        cleaned = "".join(text.split())
        total += len(cleaned)
    return total


def build_class_overview_rows(students):
    """整理供導師班級總覽表與 Excel 匯出使用的每一筆學生資料。"""
    rows = []
    for student in students:
        journey = build_journey(student)
        targets = StudentTarget.query.filter_by(student_id=student.id).order_by(StudentTarget.selected_at).all()
        target_programs = [target.program for target in targets]
        reviews = [latest_review(student, target.program) for target in targets]

        profile = student.student_profile
        student_no = profile.student_no if profile and profile.student_no else "—"
        class_name = profile.class_name if profile and profile.class_name else "—"
        display_name = student.display_name or "—"

        # 送審校系（多個用「、」）
        if target_programs:
            target_programs_text = "、".join(f"{p.school_name} {p.department_name}" for p in target_programs)
        else:
            target_programs_text = "—"

        # 自傳狀態（未起稿／草稿／已送審／導師請修改／導師已確認，由該學生各目標校系的 latest_draft 與 latest_review 推得；推不出來寫「—」）
        if targets:
            statuses = []
            drafts = []
            for target in targets:
                draft = latest_draft(student, target.program)
                if draft:
                    drafts.append(draft)
                rev = latest_review(student, target.program)
                if rev:
                    if rev.status == "pending":
                        statuses.append("已送審")
                    elif rev.status == "needs_revision":
                        statuses.append("導師請修改")
                    elif rev.status == "confirmed":
                        statuses.append("導師已確認")
                    else:
                        statuses.append("已送審")
                elif draft:
                    statuses.append("草稿")
                else:
                    statuses.append("未起稿")

            if "已送審" in statuses:
                autobiography_status = "已送審"
            elif "導師請修改" in statuses:
                autobiography_status = "導師請修改"
            elif "導師已確認" in statuses:
                autobiography_status = "導師已確認"
            elif "草稿" in statuses:
                autobiography_status = "草稿"
            elif all(s == "未起稿" for s in statuses):
                autobiography_status = "未起稿"
            else:
                autobiography_status = "—"

            if drafts:
                latest_d = max(drafts, key=lambda d: d.id)
                autobiography_words = _clean_word_count(latest_d)
            else:
                autobiography_words = 0
        else:
            draft = (LearningProfileOutput.query.filter_by(student_id=student.id, output_type=OUTPUT_TYPE)
                     .order_by(LearningProfileOutput.id.desc()).first())
            if draft:
                autobiography_status = "草稿"
                autobiography_words = _clean_word_count(draft)
            else:
                autobiography_status = "—"
                autobiography_words = 0

        # 學分缺口或畢業門檻狀態（沿用 graduation_check_service 既有結果，不要自創規則）
        assessment = graduation_check_service.assess(student)
        overall = graduation_check_service.overall_result(assessment)
        if overall == "gap":
            gaps = []
            for key, data in assessment["items"].items():
                if data.get("result") == "gap":
                    item_name = graduation_case_service.ITEM_LABELS.get(key, key)
                    short = data.get("current_amount")
                    unit = data.get("unit", "")
                    if short is not None:
                        gaps.append(f"{item_name}差{short}{unit}")
                    else:
                        gaps.append(f"{item_name}缺口")
            graduation_status = f"有缺口（{'、'.join(gaps)}）" if gaps else graduation_check_service.OVERALL_LABELS["gap"][0]
        else:
            graduation_status = graduation_check_service.OVERALL_LABELS.get(overall, (overall, ""))[0]

        # 證照數
        certificate_count = journey["totals"].get("credential", 0)

        # 待確認送審數
        pending = sum(1 for review in reviews if review and review.status == "pending")

        rows.append({
            "student": student,
            "student_no": student_no,
            "display_name": display_name,
            "class_name": class_name,
            "target_programs_text": target_programs_text,
            "targets": target_programs,
            "target_progress": _target_progress(student, journey, targets),
            "autobiography_status": autobiography_status,
            "autobiography_words": autobiography_words,
            "graduation_status": graduation_status,
            "certificate_count": certificate_count,
            "pending": pending,
            "totals": journey["totals"],
            "missing": len(journey["missing_categories"]),
        })

    return rows


def export_class_overview_xlsx(students):
    """產出導師班級總覽 Excel 檔案（包含班級總覽與統計工作表）。回傳 BytesIO 串流。"""
    wb = openpyxl.Workbook()

    # 工作表 1：「班級總覽」
    ws_overview = wb.active
    ws_overview.title = "班級總覽"

    headers = [
        "學號", "姓名", "班級", "送審校系", "自傳狀態",
        "自傳字數", "學分缺口或畢業門檻狀態", "證照數", "待確認送審數",
    ]
    ws_overview.append(headers)

    header_font = Font(bold=True)
    for col_idx in range(1, len(headers) + 1):
        ws_overview.cell(row=1, column=col_idx).font = header_font

    rows = build_class_overview_rows(students)
    for r in rows:
        ws_overview.append([
            r["student_no"],
            r["display_name"],
            r["class_name"],
            r["target_programs_text"],
            r["autobiography_status"],
            r["autobiography_words"],
            r["graduation_status"],
            r["certificate_count"],
            r["pending"],
        ])

    last_row = max(2, len(rows) + 1)

    # 凍結首列與前兩欄（在 C2 凍結）
    ws_overview.freeze_panes = "C2"

    # 開啟自動篩選
    ws_overview.auto_filter.ref = f"A1:I{last_row}"

    # 適中欄寬
    col_widths = {
        "A": 14,  # 學號
        "B": 12,  # 姓名
        "C": 14,  # 班級
        "D": 36,  # 送審校系
        "E": 16,  # 自傳狀態
        "F": 14,  # 自傳字數
        "G": 32,  # 學分缺口或畢業門檻狀態
        "H": 12,  # 證照數
        "I": 16,  # 待確認送審數
    }
    for col_letter, width in col_widths.items():
        ws_overview.column_dimensions[col_letter].width = width

    # 工作表 2：「統計」
    ws_stats = wb.create_sheet(title="統計")
    ws_stats.append(["項目", "數值"])
    ws_stats.cell(row=1, column=1).font = header_font
    ws_stats.cell(row=1, column=2).font = header_font

    stat_items = [
        ("總人數", f"=COUNTA('班級總覽'!A2:A{last_row})"),
        ("已送審人數", f'=COUNTIF(\'班級總覽\'!E2:E{last_row}, "已送審")'),
        ("平均自傳字數", f"=AVERAGE('班級總覽'!F2:F{last_row})"),
        ("自傳字數標準差", f"=STDEV('班級總覽'!F2:F{last_row})"),
        ("尚未起稿人數", f'=COUNTIF(\'班級總覽\'!E2:E{last_row}, "未起稿")'),
    ]
    for item_name, formula in stat_items:
        ws_stats.append([item_name, formula])

    ws_stats.column_dimensions["A"].width = 20
    ws_stats.column_dimensions["B"].width = 24

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream

"""科主任（含副主任）檢視全年級學生的詳細資料（2026-11-19 使用者決定）。

- 唯讀，只有科主任（`staff_roles.is_chief`）；科助與其他行政人員不行。
- 每次打開學生詳細頁都寫操作紀錄 `staff.student_view`，只記學生編號與看了哪些區塊，不記內容。
- 缺曠只存學期合計；這裡顯示合計，不送外部 AI（規則 2026-11-19 改成：本人、班導、科主任可看）。
"""

from app.extensions import db
from app.models import (CredentialRecord, LearningCourseRecord, SchoolAwardRecord, StudentProfile, StudentTarget,
                        TransferCreditRecord, User)
from app.services import autobiography_service, graduation_case_service, graduation_check_service
from app.services.journey_service import current_grade
from app.services.package_service import latest_review

GRADE_LABELS = {1: "專一", 2: "專二", 3: "專三", 4: "專四", 5: "專五"}
DETAIL_SECTIONS = {
    "learning": ["基本資料", "畢業門檻", "成績", "證照", "缺曠合計", "獎懲"],
    "admissions": ["基本資料", "目標校系與備審", "自傳", "實習履歷"],
}
STATUS_FILTERS = {"gap": "有缺口", "ok": "達標", "check": "待確認"}


def _item_rows(assessment):
    rows = []
    for key, item in (assessment.get("items") or {}).items():
        status = item.get("status")
        rows.append({"key": key, "label": graduation_case_service.ITEM_LABELS.get(key, key), "status": status,
                     "status_label": graduation_check_service.RESULT_LABELS.get(status, str(status)),
                     "reason": item.get("reason") or ""})
    return rows


def graduation_summary(student):
    """回傳 (摘要鍵 gap／ok／check, 缺口項目名稱清單, 各項目列)。"""
    try:
        assessment = graduation_check_service.assess(student)
    except Exception:  # noqa: BLE001  缺資料的學生不要讓整份清單壞掉
        return "check", [], []
    rows = _item_rows(assessment)
    gaps = [row["label"] for row in rows if row["status"] == "short"]
    unknown = [row for row in rows if row["status"] not in ("ok", "short")]
    key = "gap" if gaps else ("check" if unknown else "ok")
    return key, gaps, rows


def students(grade=None, class_name="", query="", status=""):
    """依條件篩選學生，每位附年級、畢業狀態、證照數；已停用的學生不列。"""
    rows = []
    base = (User.query.join(StudentProfile, StudentProfile.user_id == User.id)
            .filter(User.role == "student", User.is_active.is_(True)))
    if class_name:
        base = base.filter(StudentProfile.class_name == class_name)
    for student in base.order_by(StudentProfile.student_no).all():
        profile = student.student_profile
        student_grade = current_grade(profile.admission_year)
        if grade and student_grade != grade:
            continue
        text = f"{profile.student_no} {student.display_name}"
        if query and query.lower() not in text.lower():
            continue
        key, gaps, _ = graduation_summary(student)
        if status and status != key:
            continue

        # 計算目標校系與自傳狀態
        stu_targets = StudentTarget.query.filter_by(student_id=student.id).order_by(StudentTarget.selected_at).all()
        target_count = len(stu_targets)
        if target_count == 0:
            target_summary = "尚未設定"
            bio_status_label = "未開始"
            bio_status_tag = "tag--warn"
        else:
            first_prog = stu_targets[0].program
            target_summary = f"{target_count} 個志願（第 1：{first_prog.school_name} {first_prog.department_name}）"
            all_reviews = [latest_review(student, t.program) for t in stu_targets]
            valid_reviews = [r for r in all_reviews if r is not None]
            if any(r.status == "confirmed" for r in valid_reviews):
                bio_status_label = "已通過"
                bio_status_tag = "tag--ok"
            elif any(r.status == "pending" for r in valid_reviews):
                bio_status_label = "待審閱"
                bio_status_tag = "tag--accent"
            elif any(r.status == "needs_revision" for r in valid_reviews):
                bio_status_label = "請修改"
                bio_status_tag = "tag--danger"
            else:
                has_draft = any(autobiography_service.latest_draft(student, t.program) is not None for t in stu_targets)
                if has_draft:
                    bio_status_label = "草稿中"
                    bio_status_tag = "tag--info"
                else:
                    bio_status_label = "未開始"
                    bio_status_tag = "tag--warn"

        rows.append({
            "student": student, "profile": profile, "grade": student_grade,
            "grade_label": GRADE_LABELS.get(student_grade, "—"),
            "status_key": key, "status_label": STATUS_FILTERS[key], "gaps": gaps,
            "certificates": CredentialRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed").count(),
            "transfer": TransferCreditRecord.query.filter_by(student_id=student.id).first() is not None,
            "target_summary": target_summary,
            "bio_status_label": bio_status_label,
            "bio_status_tag": bio_status_tag,
        })
    return rows


def class_names():
    return sorted({p.class_name for p in StudentProfile.query.all() if p.class_name})


def detail(student, page):
    """載入學生基本資料與目前分頁的唯讀區塊。"""
    profile = student.student_profile
    return {
        "student": student,
        "profile": profile,
        "grade": current_grade(profile.admission_year),
        **(_learning_detail(student) if page == "learning" else _admissions_detail(student)),
    }


def _learning_detail(student):
    from app.models.attendance import AttendanceSummary
    key, gaps, items = graduation_summary(student)
    return {
        "status_key": key, "status_label": STATUS_FILTERS[key], "gaps": gaps, "grad_items": items,
        "courses": (LearningCourseRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed")
                    .order_by(LearningCourseRecord.school_year, LearningCourseRecord.semester).all()),
        "credentials": (CredentialRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed")
                        .order_by(CredentialRecord.id).all()),
        "attendance": (AttendanceSummary.query.filter_by(student_id=student.id)
                       .order_by(AttendanceSummary.school_year, AttendanceSummary.semester).all()),
        "awards": (SchoolAwardRecord.query.filter_by(student_id=student.id)
                   .order_by(SchoolAwardRecord.date, SchoolAwardRecord.id).all()),
        "transfer": TransferCreditRecord.query.filter_by(student_id=student.id).first(),
    }


def _admissions_detail(student):
    from app.models import AutobiographySuggestion, AutobiographyComment
    from app.services import internship_resume_draft
    targets = []
    for target in StudentTarget.query.filter_by(student_id=student.id).order_by(StudentTarget.selected_at).all():
        program = target.program
        review = latest_review(student, program)
        draft = autobiography_service.latest_draft(student, program)
        sugs = AutobiographySuggestion.query.filter_by(student_id=student.id, program_id=program.id).order_by(AutobiographySuggestion.created_at).all()
        comments = AutobiographyComment.query.filter_by(student_id=student.id, program_id=program.id).order_by(AutobiographyComment.created_at).all()
        targets.append({
            "program": program, "review": review,
            "autobiography": ({"version": autobiography_service.version_of(draft),
                               "paragraphs": draft.content_json.get("paragraphs", []),
                               "versions": len(autobiography_service.versions(student, program))} if draft else None),
            "suggestions": sugs,
            "comments": comments,
        })

    # 實習履歷資料
    resume_row = internship_resume_draft.latest_row(student)
    resume_draft = internship_resume_draft.load(student) if resume_row else None
    resume_choices = internship_resume_draft.saved_choices(student) if resume_row else None
    internship_resume_info = None
    if resume_row:
        texts = (resume_choices or {}).get("texts", {})
        bio_sections = [
            {"key": "family", "title": "家庭生活", "text": texts.get("family", "")},
            {"key": "study", "title": "求學經過及社團活動", "text": texts.get("study", "")},
            {"key": "skill", "title": "個人專長及簡要經歷", "text": texts.get("skill", "")},
            {"key": "future", "title": "未來生涯規劃", "text": texts.get("future", "")},
        ]
        internship_resume_info = {
            "period": resume_draft.get("period", ""),
            "email": resume_draft.get("email", ""),
            "phone": resume_draft.get("phone", ""),
            "bio_sections": bio_sections,
            "has_data": bool(resume_draft.get("period") or any(s["text"] for s in bio_sections)),
            "updated_at": resume_row.created_at,
        }

    return {
        "targets": targets,
        "internship_resume": internship_resume_info,
    }

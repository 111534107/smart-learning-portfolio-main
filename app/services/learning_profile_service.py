"""Rule-based, traceable learning-profile output generation."""

from collections import defaultdict

from app.extensions import db
from app.models import (
    CourseRule,
    CredentialRecord,
    LearningCourseRecord,
    LearningProfileOutput,
)


FORMAL_REVIEW_DISCLAIMER = "此結果僅供學習規劃參考，不代表正式畢業審查、學分抵免或錄取結果。"


def _rule_status(record):
    if record is None:
        return "missing"
    return record.acquisition_status


def generate_learning_profile_outputs(student, school_year):
    """Persist four display-ready drafts from student-confirmed records and active rules."""
    rules = CourseRule.query.filter_by(school_year=school_year, is_active=True).order_by(CourseRule.id).all()
    courses = LearningCourseRecord.query.filter_by(
        student_id=student.id, confirmation_status="confirmed"
    ).order_by(LearningCourseRecord.id).all()
    credentials = CredentialRecord.query.filter_by(
        student_id=student.id, confirmation_status="confirmed"
    ).order_by(CredentialRecord.id).all()
    courses_by_name = {course.normalized_course_name: course for course in courses}

    ability_domains = defaultdict(list)
    for rule in rules:
        course = courses_by_name.get(rule.normalized_course_name)
        if rule.ability_domain and course and course.score is not None:
            ability_domains[rule.ability_domain].append(course.score)
    ability_summary = [
        {"name": domain, "average_score": round(sum(scores) / len(scores), 1), "course_count": len(scores)}
        for domain, scores in sorted(ability_domains.items())
    ]

    missing_required_courses = []
    pending_rule_confirmation = []
    makeup_courses = []
    for rule in rules:
        if rule.requirement_type != "required":
            continue
        record = courses_by_name.get(rule.normalized_course_name)
        status = _rule_status(record)
        if status in {"missing", "not_passed", "makeup_record"}:
            missing_required_courses.append(rule.course_name)
        if status == "pending_rule_confirmation":
            pending_rule_confirmation.append(rule.course_name)
        if status == "makeup_record":
            makeup_courses.append(rule.course_name)

    credential_names = [item.credential_name for item in credentials]
    source_snapshot = {
        "school_year": school_year,
        "course_rule_ids": [rule.id for rule in rules],
        "course_record_ids": [course.id for course in courses],
        "credential_ids": [credential.id for credential in credentials],
    }
    output_content = {
        "profile_summary": {
            "student_name": student.display_name,
            "school_year": school_year,
            "ability_domains": ability_summary,
            "credential_names": credential_names,
            "disclaimer": FORMAL_REVIEW_DISCLAIMER,
        },
        "curriculum_gap": {
            "missing_required_courses": missing_required_courses,
            "pending_rule_confirmation": pending_rule_confirmation,
            "makeup_courses": makeup_courses,
            "disclaimer": FORMAL_REVIEW_DISCLAIMER,
        },
        "autobiography": {
            "draft": (
                f"我是{student.display_name}。我已確認並整理自己的課程與證照資料；"
                f"目前可呈現的證照包括：{'、'.join(credential_names) if credential_names else '尚未提供'}。"
                "以下內容應由學生依實際經驗補充與修訂。"
            ),
            "disclaimer": "自傳為草稿，請學生確認後再使用。",
        },
        "study_plan": {
            "draft": (
                "建議依已確認的學習紀錄安排下一階段課程、作品與證照準備；"
                "對於尚未符合或待確認的項目，請先向導師、科辦或課程規則管理者確認。"
            ),
            "disclaimer": FORMAL_REVIEW_DISCLAIMER,
        },
    }
    outputs = {}
    for output_type, content_json in output_content.items():
        output = LearningProfileOutput(
            student_id=student.id,
            output_type=output_type,
            content_json=content_json,
            source_snapshot_json=source_snapshot,
        )
        db.session.add(output)
        outputs[output_type] = output
    db.session.commit()
    return outputs

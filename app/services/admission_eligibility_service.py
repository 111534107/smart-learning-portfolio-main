"""使用已確認的學生資料，比對管理者已確認的招生資格規則。"""

from datetime import date

from app.models import CredentialRecord, Portfolio

LEVEL_RANK = {"丙級": 1, "乙級": 2, "甲級": 3, "特級": 4}
RESULT_MATCHED = "matched"
RESULT_NOT_MATCHED = "not_matched"
RESULT_INSUFFICIENT = "insufficient_data"
RESULT_REVIEW = "needs_review"


def _normalized(text):
    return "".join((text or "").casefold().split())


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _source_for(rule, program):
    url = rule.source_url or program.source_url
    location = rule.source_location
    return {"url": url, "location": location} if url and location else None


def validate_eligibility_condition(condition_type, operator, value):
    """回傳可顯示的驗證錯誤；None 表示此版本可由規則服務判斷。"""
    if not isinstance(value, dict):
        return "資格條件必須是 JSON 物件。"
    if condition_type == "student_status":
        if operator != "in" or set(value) != {"field", "values"}:
            return "學籍條件需使用 in，並提供 field 與 values。"
        field, values = value.get("field"), value.get("values")
        if not isinstance(field, str) or field not in {"class_name", "admission_year"} or not isinstance(values, list) or not values:
            return "學籍欄位或允許值格式不正確。"
        if field == "class_name" and not all(isinstance(item, str) and item.strip() for item in values):
            return "班級允許值必須是非空文字。"
        if field == "admission_year" and not all(
            isinstance(item, int) and not isinstance(item, bool) for item in values
        ):
            return "入學年度允許值必須是整數。"
        return None
    if condition_type == "credential":
        allowed = {"name", "issuer", "min_level", "issue_date_from", "issue_date_to"}
        if operator != "has_credential" or set(value) - allowed:
            return "證照條件需使用 has_credential，且只能包含支援的欄位。"
        name, issuer, minimum_level = value.get("name"), value.get("issuer"), value.get("min_level")
        date_from_text, date_to_text = value.get("issue_date_from"), value.get("issue_date_to")
        date_from = _parse_date(date_from_text) if date_from_text else None
        date_to = _parse_date(date_to_text) if date_to_text else None
        if not any((name, issuer, minimum_level, date_from_text, date_to_text)):
            return "至少要指定證照名稱、發證單位、最低級別或取得日期範圍。"
        if name is not None and (not isinstance(name, str) or not name.strip()):
            return "證照名稱必須是非空文字。"
        if issuer is not None and (not isinstance(issuer, str) or not issuer.strip()):
            return "發證單位必須是非空文字。"
        if minimum_level is not None and (
            not isinstance(minimum_level, str) or minimum_level not in LEVEL_RANK
        ):
            return "目前只支援丙級、乙級、甲級或特級的級別比較。"
        if date_from_text and not date_from or date_to_text and not date_to:
            return "取得日期必須使用 YYYY-MM-DD 格式。"
        if date_from and date_to and date_from > date_to:
            return "取得日期起日不可晚於迄日。"
        return None
    if condition_type == "competition":
        if operator != "has_competition" or value != {"category": "competition"}:
            return "目前只支援比對是否有已確認的競賽經歷；獎項、名次及日期需人工確認。"
        return None
    return "目前不支援此類資格條件。"


def _condition(rule, program, student):
    source = _source_for(rule, program)
    result = {
        "rule_id": rule.id,
        "group": rule.rule_group,
        "required": rule.is_required,
        "description": rule.description,
        "status": RESULT_REVIEW,
        "reason": "資格規則尚未完成確認。",
        "source": source,
    }
    if rule.mapping_status != "confirmed":
        return result
    if not source:
        result["reason"] = "缺少官方來源連結或頁碼／章節位置，無法確認此條件。"
        return result

    value = rule.value_json
    validation_error = validate_eligibility_condition(rule.condition_type, rule.operator, value)
    if validation_error:
        result["reason"] = validation_error
        return result
    if rule.condition_type == "student_status":
        field = value.get("field")
        values = value.get("values")
        profile = student.student_profile
        actual = getattr(profile, field, None) if profile else None
        if actual is None or actual == "":
            result["status"] = RESULT_INSUFFICIENT
            result["reason"] = "學生資料缺少判斷這項學籍條件所需的欄位。"
        elif actual in values:
            result["status"] = RESULT_MATCHED
            result["reason"] = "學生資料符合此項學籍條件。"
        else:
            result["status"] = RESULT_NOT_MATCHED
            result["reason"] = "學生資料不符合此項學籍條件。"
        return result

    if rule.condition_type == "credential":
        name = value.get("name")
        issuer = value.get("issuer")
        minimum_level = value.get("min_level")
        date_from = _parse_date(value.get("issue_date_from")) if value.get("issue_date_from") else None
        date_to = _parse_date(value.get("issue_date_to")) if value.get("issue_date_to") else None
        records = CredentialRecord.query.filter_by(student_id=student.id).all()
        confirmed = [record for record in records if record.confirmation_status == "confirmed"]
        possible_unconfirmed = [record for record in records if record.confirmation_status != "confirmed"]
        unknown_level = False
        missing_field = False
        for record in confirmed:
            if name and _normalized(record.credential_name) != _normalized(name):
                continue
            if issuer:
                if not record.issuing_organization:
                    missing_field = True
                    continue
                if _normalized(record.issuing_organization) != _normalized(issuer):
                    continue
            if minimum_level:
                record_level = LEVEL_RANK.get((record.level or "").strip())
                if record_level is None:
                    unknown_level = True
                    continue
                if record_level < LEVEL_RANK[minimum_level]:
                    continue
            if date_from or date_to:
                if record.issue_date is None:
                    missing_field = True
                    continue
                if date_from and record.issue_date < date_from:
                    continue
                if date_to and record.issue_date > date_to:
                    continue
            result["status"] = RESULT_MATCHED
            result["reason"] = "學生已確認的證照資料符合此項資格條件。"
            return result
        if unknown_level:
            result["reason"] = "學生已有相關證照，但級別不在系統可比較的範圍內。"
        elif missing_field or not confirmed or possible_unconfirmed:
            result["status"] = RESULT_INSUFFICIENT
            result["reason"] = "目前沒有足夠的已確認證照資料可判斷此項條件。"
        else:
            result["status"] = RESULT_NOT_MATCHED
            result["reason"] = "目前已確認的證照資料不符合此項資格條件。"
        return result

    if rule.condition_type == "competition":
        records = Portfolio.query.filter_by(student_id=student.id, category="competition").all()
        confirmed = [record for record in records if record.status == "confirmed"]
        if confirmed:
            result["status"] = RESULT_MATCHED
            result["reason"] = "學生已有確認過的競賽經歷；系統只判斷有無經歷，不能判斷獎項或名次。"
        elif records:
            result["status"] = RESULT_INSUFFICIENT
            result["reason"] = "競賽經歷尚未確認，不能用來判斷資格。"
        else:
            result["status"] = RESULT_INSUFFICIENT
            result["reason"] = "目前沒有已確認的競賽經歷可供判斷。"
        return result

    result["reason"] = "目前不支援這種資格條件類型。"
    return result


def evaluate_program(student, program):
    """回傳一個校系版本的資格狀態、逐條理由及官方來源。"""
    conditions = []
    for rule in program.eligibility_rules:
        conditions.append(_condition(rule, program, student))

    required = [condition for condition in conditions if condition["required"]]
    groups = {}
    for condition in required:
        groups.setdefault(condition["group"], []).append(condition)

    matched_groups = sorted(
        group for group, rows in groups.items()
        if rows and all(row["status"] == RESULT_MATCHED for row in rows)
    )
    if matched_groups:
        status = "eligible"
    elif not groups:
        status = "needs_review"
    else:
        group_has_unknown = any(
            not any(row["status"] == RESULT_NOT_MATCHED for row in rows)
            and any(row["status"] in {RESULT_INSUFFICIENT, RESULT_REVIEW} for row in rows)
            for rows in groups.values()
        )
        if not group_has_unknown:
            status = "not_eligible"
        elif any(
            row["status"] == RESULT_REVIEW
            for rows in groups.values()
            for row in rows
            if not any(member["status"] == RESULT_NOT_MATCHED for member in rows)
        ):
            status = "needs_review"
        else:
            status = "insufficient_data"

    sources = []
    for condition in conditions:
        source = condition["source"]
        if source and source not in sources:
            sources.append(source)
    return {
        "program_code": program.program_code,
        "admission_year": program.admission_year,
        "status": status,
        "matched_groups": matched_groups,
        "conditions": conditions,
        "sources": sources,
    }

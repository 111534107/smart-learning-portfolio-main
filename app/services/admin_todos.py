"""管理員首頁「今天要處理什麼」：只統計系統裡已經存在的資料，每一項都連到既有的處理頁。

規格「四、管理員」：核准或駁回 AI 擷取的候選更新、資料來源維護（失效標紅）、核對資料分類、
指派導師；另外把 OCR 失敗與雲端儲存斷線列出來，管理員才知道要檢查設定。
"""
from datetime import datetime, timedelta, timezone

from flask import current_app, url_for
from sqlalchemy import func

from app.extensions import db
from app.models import (
    AdmissionEligibilityRule,
    AdmissionProgram,
    AdmissionRequirementItem,
    AdmissionScheduleEvent,
    AgentTask,
    ClassAdvisor,
    DocumentExtraction,
    PublicSource,
    PublicSourceChange,
    StudentProfile,
    User,
)

OCR_FAILURE_DAYS = 7


def failed_source_ids():
    """網址來源中，最近一次「檢查來源」失敗的來源編號（網址可能失效，畫面標紅）。"""
    latest = (db.session.query(AgentTask.target_id, func.max(AgentTask.id))
              .filter(AgentTask.task_type == "admission_source_check", AgentTask.target_type == "public_source")
              .group_by(AgentTask.target_id).all())
    task_ids = [task_id for _, task_id in latest]
    if not task_ids:
        return set()
    failed = {task.target_id for task in AgentTask.query.filter(AgentTask.id.in_(task_ids), AgentTask.status == "failed")}
    url_ids = {row.id for row in PublicSource.query.filter_by(source_type="url", is_active=True)}
    return failed & url_ids


def classes_without_advisor():
    """有啟用學生、但還沒有任何導師負責的班級。"""
    names = {name for (name,) in db.session.query(StudentProfile.class_name)
             .join(User, StudentProfile.user_id == User.id)
             .filter(User.is_active.is_(True), StudentProfile.class_name.isnot(None), StudentProfile.class_name != "")}
    covered = {name for (name,) in db.session.query(ClassAdvisor.class_name).distinct()}
    return sorted(names - covered)


def _drive_disconnected():
    from app.services import storage_service
    app = current_app._get_current_object()
    if not storage_service.wants_drive(app.config):
        return False
    return not (storage_service.configured(app.config) and storage_service.token_holder(app).connected)


def _curriculum_pending():
    from app.services.curriculum_agent_service import pending_count
    return pending_count()


def admin_todos():
    """回傳待辦卡清單；每張卡：key、label（標題）、count、hint（說明）、href（處理頁）。"""
    since = datetime.now(timezone.utc) - timedelta(days=OCR_FAILURE_DAYS)
    schedule_groups = (db.session.query(AdmissionScheduleEvent.channel, AdmissionScheduleEvent.admission_year)
                       .filter_by(status="candidate").distinct().count())
    pending_mapping = (AdmissionRequirementItem.query.filter_by(mapping_status="pending").count()
                       + AdmissionEligibilityRule.query.filter_by(mapping_status="pending").count())
    todos = [
        {"key": "candidate-programs", "label": "候選校系待核准",
         "count": AdmissionProgram.query.filter_by(status="candidate").count(),
         "hint": "Agent 擷取或手動建立的候選版本，核准後學生才看得到", "href": url_for("admin.programs")},
        {"key": "candidate-schedules", "label": "候選招生日程待核准", "count": schedule_groups,
         "hint": "以「一個管道、一個學年度」為一組，對照原文後核准或退回",
         "href": url_for("admin.agent_home") + "#candidate-schedules"},
        {"key": "pending-changes", "label": "簡章更新待擷取",
         "count": PublicSourceChange.query.filter(PublicSourceChange.status != "extracted").count(),
         "hint": "官方來源有新內容，還沒擷取成候選校系", "href": url_for("admin.agent_home") + "#source-changes"},
        {"key": "failed-sources", "label": "資料來源檢查失敗", "count": len(failed_source_ids()),
         "hint": "最近一次抓取失敗，網址可能失效，請更新或改用上傳", "href": url_for("admin.agent_home") + "#public-sources"},
        {"key": "pending-mapping", "label": "資料分類待核對", "count": pending_mapping,
         "hint": "簡章評分項目、報考資格還沒確認對應到哪一類資料", "href": url_for("admin.programs")},
        {"key": "curriculum", "label": "修業科目表待確認", "count": _curriculum_pending(),
         "hint": "代理從資管科網頁抓到新版本或檢查不通過，確認後畢業門檻才會使用",
         "href": url_for("admin.curriculum_home")},
        {"key": "classes-without-advisor", "label": "班級還沒指派導師", "count": len(classes_without_advisor()),
         "hint": "有學生的班級還沒有導師負責", "href": url_for("admin.classes")},
        {"key": "ocr-failures", "label": f"近 {OCR_FAILURE_DAYS} 天 OCR 辨識失敗",
         "count": DocumentExtraction.query.filter(DocumentExtraction.status == "failed",
                                                   DocumentExtraction.updated_at >= since.replace(tzinfo=None)).count(),
         "hint": "學生上傳的成績單或證照沒辨識成功；連續失敗請檢查辨識設定", "href": url_for("admin.ocr_settings_page")},
    ]
    if _drive_disconnected():
        todos.append({"key": "storage-disconnected", "label": "雲端儲存未連線", "count": 1,
                      "hint": "設定要存到 Google 雲端硬碟，但目前沒有連線，檔案暫存本機",
                      "href": url_for("storage.settings_page")})
    return todos

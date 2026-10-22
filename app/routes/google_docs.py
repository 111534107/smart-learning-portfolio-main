"""自傳在 Google 文件中編輯（示範版）：Google 授權、建立／開啟文件、取回成新版本。

Google 任何一步失敗都只回到自傳頁顯示提示，學生仍可在系統內編輯；送導師確認一樣用系統內的版本快照。
"""
from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, redirect, request, session, url_for

from app.extensions import db
from app.models import AdmissionProgram, AutobiographyGoogleDoc, LearningProfileOutput
from app.routes.main import get_current_user, role_required
from app.services import autobiography_service, google_docs_service as gdocs

google_docs_bp = Blueprint("google_docs", __name__)

# 自傳頁上方的提示（網址參數 google=…）
MESSAGES = {
    "unconfigured": ("warn", "Google 尚未設定，請先在系統內編輯。"),
    "connected": ("ok", "已連上你的 Google 帳號（只授權本系統建立的文件），可以按「在 Google 文件中編輯」。"),
    "denied": ("warn", "沒有完成 Google 授權，請先在系統內編輯；要用 Google 文件時再按一次。"),
    "expired": ("warn", "Google 授權已過期，請重新連結 Google；這段期間可以先在系統內編輯。"),
    "unavailable": ("warn", "Google 暫時無法使用，請先在系統內編輯，稍後再試。你的自傳都還在系統裡。"),
    "no_doc": ("warn", "還沒有建立 Google 文件，請先按「在 Google 文件中編輯」。"),
    "no_titles": ("warn", "取回失敗：Google 文件裡找不到「## 標題」開頭的段落，請保留每段的標題行再取回。系統內的版本沒有變。"),
    "pulled": ("ok", "已從 Google 文件取回，存成新的一版（舊版不動）。請檢查下面每段的來源提示。"),
}

TOKEN_REF = "google_docs_token_ref"
STATE = "google_oauth_state"
PENDING_PROGRAM = "google_oauth_program"


def _back(program_id, status):
    return redirect(url_for("student.autobiography", program_id=program_id, google=status))


def _owned_draft_or_abort(user, output_id):
    output = db.session.get(LearningProfileOutput, output_id)
    if not output or output.output_type != autobiography_service.OUTPUT_TYPE:
        abort(404)
    if output.student_id != user.id:
        abort(403)
    return output


def _token(user):
    return gdocs.token_store(current_app).get(session.get(TOKEN_REF), user.id)


def _forget_token():
    gdocs.token_store(current_app).drop(session.pop(TOKEN_REF, None))


def _ask_for_authorization(program_id):
    session[PENDING_PROGRAM] = program_id
    return redirect(url_for("google_docs.connect"))


@google_docs_bp.app_template_global()
def google_docs_panel(user, program):
    """自傳頁的 Google 文件區塊要顯示什麼。"""
    link = (AutobiographyGoogleDoc.query.filter_by(student_id=user.id, program_id=program.id).first()
            if user and program else None)
    based_on = db.session.get(LearningProfileOutput, link.based_on_output_id) if link else None
    return {
        "configured": gdocs.configured(current_app.config),
        "authorized": bool(user and _token(user)),
        "link": link,
        "based_on_version": autobiography_service.version_of(based_on) if based_on else None,
        "message": MESSAGES.get(request.args.get("google", "")),
    }


@google_docs_bp.get("/student/google/connect")
@role_required("student")
def connect():
    program_id = request.args.get("program_id", type=int) or session.get(PENDING_PROGRAM)
    if program_id:
        session[PENDING_PROGRAM] = program_id
    if not gdocs.configured(current_app.config):
        return _back(program_id, "unconfigured")
    session[STATE] = gdocs.new_state()
    return redirect(gdocs.authorization_url(current_app.config, session[STATE]))


@google_docs_bp.get("/student/google/callback")
@role_required("student")
def callback():
    user = get_current_user()
    expected = session.pop(STATE, None)
    if not expected or request.args.get("state") != expected:
        abort(400, description="Google 授權狀態不符，請回到自傳頁重新連結。")
    program_id = session.pop(PENDING_PROGRAM, None)
    code = request.args.get("code")
    if request.args.get("error") or not code:
        return _back(program_id, "denied")
    try:
        token = gdocs.client_for(current_app).exchange_code(code)
    except gdocs.GoogleDocsAuthExpired:
        return _back(program_id, "denied")
    except gdocs.GoogleDocsError:
        return _back(program_id, "unavailable")
    _forget_token()
    session[TOKEN_REF] = gdocs.token_store(current_app).put(user.id, token["access_token"], token.get("expires_in"))
    return _back(program_id, "connected")


@google_docs_bp.post("/student/google/disconnect")
@role_required("student")
def disconnect():
    _forget_token()
    return _back(request.form.get("program_id", type=int), None)


@google_docs_bp.post("/student/autobiography/<int:output_id>/google/open")
@role_required("student")
def open_document(output_id):
    user = get_current_user()
    output = _owned_draft_or_abort(user, output_id)
    program_id = output.content_json["program_id"]
    if not gdocs.configured(current_app.config):
        return _back(program_id, "unconfigured")
    link = AutobiographyGoogleDoc.query.filter_by(student_id=user.id, program_id=program_id).first()
    if link:
        return redirect(link.web_view_link)
    token = _token(user)
    if not token:
        return _ask_for_authorization(program_id)
    draft = autobiography_service.latest_draft(user, db.session.get(AdmissionProgram, program_id)) or output
    program = db.session.get(AdmissionProgram, program_id)
    label = f"{program.school_name} {program.department_name}"
    text = gdocs.document_text(label, autobiography_service.version_of(draft), draft.content_json.get("paragraphs", []))
    try:
        file_id = gdocs.client_for(current_app).create_document(token, f"自傳草稿－{label}", text)
        web_view_link = gdocs.doc_link(file_id)
    except gdocs.GoogleDocsAuthExpired:
        _forget_token()
        return _back(program_id, "expired")
    except gdocs.GoogleDocsError:
        return _back(program_id, "unavailable")
    db.session.add(AutobiographyGoogleDoc(student_id=user.id, program_id=program_id, google_file_id=file_id,
                                          web_view_link=web_view_link, based_on_output_id=draft.id))
    db.session.commit()
    return redirect(web_view_link)


@google_docs_bp.post("/student/autobiography/<int:output_id>/google/pull")
@role_required("student")
def pull_document(output_id):
    user = get_current_user()
    output = _owned_draft_or_abort(user, output_id)
    program_id = output.content_json["program_id"]
    if not gdocs.configured(current_app.config):
        return _back(program_id, "unconfigured")
    link = AutobiographyGoogleDoc.query.filter_by(student_id=user.id, program_id=program_id).first()
    if not link:
        return _back(program_id, "no_doc")
    token = _token(user)
    if not token:
        return _ask_for_authorization(program_id)
    try:
        text = gdocs.client_for(current_app).export_text(token, link.google_file_id)
    except gdocs.GoogleDocsAuthExpired:
        _forget_token()
        return _back(program_id, "expired")
    except gdocs.GoogleDocsError:
        return _back(program_id, "unavailable")
    paragraphs = gdocs.parse_document_text(text)
    if not paragraphs:
        return _back(program_id, "no_titles")
    latest = autobiography_service.latest_draft(user, db.session.get(AdmissionProgram, program_id)) or output
    checked = gdocs.check_sources(paragraphs, latest.content_json.get("facts", []))
    new_version = autobiography_service.save_imported(latest, checked, user, origin="google_docs")
    link.last_pulled_at = datetime.now(timezone.utc)
    link.last_pulled_output_id = new_version.id
    db.session.commit()
    return _back(program_id, "pulled")

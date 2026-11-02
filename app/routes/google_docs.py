"""自傳在 Google 文件中編輯（示範版）：Google 授權、建立／開啟文件、取回成新版本。

Google 任何一步失敗都只回到自傳頁顯示提示，學生仍可在系統內編輯；送導師確認一樣用系統內的版本快照。
"""
from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, redirect, request, session, url_for

from app.extensions import db
from app.models import AdmissionProgram, AutobiographyGoogleDoc, LearningProfileOutput, StudentDriveFolder
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
    "doc_gone": ("warn", "Google 文件找不到了，請按『在 Google 文件中編輯』重建一份。"),
    "no_doc": ("warn", "還沒有建立 Google 文件，請先按「在 Google 文件中編輯」。"),
    "no_titles": ("warn", "取回失敗：Google 文件裡找不到「## 標題」開頭的段落，請保留每段的標題行再取回。系統內的版本沒有變。"),
    "pulled": ("ok", "已從 Google 文件取回，存成新的一版（舊版不動）。請檢查下面每段的來源提示。"),
}

TOKEN_REF = "google_docs_token_ref"
STATE = "google_oauth_state"
PENDING_PROGRAM = "google_oauth_program"
PENDING_OPEN = "google_oauth_open_output"  # 按「在 Google 文件中編輯」才去授權的話，授權完直接建立文件


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
    pending_output = session.pop(PENDING_OPEN, None)  # 授權失敗也要清掉，免得下次連線意外建立文件
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
    if pending_output:
        # 11-02 實測：授權完還要再按一次才會建立文件，學生以為已經好了。這裡直接接著建立
        output = _owned_draft_or_abort(user, pending_output)
        existing = AutobiographyGoogleDoc.query.filter_by(student_id=user.id, program_id=output.content_json["program_id"]).first()
        return _open_or_create(user, output, output.content_json["program_id"], token["access_token"], existing)
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
    token = _token(user)
    if not token:
        if link:
            return redirect(link.web_view_link)
        session[PENDING_OPEN] = output_id
        return _ask_for_authorization(program_id)
    return _open_or_create(user, output, program_id, token, link)


def _open_or_create(user, output, program_id, token, link):
    if link:
        try:
            if gdocs.client_for(current_app).file_usable(token, link.google_file_id):
                return redirect(link.web_view_link)
        except gdocs.GoogleDocsError:
            return redirect(link.web_view_link)
    return _create_document(user, output, program_id, token, link)


def _drive_folder_id(user, folder_key, name, parent_id, token):
    """找出或建立一個資料夾：編號記在資料庫，只建一次，之後重用。

    重用前先問 Google 還在不在：學生把資料夾刪掉或丟進垃圾桶，就重建一個並更新編號。
    """
    client = gdocs.client_for(current_app)
    saved = StudentDriveFolder.query.filter_by(student_id=user.id, folder_key=folder_key).first()
    if saved and client.file_usable(token, saved.google_folder_id):
        return saved.google_folder_id
    folder_id = client.create_folder(token, name, parent_id)
    if saved:
        saved.google_folder_id = folder_id
    else:
        db.session.add(StudentDriveFolder(student_id=user.id, folder_key=folder_key, google_folder_id=folder_id))
    db.session.commit()
    return folder_id


def _school_folder_id(user, program, token):
    """學生雲端硬碟的「備審資料／校名_科系」，回傳該校系資料夾的編號。"""
    root_id = _drive_folder_id(user, "root", "備審資料", None, token)
    school_name = f"{program.school_name}_{program.department_name}".replace("/", "／")
    return _drive_folder_id(user, f"program:{program.id}", school_name, root_id, token)


def _create_document(user, output, program_id, token, existing=None):
    """把最新草稿建立成學生自己的 Google 文件（放進「備審資料／校名_科系」），記下連結後轉過去。"""
    draft = autobiography_service.latest_draft(user, db.session.get(AdmissionProgram, program_id)) or output
    program = db.session.get(AdmissionProgram, program_id)
    label = f"{program.school_name} {program.department_name}"
    text = gdocs.document_text(label, autobiography_service.version_of(draft), draft.content_json.get("paragraphs", []))
    try:
        folder_id = _school_folder_id(user, program, token)
        file_id = gdocs.client_for(current_app).create_document(token, f"自傳草稿－{label}", text, folder_id=folder_id)
        web_view_link = gdocs.doc_link(file_id)
    except gdocs.GoogleDocsAuthExpired:
        _forget_token()
        return _back(program_id, "expired")
    except gdocs.GoogleDocsError:
        return _back(program_id, "unavailable")
    if existing:
        existing.google_file_id = file_id
        existing.web_view_link = web_view_link
        existing.based_on_output_id = draft.id
        existing.created_at = datetime.now(timezone.utc)
        existing.last_pulled_at = None
        existing.last_pulled_output_id = None
    else:
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
    except gdocs.GoogleDocsNotFound:
        return _back(program_id, "doc_gone")
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

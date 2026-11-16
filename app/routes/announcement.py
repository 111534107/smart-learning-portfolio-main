"""二技公告（UC-25）頁面：學生、導師、科辦閱讀；導師提醒；管理員擬稿、發布、下架。

規則都在 services/announcement_service.py。截止日只從 Agent 核准的日程帶出，這裡沒有任何輸入日期的欄位。
"""
from flask import Blueprint, abort, redirect, render_template, request, url_for

from app.extensions import db
from app.models import Announcement
from app.routes.main import get_current_user, role_required
from app.services import announcement_service as service

announcement_bp = Blueprint("announcement", __name__)


@announcement_bp.app_context_processor
def _home_helpers():
    """首頁用 {% include "partials/announcement_home.html" %} 取最新公告與科辦截止卡，不必改各首頁的路由函式。"""
    return {"announcement_home": service.home_summary}


def _readable_or_404(announcement_id, user):
    announcement = db.session.get(Announcement, announcement_id)
    if not service.can_read(user, announcement):
        abort(404)
    return announcement


@announcement_bp.get("/announcements")
@role_required("student", "teacher", "staff")
def index():
    user = get_current_user()
    rows = service.visible_for(user)
    return render_template("announcements.html", user=user, rows=rows, unread=service.unread_ids(user, rows))


@announcement_bp.get("/announcements/<int:announcement_id>")
@role_required("student", "teacher", "staff")
def detail(announcement_id):
    user = get_current_user()
    announcement = _readable_or_404(announcement_id, user)
    service.mark_read(announcement, user)
    targets = service.teacher_targets(user) if user.role == "teacher" else None
    return render_template("announcement_detail.html", user=user, announcement=announcement,
                           dates=service.key_dates(announcement), targets=targets,
                           message=request.args.get("message"))


@announcement_bp.post("/announcements/<int:announcement_id>/remind")
@role_required("teacher")
def remind(announcement_id):
    """導師按「提醒這些學生」：自己班上四、五年級的學生各收到一則站內通知，寫進操作紀錄。"""
    user = get_current_user()
    announcement = _readable_or_404(announcement_id, user)
    try:
        count = service.remind_students(announcement, user)
    except ValueError as exc:
        abort(400, description=str(exc))
    return redirect(url_for("announcement.detail", announcement_id=announcement.id, message=f"已提醒 {count} 位學生"))


# ---- 管理員 ----

def _announcement_or_404(announcement_id):
    announcement = db.session.get(Announcement, announcement_id)
    if announcement is None:
        abort(404)
    return announcement


def _form_values():
    return (request.form.get("title", "").strip(), request.form.get("body", "").strip(),
            [role for role in service.READER_ROLES if role in request.form.getlist("audience")])


@announcement_bp.get("/admin/announcements")
@role_required("admin")
def admin_list():
    rows = Announcement.query.order_by(Announcement.created_at.desc(), Announcement.id.desc()).all()
    groups = {status: [row for row in rows if row.status == status] for status in ("draft", "published", "withdrawn")}
    return render_template("admin_announcements.html", user=get_current_user(), groups=groups,
                           message=request.args.get("message"), error=request.args.get("error"))


@announcement_bp.route("/admin/announcements/new", methods=["GET", "POST"])
@role_required("admin")
def admin_new():
    user = get_current_user()
    if request.method == "POST":
        title, body, audience = _form_values()
        try:
            announcement = service.create_manual(title, body, audience, user)
        except ValueError as exc:
            return render_template("admin_announcement_form.html", user=user, announcement=None, error=str(exc),
                                   values={"title": title, "body": body, "audience": audience})
        return redirect(url_for("announcement.admin_edit", announcement_id=announcement.id))
    return render_template("admin_announcement_form.html", user=user, announcement=None,
                           values={"title": "", "body": "", "audience": list(service.READER_ROLES)})


@announcement_bp.route("/admin/announcements/<int:announcement_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def admin_edit(announcement_id):
    """只能改草稿。截止日由已核准的日程帶出，這裡沒有日期欄位（11-09 使用者決定）。"""
    user = get_current_user()
    announcement = _announcement_or_404(announcement_id)
    if announcement.status != "draft":
        return redirect(url_for("announcement.admin_list", error="已發布或已下架的公告不能再修改"))
    if request.method == "POST":
        title, body, audience = _form_values()
        if not title or not audience:
            return render_template("admin_announcement_form.html", user=user, announcement=announcement,
                                   error="標題和對象都要填", values={"title": title, "body": body, "audience": audience},
                                   dates=service.key_dates(announcement))
        announcement.title, announcement.body, announcement.audience = title, body, ",".join(audience)
        db.session.commit()
        if request.form.get("action") == "publish":
            count = service.publish(announcement, user)
            return redirect(url_for("announcement.admin_list", message=f"已發布「{title}」，通知 {count} 人"))
        return redirect(url_for("announcement.admin_list", message=f"已存草稿「{title}」"))
    return render_template("admin_announcement_form.html", user=user, announcement=announcement,
                           values={"title": announcement.title, "body": announcement.body,
                                   "audience": sorted(announcement.audience_roles)},
                           dates=service.key_dates(announcement), message=request.args.get("message"))


@announcement_bp.post("/admin/announcements/<int:announcement_id>/withdraw")
@role_required("admin")
def admin_withdraw(announcement_id):
    announcement = _announcement_or_404(announcement_id)
    try:
        service.withdraw(announcement, get_current_user())
    except ValueError as exc:
        return redirect(url_for("announcement.admin_list", error=str(exc)))
    return redirect(url_for("announcement.admin_list", message=f"已下架「{announcement.title}」"))

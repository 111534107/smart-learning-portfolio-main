"""表單下載區（UC-28／F-53）：學生與老師 /forms 下載；科辦 /staff/forms 管理分類、上架、改版、下架。

規則都在 services/form_library_service.py；收件功能 2026-10-09 暫停，這裡沒有。
"""
from flask import Blueprint, abort, redirect, render_template, request, send_file, url_for

from app.extensions import db
from app.models import FormCategory, FormItem, FormItemVersion
from app.routes.main import get_current_user, role_required
from app.services import audit_service, storage_service
from app.services import form_library_service as service

forms_bp = Blueprint("forms", __name__)


def _send(version):
    path = storage_service.local_path_or_none(version.file_path)
    if path is None:
        abort(404)
    response = send_file(path.resolve(), as_attachment=True, download_name=version.original_filename)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _item_or_404(item_id):
    item = db.session.get(FormItem, item_id)
    if not item:
        abort(404)
    return item


# ---------- 學生與老師 ----------

@forms_bp.get("/forms")
@role_required("student", "teacher")
def form_list():
    user = get_current_user()
    q = request.args.get("q", "").strip()
    return render_template("forms_list.html", user=user, groups=service.visible_items(user, q), q=q,
                           extension=lambda name: name.rsplit(".", 1)[-1].upper() if "." in name else "")


@forms_bp.get("/forms/<int:item_id>/download")
@role_required("student", "teacher", "staff")
def form_download(item_id):
    item = _item_or_404(item_id)
    if not service.can_download(get_current_user(), item):
        abort(403)
    if not item.latest_version:
        abort(404)
    return _send(item.latest_version)


# ---------- 科辦 ----------

def _audience(form):
    return bool(form.get("open_to_students")), bool(form.get("open_to_teachers"))


def _category_from(form):
    try:
        category = db.session.get(FormCategory, int(form.get("category_id", "")))
    except ValueError:
        category = None
    return category


def _render_manage(error=None, status=200, form=None):
    categories = FormCategory.query.order_by(FormCategory.sort_order, FormCategory.name).all()
    return render_template("staff_forms.html", user=get_current_user(), categories=categories,
                           error=error, form=form or {}, broken_links=service.broken_link_count(),
                           link_labels=service.LINK_STATUS_LABELS), status


# ---------- 學校網站連結檢查（科辦與管理員） ----------

@forms_bp.get("/staff/forms/links")
@role_required("staff", "admin")
def staff_links():
    items = service.linked_items()
    return render_template("staff_form_links.html", user=get_current_user(), items=items,
                           link_labels=service.LINK_STATUS_LABELS, timeout=service.LINK_TIMEOUT_SECONDS,
                           broken=[item for item in items if item.link_status == "broken"])


@forms_bp.post("/staff/forms/links/check")
@role_required("staff", "admin")
def staff_links_check():
    """按「檢查連結」才連線；每個連結有逾時，只記狀態碼。"""
    summary = service.check_all_links()
    audit_service.record(get_current_user(), "form.check_links", detail=summary)
    db.session.commit()
    return redirect(url_for("forms.staff_links"))


@forms_bp.get("/staff/forms")
@role_required("staff")
def staff_forms():
    return _render_manage()


@forms_bp.post("/staff/forms")
@role_required("staff")
def staff_publish():
    user = get_current_user()
    form = request.form
    category = _category_from(form)
    title = form.get("title", "").strip()[:100]
    students, teachers = _audience(form)
    uploaded = request.files.get("file")
    if not category:
        return _render_manage("請選擇分類；還沒有分類時先在下方新增。", 400, form)
    if not title:
        return _render_manage("請填表單名稱。", 400, form)
    if not (students or teachers):
        return _render_manage("請至少勾選一個開放對象（學生或老師）。", 400, form)
    has_file = bool(uploaded and uploaded.filename)
    try:
        source_url = service.clean_url(form.get("source_url"))
    except service.LinkRejected as error:
        return _render_manage(str(error), 400, form)
    if not has_file and not source_url:
        return _render_manage("請選擇要上架的檔案，或填學校網站連結（至少要有一個）。", 400, form)
    item = FormItem(category=category, title=title, description=form.get("description", "").strip() or None,
                    open_to_students=students, open_to_teachers=teachers, is_published=True,
                    created_by_id=user.id, source_url=source_url)
    db.session.add(item)
    db.session.flush()
    try:
        if has_file:
            service.add_version(item, uploaded.filename, uploaded.read(), user)
    except service.UploadRejected as error:
        db.session.rollback()
        return _render_manage(str(error), 400, form)
    audit_service.record(user, "form.publish", "form_item", item.id)
    db.session.commit()
    return redirect(url_for("forms.staff_detail", item_id=item.id))


@forms_bp.post("/staff/forms/categories")
@role_required("staff")
def staff_category_create():
    name = request.form.get("name", "").strip()[:50]
    if not name:
        return _render_manage("請填分類名稱。", 400)
    if FormCategory.query.filter_by(name=name).first():
        return _render_manage(f"已經有「{name}」這個分類。", 400)
    category = FormCategory(name=name, sort_order=_int(request.form.get("sort_order"), 0), is_active=True)
    db.session.add(category)
    db.session.flush()
    audit_service.record(get_current_user(), "form_category.create", "form_category", category.id)
    db.session.commit()
    return redirect(url_for("forms.staff_forms") + "#categories")


@forms_bp.post("/staff/forms/categories/<int:category_id>")
@role_required("staff")
def staff_category_update(category_id):
    category = db.session.get(FormCategory, category_id)
    if not category:
        abort(404)
    name = request.form.get("name", "").strip()[:50]
    if not name:
        return _render_manage("分類名稱不能空白。", 400)
    duplicate = FormCategory.query.filter(FormCategory.name == name, FormCategory.id != category.id).first()
    if duplicate:
        return _render_manage(f"已經有「{name}」這個分類。", 400)
    category.name = name
    category.sort_order = _int(request.form.get("sort_order"), category.sort_order)
    category.is_active = bool(request.form.get("is_active"))
    audit_service.record(get_current_user(), "form_category.update", "form_category", category.id,
                         detail={"is_active": category.is_active})
    db.session.commit()
    return redirect(url_for("forms.staff_forms") + "#categories")


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _render_detail(item, error=None, status=200):
    categories = FormCategory.query.order_by(FormCategory.sort_order, FormCategory.name).all()
    return render_template("staff_form_detail.html", user=get_current_user(), item=item,
                           categories=categories, error=error, link_labels=service.LINK_STATUS_LABELS), status


@forms_bp.get("/staff/forms/<int:item_id>")
@role_required("staff")
def staff_detail(item_id):
    return _render_detail(_item_or_404(item_id))


@forms_bp.post("/staff/forms/<int:item_id>")
@role_required("staff")
def staff_update(item_id):
    item = _item_or_404(item_id)
    form = request.form
    category = _category_from(form)
    title = form.get("title", "").strip()[:100]
    students, teachers = _audience(form)
    if not category or not title:
        return _render_detail(item, "分類與名稱都要填。", 400)
    if not (students or teachers):
        return _render_detail(item, "請至少勾選一個開放對象（學生或老師）。", 400)
    try:
        new_url = service.clean_url(form.get("source_url"))
    except service.LinkRejected as error:
        return _render_detail(item, str(error), 400)
    if not new_url and not item.latest_version:
        return _render_detail(item, "這份表單沒有檔案，連結不能清空；要拿掉連結請先上傳檔案。", 400)
    service.set_source_url(item, new_url)
    item.category, item.title = category, title
    item.description = form.get("description", "").strip() or None
    item.open_to_students, item.open_to_teachers = students, teachers
    audit_service.record(get_current_user(), "form.update", "form_item", item.id)
    db.session.commit()
    return redirect(url_for("forms.staff_detail", item_id=item.id))


@forms_bp.post("/staff/forms/<int:item_id>/versions")
@role_required("staff")
def staff_new_version(item_id):
    item = _item_or_404(item_id)
    user = get_current_user()
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return _render_detail(item, "請選擇新版本的檔案。", 400)
    try:
        version = service.add_version(item, uploaded.filename, uploaded.read(), user, note=request.form.get("note", ""))
    except service.UploadRejected as error:
        db.session.rollback()
        return _render_detail(_item_or_404(item_id), str(error), 400)
    audit_service.record(user, "form.new_version", "form_item", item.id, detail={"version_no": version.version_no})
    db.session.commit()
    return redirect(url_for("forms.staff_detail", item_id=item.id))


@forms_bp.post("/staff/forms/<int:item_id>/publish")
@role_required("staff")
def staff_toggle_publish(item_id):
    item = _item_or_404(item_id)
    action = request.form.get("action")
    if action not in ("unpublish", "republish"):
        abort(400)
    item.is_published = action == "republish"
    audit_service.record(get_current_user(), f"form.{action}", "form_item", item.id)
    db.session.commit()
    return redirect(url_for("forms.staff_detail", item_id=item.id))


@forms_bp.get("/staff/forms/versions/<int:version_id>/download")
@role_required("staff")
def staff_version_download(version_id):
    version = db.session.get(FormItemVersion, version_id)
    if not version:
        abort(404)
    return _send(version)

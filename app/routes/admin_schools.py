"""管理員維護學校名錄（2026-11-13）：學生端「依地區找學校」的地圖、地區按鈕與學校卡片都讀這裡的資料。

維護方式：
1. 逐筆改：每所學校的地區、縣市、座標、官網、招生網站；每個科系的介紹網址。
2. 整批改：匯出 CSV（Excel 打得開）→ 改好 → 匯入；同名學校會更新，不會刪除沒列到的學校。
3. 檢查連結：一次檢查所有網址，失效的列出來。
4. 載入預設資料：第一次用或資料亂掉時，匯入專案附的預設資料（2026-11-13 查過的版本）。
"""
from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for

from app.extensions import db
from app.models import AdmissionProgram, School, SchoolDepartmentLink
from app.routes.main import get_current_user, role_required
from app.services import audit_service, school_directory as directory

admin_schools_bp = Blueprint("admin_schools", __name__)
MAX_CSV_BYTES = 512 * 1024


def _render(problems=None, checked=None, error=None, status=200):
    schools = School.query.order_by(School.region, School.name).all()
    known = {s.name for s in schools}
    program_pairs = sorted({(p.school_name, p.department_name) for p in AdmissionProgram.query.all()})
    missing_schools = sorted({name for name, _ in program_pairs if name not in known})
    linked = {(link.school.name, link.department_name) for link in SchoolDepartmentLink.query.all()}
    missing_departments = [pair for pair in program_pairs if pair[0] in known and pair not in linked]
    return render_template("admin_schools.html", user=get_current_user(), schools=schools, regions=directory.REGIONS,
                           missing_schools=missing_schools, missing_departments=missing_departments,
                           problems=problems, checked=checked, error=error), status


@admin_schools_bp.get("/admin/schools")
@role_required("admin")
def schools_page():
    return _render()


@admin_schools_bp.post("/admin/schools/<int:school_id>")
@role_required("admin")
def school_update(school_id):
    school = db.session.get(School, school_id)
    if not school:
        abort(404)
    form = request.form
    row = {"學校": school.name, "地區": form.get("region", ""), "縣市": form.get("city", ""), "緯度": form.get("latitude", ""),
           "經度": form.get("longitude", ""), "官網": form.get("website_url", ""), "招生網站": form.get("admission_url", ""),
           "確認日期": form.get("checked_on", "")}
    try:  # 和匯入走同一套檢查，規則只寫一次
        directory.import_schools(",".join(directory.CSV_COLUMNS) + "\n" + _csv_line(row))
    except directory.ImportRejected as error:
        db.session.rollback()
        return _render(error=str(error).replace("第 2 列", school.name), status=400)
    audit_service.record(get_current_user(), "school.update", "school", school.id)
    db.session.commit()
    flash(f"已儲存「{school.name}」。")
    return redirect(url_for("admin_schools.schools_page") + f"#school-{school.id}")


@admin_schools_bp.post("/admin/schools/new")
@role_required("admin")
def school_create():
    name = request.form.get("name", "").strip()[:100]
    if not name:
        return _render(error="請填學校名稱（要和簡章上的校名一樣）。", status=400)
    row = {"學校": name, "地區": request.form.get("region", ""), "縣市": request.form.get("city", ""),
           "緯度": request.form.get("latitude", ""), "經度": request.form.get("longitude", ""),
           "官網": request.form.get("website_url", ""), "招生網站": request.form.get("admission_url", ""), "確認日期": ""}
    try:
        directory.import_schools(",".join(directory.CSV_COLUMNS) + "\n" + _csv_line(row))
    except directory.ImportRejected as error:
        db.session.rollback()
        return _render(error=str(error).replace("第 2 列", name), status=400)
    audit_service.record(get_current_user(), "school.create", "school", School.query.filter_by(name=name).one().id)
    db.session.commit()
    flash(f"已新增「{name}」。")
    return redirect(url_for("admin_schools.schools_page"))


@admin_schools_bp.post("/admin/schools/<int:school_id>/departments")
@role_required("admin")
def department_save(school_id):
    school = db.session.get(School, school_id)
    if not school:
        abort(404)
    department = request.form.get("department_name", "").strip()[:100]
    if not department:
        return _render(error="請填科系名稱（要和簡章上的寫法一樣）。", status=400)
    text = "學校,科系,網址\n" + _csv_line({"學校": school.name, "科系": department, "網址": request.form.get("url", "")})
    try:
        directory.import_department_links(text)
    except directory.ImportRejected as error:
        db.session.rollback()
        return _render(error=str(error).replace("第 2 列", f"{school.name}{department}"), status=400)
    audit_service.record(get_current_user(), "school.department_link", "school", school.id, detail={"department": department})
    db.session.commit()
    flash(f"已更新「{school.name}{department}」的科系網址。" if request.form.get("url", "").strip() else f"已移除「{department}」的科系網址。")
    return redirect(url_for("admin_schools.schools_page") + f"#school-{school.id}")


@admin_schools_bp.get("/admin/schools/export/<kind>.csv")
@role_required("admin")
def export(kind):
    if kind not in ("schools", "departments"):
        abort(404)
    text = directory.export_schools() if kind == "schools" else directory.export_department_links()
    name = "schools.csv" if kind == "schools" else "school_department_links.csv"
    return Response(text.encode("utf-8"), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={name}"})


@admin_schools_bp.post("/admin/schools/import")
@role_required("admin")
def import_csv():
    uploaded = request.files.get("file")
    kind = request.form.get("kind")
    if kind not in ("schools", "departments") or not uploaded or not uploaded.filename:
        return _render(error="請選擇要匯入的種類和 CSV 檔。", status=400)
    data = uploaded.read(MAX_CSV_BYTES + 1)
    if len(data) > MAX_CSV_BYTES:
        return _render(error="檔案太大（上限 512 KB）。", status=400)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = data.decode("cp950")  # Excel 另存成「CSV（逗號分隔）」時常是 Big5
        except UnicodeDecodeError:
            return _render(error="看不懂檔案的文字編碼，請用 Excel 另存成「CSV UTF-8（逗號分隔）」。", status=400)
    try:
        if kind == "schools":
            added, updated = directory.import_schools(text)
            message = f"已匯入學校：新增 {added} 所、更新 {updated} 所。"
        else:
            message = f"已匯入科系網址 {directory.import_department_links(text)} 筆。"
    except directory.ImportRejected as error:
        db.session.rollback()
        return _render(error=f"沒有匯入任何資料：{error}", status=400)
    audit_service.record(get_current_user(), "school.import", detail={"kind": kind})
    db.session.commit()
    flash(message)
    return redirect(url_for("admin_schools.schools_page"))


@admin_schools_bp.post("/admin/schools/defaults")
@role_required("admin")
def load_defaults():
    added, updated, links = directory.import_defaults()
    audit_service.record(get_current_user(), "school.import", detail={"kind": "defaults"})
    db.session.commit()
    flash(f"已載入預設資料：新增 {added} 所、更新 {updated} 所學校，科系網址 {links} 筆。")
    return redirect(url_for("admin_schools.schools_page"))


@admin_schools_bp.post("/admin/schools/check-links")
@role_required("admin")
def check_links():
    problems, checked = directory.check_links()
    audit_service.record(get_current_user(), "school.check_links", detail={"checked": checked, "problems": len(problems)})
    db.session.commit()
    return _render(problems=problems, checked=checked)


def _csv_line(row):
    import csv
    import io
    out = io.StringIO()
    csv.writer(out).writerow(list(row.values()))
    return out.getvalue()

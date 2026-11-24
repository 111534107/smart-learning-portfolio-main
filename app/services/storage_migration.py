"""把存在本機的舊檔搬進 Google 雲端硬碟的學生資料夾（B24「決定舊檔要不要搬進學生資料夾」）。

三個階段，前兩個不會改任何東西：
1. preview()：只讀資料庫與本機檔案，列出哪些檔案可以搬、哪些找不到、哪些已在雲端或已標記刪除。
2. dry_run()：在 preview 之外把每個可搬的檔案讀一遍、算雜湊、列出會放到雲端哪個資料夾；不連 Google 寫入。
3. execute()：管理員確認後才執行。把本機檔案複製到雲端學生資料夾、資料庫改記 drive: 位置，
   **本機原檔保留不刪**，旁邊寫 .migrated.json 記下搬去哪裡（M10：不實體刪除）。

範圍：成績單與證照（SourceDocument）、經歷佐證（PortfolioEvidence）、自傳 Word 備份（LearningProfileOutput）。
表單下載區的檔案屬於科辦，不是學生資料，不搬。已標記刪除的檔案也不搬（留在本機保存）。
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app
from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.services import storage_service

MIGRATED_SUFFIX = ".migrated.json"
KIND_LABELS = {"learning-profile": "成績單與證照", "": "經歷佐證", "autobiography": "自傳備份"}
STATUS_LABELS = {
    "ready": "可以搬",
    "missing": "本機找不到檔案",
    "drive": "已在雲端",
    "deleted": "已標記刪除（不搬，留本機保存）",
}


def _rows():
    """逐筆產生 (種類, 資料列, 擁有者 id, 位置)。只讀不寫。"""
    from app.models import LearningProfileOutput, Portfolio, PortfolioEvidence, SourceDocument

    for row in SourceDocument.query.order_by(SourceDocument.id).all():
        yield "learning-profile", row, row.owner_id, row.file_path
    query = (db.session.query(PortfolioEvidence, Portfolio.student_id)
             .join(Portfolio, Portfolio.id == PortfolioEvidence.portfolio_id)
             .filter(PortfolioEvidence.file_path.isnot(None)).order_by(PortfolioEvidence.id))
    for row, student_id in query.all():
        yield "", row, student_id, row.file_path
    for row in LearningProfileOutput.query.order_by(LearningProfileOutput.id).all():
        location = (row.content_json or {}).get("backup_location") if isinstance(row.content_json, dict) else None
        if location:
            yield "autobiography", row, row.student_id, location


def _original_name(location):
    """本機存檔名是「<32 碼亂數>_<原檔名>」，搬到雲端時拿掉亂數，save() 會再加新的。"""
    name = Path(str(location)).name
    head, sep, tail = name.partition("_")
    return tail if sep and len(head) == 32 else name


def _is_deleted(kind, row, location):
    if kind == "" and getattr(row, "deleted_at", None):
        return True
    try:
        return storage_service.is_marked_deleted(location)
    except storage_service.StorageUnavailable:
        return False


def _item(kind, row, owner_id, location):
    if str(location).startswith(storage_service.DRIVE_PREFIX):
        status, size = "drive", None
    elif _is_deleted(kind, row, location):
        status, size = "deleted", None
    else:
        path = storage_service.LocalStorage.path(str(location))
        status = "ready" if path.is_file() else "missing"
        size = path.stat().st_size if status == "ready" else None
    return {"kind": kind, "kind_label": KIND_LABELS[kind], "table": row.__tablename__, "id": row.id,
            "owner_id": owner_id, "status": status, "status_label": STATUS_LABELS[status],
            "name": _original_name(location), "size": size}


def preview():
    """回傳 {"items", "counts", "by_student", "total_bytes"}；只讀，不碰 Google、不改資料。"""
    from app.models import User

    items = [_item(*row) for row in _rows()]
    counts = {status: sum(1 for item in items if item["status"] == status) for status in STATUS_LABELS}
    owners = {item["owner_id"] for item in items}
    names = {user.id: storage_service._owner_folder_name(user.id) for user in
             User.query.filter(User.id.in_(owners)).all()} if owners else {}
    by_student = {}
    for item in items:
        item["folder"] = names.get(item["owner_id"], f"使用者{item['owner_id']}")
        entry = by_student.setdefault(item["owner_id"], {"folder": item["folder"], "ready": 0, "bytes": 0,
                                                         "missing": 0, "drive": 0, "deleted": 0})
        entry[item["status"]] += 1
        entry["bytes"] += item["size"] or 0
    return {"items": items, "counts": counts, "by_student": sorted(by_student.values(), key=lambda e: e["folder"]),
            "total_bytes": sum(item["size"] or 0 for item in items if item["status"] == "ready")}


def blockers():
    """真的要搬之前必須先解決的事；空清單才能執行。"""
    app = current_app._get_current_object()
    problems = [f"{item['label']}：{item['hint']}" for item in storage_service.check_settings(app.config)
                if not item["ok"]]
    if not problems and not storage_service.token_holder(app).connected:
        problems.append("管理員還沒按「連上 Google 雲端硬碟」。")
    return problems


def dry_run():
    """試跑：把每個可搬的檔案讀一遍、算 SHA-256，列出目標資料夾。不連 Google、不改資料。"""
    result = preview()
    for item in result["items"]:
        if item["status"] != "ready":
            continue
        try:
            data = storage_service.read_bytes(_location_of(item))
        except (storage_service.StorageUnavailable, OSError) as error:
            item["status"], item["status_label"], item["note"] = "missing", STATUS_LABELS["missing"], str(error)
            continue
        item["sha256"] = hashlib.sha256(data).hexdigest()
        item["target"] = (f"{storage_service.FOLDER_NAME}／{item['folder']}／"
                          f"{storage_service.SUBFOLDER_LABELS.get(item['kind'], item['kind'] or '其他')}")
    result["counts"] = {status: sum(1 for i in result["items"] if i["status"] == status) for status in STATUS_LABELS}
    result["blockers"] = blockers()
    return result


def _model(table):
    from app.models import LearningProfileOutput, PortfolioEvidence, SourceDocument
    return {SourceDocument.__tablename__: SourceDocument, PortfolioEvidence.__tablename__: PortfolioEvidence,
            LearningProfileOutput.__tablename__: LearningProfileOutput}[table]


def _location_of(item):
    row = db.session.get(_model(item["table"]), item["id"])
    if item["kind"] == "autobiography":
        return (row.content_json or {}).get("backup_location")
    return row.file_path


def _set_location(row, kind, location):
    if kind == "autobiography":
        content = dict(row.content_json)
        content["backup_location"] = location
        row.content_json = content
        flag_modified(row, "content_json")
    else:
        row.file_path = location


def execute(actor, limit=None):
    """真的搬：一次一個檔案，成功一個提交一個；失敗的留在本機、記下原因，不影響其他檔案。

    回傳 {"moved", "failed": [{"name","message"}], "skipped"}。有 blockers() 時直接丟 RuntimeError。
    """
    from app.models import AuditLog

    problems = blockers()
    if problems:
        raise RuntimeError("；".join(problems))
    app = current_app._get_current_object()
    drive = storage_service._drive(app)
    moved, failed = [], []
    ready = [item for item in preview()["items"] if item["status"] == "ready"]
    for item in ready[:limit] if limit else ready:
        row = db.session.get(_model(item["table"]), item["id"])
        old_location = _location_of(item)
        try:
            data = storage_service.read_bytes(old_location)
            new_location = drive.save(data, item["owner_id"], item["kind"], item["name"])
        except (storage_service.DriveError, storage_service.StorageUnavailable, OSError) as error:
            failed.append({"name": item["name"], "folder": item["folder"], "message": storage_service.explain(error)})
            app.logger.warning("搬移舊檔失敗（%s #%s）：%s", item["table"], item["id"], error)
            continue
        _set_location(row, item["kind"], new_location)
        db.session.commit()
        marker = Path(str(storage_service.LocalStorage.path(old_location)) + MIGRATED_SUFFIX)
        marker.write_text(json.dumps({"moved_to": new_location, "moved_at": datetime.now(timezone.utc).isoformat(),
                                      "sha256": hashlib.sha256(data).hexdigest()}, ensure_ascii=False),
                          encoding="utf-8")
        moved.append(item)
    db.session.add(AuditLog(user_id=actor.id, action="system.storage_migrate_to_drive", target_type="system_setting",
                            detail_json={"moved": len(moved), "failed": len(failed),
                                         "remaining": len(ready) - len(moved)}))
    db.session.commit()
    return {"moved": moved, "failed": failed, "skipped": len(ready) - len(moved) - len(failed)}

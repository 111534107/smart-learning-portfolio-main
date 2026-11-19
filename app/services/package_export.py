"""Private, immutable archive attached to a single package submission."""

from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from flask import current_app

from app.models import PackageReview


class ExportUnavailable(RuntimeError):
    """The archived file could not be saved or loaded."""


def confirmed_export(review):
    if review and review.status == "confirmed":
        return (review.snapshot_json or {}).get("export")
    return None


def latest_confirmed_export_review(student, program):
    reviews = (PackageReview.query.filter_by(student_id=student.id, rule_version_id=program.id, status="confirmed")
               .order_by(PackageReview.requested_at.desc(), PackageReview.id.desc()))
    return next((review for review in reviews if confirmed_export(review)), None)


def _path(student_id, export):
    return Path(current_app.config["UPLOAD_FOLDER"]) / "package-reviews" / str(student_id) / f"{export['key']}.zip"


def submission_archive_available(review):
    export = (review.snapshot_json or {}).get("export")
    if not export or not export.get("key"):
        return False
    try:
        read(review.student_id, export, word=True)
    except ExportUnavailable:
        return False
    return True


def discard(student_id, export):
    try:
        _path(student_id, export).unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning("Could not remove an unused package archive", exc_info=True)


def save(student_id, archive, manifest, filename):
    export = {"key": uuid4().hex, "manifest": manifest, "filename": filename}
    path = _path(student_id, export)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as output:
            output.write(archive.getbuffer())
    except OSError as error:
        discard(student_id, export)
        raise ExportUnavailable("暫時無法保存這次送審的備審檔案，請稍後再送一次。") from error
    return export


def read(student_id, export, *, word=False):
    path = _path(student_id, export)
    try:
        if word:
            with ZipFile(path) as archive:
                name = next(name for name in archive.namelist() if name.endswith("/01_備審資料.docx"))
                return BytesIO(archive.read(name))
        return BytesIO(path.read_bytes())
    except (OSError, BadZipFile, StopIteration) as error:
        raise ExportUnavailable("暫時無法讀取這份已確認的備審檔案，請聯絡系統管理員。") from error

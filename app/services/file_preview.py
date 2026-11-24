"""哪些上傳檔案可以直接在瀏覽器裡看（不用下載）。

只開放圖片和 PDF。其他類型（例如 .txt、.html）如果直接顯示，瀏覽器可能把它當成網頁執行，
所以一律只能下載。
"""

from pathlib import Path

from flask import abort, send_file

PREVIEW_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "pdf": "application/pdf"}


def extension(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def preview_kind(filename):
    """回傳 "image"、"pdf"，不能預覽就回傳 None。"""
    mimetype = PREVIEW_TYPES.get(extension(filename))
    if not mimetype:
        return None
    return "pdf" if mimetype == "application/pdf" else "image"


def inline_file(file_path, filename):
    """在瀏覽器直接顯示檔案；不能預覽或檔案不見了（含雲端暫時拿不到）就回 404。

    file_path 是資料庫裡的檔案位置，由 storage_service 換成本機可讀的路徑。
    """
    from app.services import storage_service

    path = storage_service.local_path_or_none(file_path) if preview_kind(filename) else None
    if path is None:
        abort(404)
    # 轉成絕對路徑：send_file 會把相對路徑當成相對於 app/ 資料夾，而上傳檔是相對於專案資料夾
    response = send_file(Path(path).resolve(), mimetype=PREVIEW_TYPES[extension(filename)])
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

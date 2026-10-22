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
    """在瀏覽器直接顯示檔案；不能預覽或檔案不見了就回 404。"""
    if not preview_kind(filename) or not file_path or not Path(file_path).is_file():
        abort(404)
    # 轉成絕對路徑：send_file 會把相對路徑當成相對於 app/ 資料夾，而上傳檔是相對於專案資料夾
    response = send_file(Path(file_path).resolve(), mimetype=PREVIEW_TYPES[extension(filename)])
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

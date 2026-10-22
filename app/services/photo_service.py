"""學期照片：學生上傳「這學期最快樂的照片」，當成首頁拼圖的圖（使用者 2026-10-10 決定）。

- 每學期一張，只有學生本人看得到；不放進備審、不給 AI、不給老師。
- 不新增資料表：存在 UPLOAD_FOLDER/semester-photos/<學生編號>/<年級>-<學期>.jpg，同一學期再傳就覆蓋。
- 一律用 Pillow 重新壓成 JPEG：去掉 EXIF（含拍攝地點），轉正方向，裁成拼圖的 3:2，最長邊 1500 像素。
"""

from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile
import warnings

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

RATIO = 3 / 2
MAX_WIDTH = 1500
MAX_PIXELS = 40_000_000
TOO_LARGE_MESSAGE = "照片太大了，請換一張或先縮小再上傳。"


def current_semester(today=None):
    """上學期 8 月～隔年 1 月，下學期 2～7 月。"""
    month = (today or date.today()).month
    return 1 if month >= 8 or month == 1 else 2


def photo_path(user_id, grade, semester):
    return Path(current_app.config["UPLOAD_FOLDER"]) / "semester-photos" / str(user_id) / f"{grade}-{semester}.jpg"


def has_photo(user_id, grade, semester):
    return photo_path(user_id, grade, semester).is_file()


def save_photo(user_id, grade, semester, stream):
    """讀不懂的檔案丟 ValueError（訊息給學生看）。"""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(stream) as source:
                width, height = source.size
                if width * height > MAX_PIXELS:
                    raise ValueError(TOO_LARGE_MESSAGE)
                image = ImageOps.exif_transpose(source).convert("RGB")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError(TOO_LARGE_MESSAGE) from error
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("看不懂這個檔案，請上傳 JPG 或 PNG 照片。") from error

    # 從中間裁成 3:2
    width, height = image.size
    if width / height > RATIO:
        new_width = int(height * RATIO)
        left = (width - new_width) // 2
        image = image.crop((left, 0, left + new_width, height))
    else:
        new_height = int(width / RATIO)
        top = (height - new_height) // 2
        image = image.crop((0, top, width, top + new_height))
    if image.width > MAX_WIDTH:
        image = image.resize((MAX_WIDTH, int(MAX_WIDTH / RATIO)), Image.LANCZOS)

    path = photo_path(user_id, grade, semester)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
        image.save(temporary, "JPEG", quality=85)  # 不帶 exif 參數，原本的拍攝資訊都不會寫入
        temporary.replace(path)
    finally:
        image.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path

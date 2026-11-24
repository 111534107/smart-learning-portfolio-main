"""自傳段落的圖片（2026-11-18 使用者要求：自傳能貼上圖片）。

- 不新增資料表：檔案存在 UPLOAD_FOLDER/autobiography-images/<學生編號>/<32 碼編號>.jpg；
  段落（content_json["paragraphs"][i]["images"]）只記編號。每次儲存都是新的一版，舊版引用的圖不刪。
- 一律用 Pillow 重新壓成 JPEG：去掉 EXIF（含拍攝地點）、擋掉不是圖片的檔案（SVG、偽裝檔）。
- 只有本人與負責該班的導師看得到；圖片不送 AI（AI 只拿段落文字）。
"""

import re
import warnings
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 6 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_SIDE = 1600
MAX_PER_PARAGRAPH = 6
ID_PATTERN = re.compile(r"[0-9a-f]{32}")


def _folder(student_id):
    return Path(current_app.config["UPLOAD_FOLDER"]).resolve() / "autobiography-images" / str(int(student_id))


def image_path(student_id, image_id):
    """編號不合格式或檔案不存在回傳 None（編號進路徑前先驗，擋掉 ../）。"""
    if not isinstance(image_id, str) or not ID_PATTERN.fullmatch(image_id):
        return None
    path = _folder(student_id) / f"{image_id}.jpg"
    return path if path.is_file() else None


def _save_jpeg(student_id, image):
    image_id = uuid4().hex
    folder = _folder(student_id)
    folder.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=folder, prefix=".img.", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
        image.save(temporary, "JPEG", quality=85)
        temporary.replace(folder / f"{image_id}.jpg")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return image_id


def import_pil(student_id, image):
    """學生上傳過的原始檔（證照照片、成績單掃描）轉成這裡的圖：去 EXIF、縮到最長邊 1600、存成 JPEG。回傳新編號。"""
    converted = ImageOps.exif_transpose(image).convert("RGB")
    try:
        converted.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
        return _save_jpeg(student_id, converted)
    finally:
        converted.close()


def rotate_image(student_id, image_id, degrees=90):
    """順時針轉 90 度（學校成績單是橫的，貼進直式 A4 要轉過去）；存成新的一張，原圖保留。回傳 (新編號, 寬, 高)。"""
    path = image_path(student_id, image_id)
    if path is None:
        raise ValueError("找不到這張圖片。")
    with Image.open(path) as source:
        turned = source.convert("RGB").rotate(-(int(degrees) % 360), expand=True)
    try:
        return _save_jpeg(student_id, turned), turned.width, turned.height
    finally:
        turned.close()


def size_of(student_id, image_id):
    path = image_path(student_id, image_id)
    if path is None:
        return None
    with Image.open(path) as source:
        return source.size


def save_image(student_id, stream):
    """回傳新圖片編號；看不懂的檔案丟 ValueError（訊息給學生看）。"""
    data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("圖片太大了（上限 6 MB），請先縮小再貼上。")
    try:
        import io
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in ("PNG", "JPEG", "WEBP", "GIF", "BMP"):
                    raise ValueError("只能貼上 JPG、PNG、WEBP 圖片。")
                if source.width * source.height > MAX_PIXELS:
                    raise ValueError("圖片太大了，請先縮小再貼上。")
                image = ImageOps.exif_transpose(source).convert("RGB")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError("圖片太大了，請先縮小再貼上。") from error
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("看不懂這個檔案，請貼上 JPG 或 PNG 圖片。") from error
    image.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    image_id = uuid4().hex
    folder = _folder(student_id)
    folder.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=folder, prefix=".img.", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
        image.save(temporary, "JPEG", quality=85)
        temporary.replace(folder / f"{image_id}.jpg")
    finally:
        image.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return image_id


def clean_ids(student_id, ids):
    """只留格式正確、確實是這位學生自己的圖，去重、最多 6 張。"""
    kept = []
    for image_id in ids:
        if image_id not in kept and image_path(student_id, image_id):
            kept.append(image_id)
    return kept[:MAX_PER_PARAGRAPH]

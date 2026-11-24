"""證照、獎狀照片是否模糊或歪斜（11-05 評審意見 3，2026-11-10）。

只提醒「可能看不清楚，建議重拍」，不擋上傳。各支手機拍照品質不同，所以不看手機型號，只看圖片本身：
- 模糊：灰階縮到長邊 1000 像素後做邊緣偵測（拉普拉斯），邊緣強度的變異數太低代表沒有清楚的筆畫邊緣。
- 歪斜：把圖片轉 -12°～+12°，看哪個角度讓「每一列的深色比例」起伏最大（文字列對齊水平時，列與列間距最分明）。
  最佳角度超過 3° 就提醒擺正。
只用 Pillow（requirements.txt 已有），不另外安裝套件。PDF 不檢查（通常是電子檔，不會模糊或歪）。
"""
import io
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps, ImageStat

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
BLUR_THRESHOLD = 25.0  # 筆畫邊緣強度（0～128）；清楚照片接近 128，合成文件糊化 sigma 3 約 20（11-10 校正）
SKEW_LIMIT = 3.0  # 度
SKEW_ANGLES = [x / 2 for x in range(-24, 25)]  # -12°～+12°，每 0.5° 一格
LAPLACIAN = ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=128)

MESSAGE = "這張照片可能看不清楚，建議重拍：{reasons}。系統沒有擋下，請對照原圖確認辨識結果。"


def _gray(image, long_side):
    image = ImageOps.exif_transpose(image).convert("L")
    ratio = long_side / max(image.size)
    if ratio < 1:
        image = image.resize((max(1, round(image.width * ratio)), max(1, round(image.height * ratio))),
                             Image.Resampling.LANCZOS)
    return image


def blur_score(image):
    """筆畫邊緣有多銳利：只看有邊緣的像素（強度 ≥ 4），取其中前 5% 的邊緣強度。
    只看有邊緣的地方，所以文字多寡、留白多少不影響分數。"""
    edges = _gray(image, 1000).filter(LAPLACIAN)
    edges = edges.crop((1, 1, edges.width - 1, edges.height - 1))  # Pillow 不處理最外圈像素，保留原值會被誤當成強邊緣
    histogram = edges.histogram()
    strength = [0] * 129
    for value, count in enumerate(histogram):
        strength[min(abs(value - 128), 128)] += count
    total = sum(strength[4:])
    if total < 200:  # 幾乎沒有邊緣（空白或整張糊掉）
        return 0.0
    seen = 0
    for level in range(128, 3, -1):
        seen += strength[level]
        if seen >= total * 0.05:
            return float(level)
    return 4.0


def _row_profile_score(gray, angle):
    rotated = gray.rotate(angle, resample=Image.Resampling.BILINEAR, expand=False, fillcolor=255)
    width, height = rotated.size
    margin_x, margin_y = width // 6, height // 6  # 只看中間，避開旋轉後補白的角落
    middle = rotated.crop((margin_x, margin_y, width - margin_x, height - margin_y))
    rows = middle.resize((1, middle.height), Image.Resampling.BOX)  # 每一列的平均亮度
    return ImageStat.Stat(rows).var[0]


def skew_angle(image):
    """估計文字傾斜幾度（正負代表方向）；看不出文字列時回傳 0。"""
    gray = _gray(image, 600)
    gray = gray.point(lambda value: 0 if value < 140 else 255)  # 黑白化，文字列更分明
    scores = [(_row_profile_score(gray, angle), angle) for angle in SKEW_ANGLES]
    best_score, best_angle = max(scores, key=lambda item: (item[0], -abs(item[1])))
    level_score = next(score for score, angle in scores if angle == 0)
    if best_score <= 0 or level_score <= 0:
        return 0.0
    if best_score < level_score * 1.15:  # 差不多就當作沒歪，避免照片背景造成誤判
        return 0.0
    return -best_angle  # 轉 -x 度變正，代表原圖歪 x 度


def check(file_bytes, filename):
    """回傳 {"blurry": bool, "skew": 度數, "message": 提醒文字}；不是圖片或讀不了時回傳 None。"""
    if Path(filename or "").suffix.lower() not in IMAGE_SUFFIXES:
        return None
    try:
        with Image.open(io.BytesIO(file_bytes)) as image:
            image.load()
            blur = blur_score(image)
            skew = skew_angle(image)
    except Exception:
        return None
    reasons = []
    blurry = blur < BLUR_THRESHOLD
    if blurry:
        reasons.append("照片有點模糊")
    if abs(skew) > SKEW_LIMIT:
        reasons.append(f"照片歪了約 {abs(skew):.0f} 度")
    return {"blurry": blurry, "skew": skew, "blur_score": round(blur, 1),
            "message": MESSAGE.format(reasons="、".join(reasons)) if reasons else ""}

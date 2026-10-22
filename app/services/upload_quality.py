"""上傳前檢查圖片解析度：成績單圖片太小時 OCR 只會產生亂字，先請學生改傳。

門檻來自實測（2026-10-20，同一份成績單縮成不同寬度，見 docs/03_開發紀錄/OCR驗收紀錄_2026-10-20.md）：
原始 3507 像素 85 門有 84 門學分成績齊全；2800 像素剩 60 門；2000 像素以下時好時壞；1024 像素完全抓不到表格。
PDF 會以 300 DPI 轉成圖片，不受影響；技術士證 1005 像素寬也全部讀對，所以只檢查成績單圖片。
"""
import io
from pathlib import Path

from PIL import Image

TRANSCRIPT_MIN_LONG_SIDE = 1600
TRANSCRIPT_RECOMMENDED_LONG_SIDE = 3000
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def resolution_check(document_type, file_bytes, filename):
    """回傳 {"level": "ok"|"low"|"too_small", "long_side": 像素, "message": 說明}；不需要檢查時回傳 None。"""
    if document_type != "transcript" or Path(filename).suffix.lower() not in IMAGE_SUFFIXES:
        return None
    try:
        with Image.open(io.BytesIO(file_bytes)) as image:
            long_side = max(image.size)
    except Exception:
        return None  # 讀不了的圖片交給辨識流程回報錯誤
    if long_side < TRANSCRIPT_MIN_LONG_SIDE:
        return {"level": "too_small", "long_side": long_side,
                "message": (f"這張圖片解析度太低（長邊只有 {long_side} 像素），字太小讀不出來。"
                            f"請改傳學校系統下載的 PDF，或長邊至少 {TRANSCRIPT_RECOMMENDED_LONG_SIDE} 像素的清楚圖片。")}
    if long_side < TRANSCRIPT_RECOMMENDED_LONG_SIDE:
        return {"level": "low", "long_side": long_side,
                "message": (f"圖片解析度偏低（長邊 {long_side} 像素），可能有課程、學分或成績漏讀；"
                            "請逐筆對照原圖，或改傳學校系統下載的 PDF。")}
    return {"level": "ok", "long_side": long_side, "message": ""}

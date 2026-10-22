"""Optional local OCR adapters; all coordinates refer to the supplied PIL image.

This module does no deskewing, EXIF rotation, resizing, table parsing, or engine
fallback. Paddle's detection/recognition internals return input-image polygons.
Heavy dependencies and model initialization are deferred until recognize().
"""

from collections.abc import Mapping
from importlib import import_module
import json
import math
import threading


_paddle_engine = None
_paddle_lock = threading.Lock()
_rapidocr_engines = {}
_rapidocr_lock = threading.Lock()
_TESSERACT_TIMEOUT_SECONDS = 60
# 回傳整行文字框的引擎（Tesseract 回傳單字）；流程依此決定是否放大裁切區。
LINE_LEVEL_ENGINES = frozenset({"paddleocr", "paddle", "rapidocr"})


def _optional_import(name):
    try:
        return import_module(name)
    except Exception:
        # DLL/import errors can include paths or arbitrary dependency messages.
        raise RuntimeError(
            f"無法載入 OCR 套件 {name}。請在本機 .venv-ocr 環境安裝 "
            "requirements-ocr.txt，並確認 CPU 執行環境完整。"
            "設定方式請參閱 docs/ocr-setup.md。"
        ) from None


def _confidence(value, scale=1.0):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return min(1.0, number / scale)


def _finite_bbox(values):
    box = [float(value) for value in values]
    if (len(box) != 4 or not all(math.isfinite(value) for value in box)
            or box[2] < box[0] or box[3] < box[1]):
        raise ValueError("Invalid OCR bounding box")
    return box


def _tesseract_tokens(data):
    texts = data["text"]
    fields = [data[key] for key in ("left", "top", "width", "height", "conf")]
    if any(len(field) != len(texts) for field in fields):
        raise ValueError("Inconsistent OCR fields")
    tokens = []
    for text, left, top, width, height, score in zip(texts, *fields):
        # TSV contains page/block/line rows with empty text and confidence -1.
        if not isinstance(text, str):
            raise ValueError("Invalid OCR text")
        if not text.strip():
            continue
        left, top, width, height = map(float, (left, top, width, height))
        tokens.append({
            "text": text,
            "bbox": _finite_bbox((left, top, left + width, top + height)),
            "confidence": _confidence(score, scale=100.0),
        })
    return tokens


def _recognize_tesseract(image, *, lang="chi_tra+eng", config="--psm 6"):
    pytesseract = _optional_import("pytesseract")
    try:
        data = pytesseract.image_to_data(
            image, lang=lang, config=config,
            output_type=pytesseract.Output.DICT, timeout=_TESSERACT_TIMEOUT_SECONDS,
        )
        return _tesseract_tokens(data)
    except Exception:
        raise RuntimeError(
            "Tesseract 文字辨識失敗。請確認本機 tesseract 執行檔、"
            "chi_tra 與 eng 語言資料已安裝；圖片過大也可能造成 60 秒執行逾時。"
            "設定方式請參閱 docs/ocr-setup.md。"
        ) from None


def recognize_tesseract_level(image):
    """Read a tightly cropped grade using Tesseract's Chinese character mode."""
    return _recognize_tesseract(image, lang="chi_sim", config="--psm 10")


def recognize_tesseract_number(image):
    """Read a tightly cropped certificate number as sparse Latin text."""
    return _recognize_tesseract(image, lang="eng", config="--psm 11")


def _paddle_tokens(result):
    # Native OCRResult is dict-like. Its .json property instead wraps a 'res'
    # dictionary; serialized JSON is also accepted for version-compatible users.
    if not isinstance(result, Mapping):
        result = result.json
    if isinstance(result, str):
        result = json.loads(result)
    if not isinstance(result, Mapping):
        raise ValueError("Invalid PaddleOCR result")
    if "res" in result:
        result = result["res"]
    texts = result["rec_texts"]
    polygons = result["rec_polys"]
    scores = result.get("rec_scores")
    if scores is None:
        scores = [None] * len(texts)
    if len(texts) != len(polygons) or len(texts) != len(scores):
        raise ValueError("Inconsistent PaddleOCR fields")
    tokens = []
    for text, polygon, score in zip(texts, polygons, scores):
        if not isinstance(text, str) or len(polygon) < 3:
            raise ValueError("Invalid PaddleOCR region")
        points = []
        for point in polygon:
            if len(point) != 2:
                raise ValueError("Invalid PaddleOCR polygon")
            x, y = float(point[0]), float(point[1])
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError("Invalid PaddleOCR coordinates")
            points.append((x, y))
        xs, ys = zip(*points)
        tokens.append({
            "text": text,
            "bbox": _finite_bbox((min(xs), min(ys), max(xs), max(ys))),
            "confidence": _confidence(score),
        })
    return tokens


def _recognize_paddle(image):
    global _paddle_engine
    # One cached predictor per process. Hold the lock through generator iteration
    # and parsing: Paddle may perform inference lazily or reuse result buffers.
    with _paddle_lock:
        if _paddle_engine is None:
            paddleocr = _optional_import("paddleocr")
            try:
                _paddle_engine = paddleocr.PaddleOCR(
                    ocr_version="PP-OCRv5",
                    text_detection_model_name="PP-OCRv5_server_det",
                    text_recognition_model_name="PP-OCRv5_server_rec",
                    device="cpu",
                    cpu_threads=4,
                    enable_mkldnn=False,
                    text_recognition_batch_size=16,
                    # The caller already upscales narrow table columns. Avoid
                    # enlarging their short side to the detector's min default.
                    text_det_limit_type="max",
                    text_det_limit_side_len=2560,
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    text_rec_score_thresh=0.0,
                )
            except Exception:
                raise RuntimeError(
                    "PaddleOCR 無法載入 PP-OCRv5 CPU 模型。請確認 "
                    "requirements-ocr.txt 套件、PaddlePaddle 執行環境、"
                    "本機模型快取及模型下載權限。設定方式請參閱 docs/ocr-setup.md。"
                ) from None
        np = _optional_import("numpy")
        try:
            # PIL uses RGB; PaddleX's ndarray reader expects BGR. Copy removes
            # negative strides and keeps the caller's pixels untouched.
            bgr = np.asarray(image.convert("RGB"), dtype=np.uint8)[:, :, ::-1].copy()
            tokens = []
            for result in _paddle_engine.predict(bgr):
                tokens.extend(_paddle_tokens(result))
            return tokens
        except Exception:
            raise RuntimeError(
                "PaddleOCR PP-OCRv5 文字辨識失敗。請確認指定的 v3 套件版本、"
                "CPU 執行環境、模型檔案及圖片大小。設定方式請參閱 docs/ocr-setup.md。"
            ) from None


def configured_rapidocr_tier():
    """Flask 設定的模型等級（OCR_MODEL_TIER）；沒有應用程式環境時用伺服器版。"""
    return configured_rapidocr_settings()[0]


def configured_rapidocr_settings():
    """回傳 (模型等級, 執行裝置, DirectML 顯示卡編號)；沒有應用程式環境時用伺服器版＋CPU。"""
    from flask import current_app, has_app_context

    if not has_app_context():
        return "server", "cpu", 0
    from app.services.ocr_settings import current_device

    # 裝置以系統管理員在網站上的設定為準，沒有設定時用設定檔
    device, dml_device_id = current_device()
    return current_app.config.get("OCR_MODEL_TIER", "server"), device, dml_device_id


def _rapidocr_engine():
    """呼叫端須持有 _rapidocr_lock。每組（模型等級、裝置、顯示卡編號）每個程序只載入一次。"""
    from app.services.document_analysis_service import RapidOcrEngine

    settings = configured_rapidocr_settings()
    if settings not in _rapidocr_engines:
        tier, device, dml_device_id = settings
        _rapidocr_engines[settings] = RapidOcrEngine(tier=tier, device=device, dml_device_id=dml_device_id)._load()
    return _rapidocr_engines[settings]


def recognize_rapidocr_line(image):
    """只做文字辨識（不偵測文字框），用於已切好的一格表格。回傳 (文字, 信心) 或 None。

    窄小的數字欄用文字框偵測時，兩位數會被拆成兩個框或漏掉一位數；整格直接辨識可避免。
    """
    with _rapidocr_lock:
        try:
            output = _rapidocr_engine()(image.convert("RGB"), use_det=False, use_cls=False, use_rec=True)
        except Exception:
            raise RuntimeError(
                "RapidOCR 文字辨識失敗。請確認 rapidocr、onnxruntime 套件與 instance/ocr-models 模型檔。"
            ) from None
    texts = list(output.txts or ())
    if not texts or not texts[0].strip():
        return None
    scores = list(output.scores or ())
    return texts[0].strip(), _confidence(scores[0]) if scores else None


def _recognize_rapidocr(image):
    # 本機 RapidOCR（PP-OCRv5 ONNX 模型，與 PaddleOCR 伺服器版同一套模型），不需 PaddlePaddle。
    # 鎖住推論，避免多執行緒共用同一個模型時互相干擾。

    with _rapidocr_lock:
        try:
            # 明確開啟偵測：rapidocr 會記住上一次呼叫的設定（逐格辨識時關掉了偵測）
            output = _rapidocr_engine()(image.convert("RGB"), use_det=True, use_cls=True, use_rec=True)
        except Exception:
            raise RuntimeError(
                "RapidOCR 文字辨識失敗。請確認 rapidocr、onnxruntime 套件與 instance/ocr-models 模型檔。"
            ) from None
    if output.boxes is None or not output.txts:
        return []
    tokens = []
    for polygon, text, score in zip(output.boxes.tolist(), output.txts, output.scores):
        xs = [float(point[0]) for point in polygon]
        ys = [float(point[1]) for point in polygon]
        tokens.append({
            "text": text,
            "bbox": _finite_bbox((min(xs), min(ys), max(xs), max(ys))),
            "confidence": _confidence(score),
        })
    return tokens


def recognize(image, engine="tesseract") -> list[dict]:
    """Return text, float [left, top, right, bottom], and confidence per region.

    ``image`` must be a PIL image already oriented by the caller. Engine names
    are ``tesseract`` (default), ``paddleocr``, the alias ``paddle``, and
    ``rapidocr`` (local PP-OCRv5 ONNX models). No
    recognition confidence filtering is performed; unknown confidence is None.
    Paddle and RapidOCR return text-line regions, while Tesseract generally returns words.
    Missing dependencies and inference failures raise sanitized RuntimeError;
    unsupported engines raise ValueError. Neither case selects another engine.
    """
    if engine not in ("tesseract", "paddleocr", "paddle", "rapidocr"):
        raise ValueError("不支援此 OCR 引擎；請選擇 'tesseract'、'paddleocr' 或 'rapidocr'。")
    pil_image = _optional_import("PIL.Image")
    if not isinstance(image, pil_image.Image) or image.width < 1 or image.height < 1:
        raise ValueError("OCR 需要寬度與高度皆大於零的 PIL 圖片。")
    if engine == "tesseract":
        return _recognize_tesseract(image)
    if engine == "rapidocr":
        return _recognize_rapidocr(image)
    return _recognize_paddle(image)

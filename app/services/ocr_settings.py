"""OCR 執行裝置設定：系統管理員可在網站切換 CPU 或顯示卡（DirectML），存進 system_settings。

資料庫沒有設定時用設定檔（OCR_DEVICE、OCR_DML_DEVICE_ID）。OCR 每一格辨識都會讀設定，
所以讀到的值快取 10 秒；管理員儲存時立即清除本程序的快取，其他程序最慢 10 秒後跟上。
"""
import time

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db

DEVICE_KEY = "ocr_device"
DML_DEVICE_ID_KEY = "ocr_dml_device_id"
DEVICE_LABELS = {"cpu": "CPU", "dml": "顯示卡（DirectML）"}
_CACHE_SECONDS = 10


def directml_available():
    """這台電腦的 onnxruntime 是否支援 DirectML 顯示卡加速（需安裝 onnxruntime-directml）。"""
    try:
        import onnxruntime
    except ImportError:
        return False
    return "DmlExecutionProvider" in onnxruntime.get_available_providers()


def _cache():
    return current_app.extensions.setdefault("ocr_device_cache", {})


def current_device():
    """回傳 (裝置, DirectML 顯示卡編號)。"""
    cache = _cache()
    now = time.monotonic()
    if cache.get("expires", 0) > now:
        return cache["value"]
    device = current_app.config.get("OCR_DEVICE", "cpu")
    dml_device_id = int(current_app.config.get("OCR_DML_DEVICE_ID", 0))
    try:
        from app.models import SystemSetting

        stored = {row.key: row.value for row in SystemSetting.query.filter(
            SystemSetting.key.in_((DEVICE_KEY, DML_DEVICE_ID_KEY))).all()}
        device = stored.get(DEVICE_KEY, device)
        dml_device_id = int(stored.get(DML_DEVICE_ID_KEY, dml_device_id))
    except SQLAlchemyError:
        db.session.rollback()  # 沒有資料表（例如離線腳本）時沿用設定檔
    value = (device, dml_device_id)
    cache.update(value=value, expires=now + _CACHE_SECONDS)
    return value


def save_device(device, dml_device_id, user):
    """驗證並儲存；不合法時丟 ValueError（訊息給管理員看）。"""
    from app.models import AuditLog, SystemSetting

    if device not in DEVICE_LABELS:
        raise ValueError("請選擇 CPU 或顯示卡")
    if not 0 <= dml_device_id <= 15:
        raise ValueError("顯示卡編號請填 0 到 15")
    if device == "dml" and not directml_available():
        raise ValueError("這台電腦沒有可用的顯示卡加速（目前安裝的 onnxruntime 只支援 CPU）；"
                         "請先依 requirements-directml.txt 改裝 onnxruntime-directml。")
    previous = current_device()
    for key, value in ((DEVICE_KEY, device), (DML_DEVICE_ID_KEY, str(dml_device_id))):
        row = SystemSetting.query.filter_by(key=key).first()
        if row:
            row.value, row.updated_by_id = value, user.id
        else:
            db.session.add(SystemSetting(key=key, value=value, updated_by_id=user.id))
    db.session.add(AuditLog(user_id=user.id, action="system.ocr_device_changed", target_type="system_setting",
                            detail_json={"from": list(previous), "to": [device, dml_device_id]}))
    db.session.commit()
    _cache().clear()

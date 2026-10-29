"""啟動腳本共用：確保展示站與正式版都用真實的本機 OCR（RapidOCR），不會停在假辨識。

使用者 10-28 要求：不管啟動哪一版（展示站、正式版），功能都要能用。
模型缺少時從官方 ModelScope 下載並核對 SHA-256（見 download_ocr_models.py）；下載失敗才退回，並大聲提示。
"""

from download_ocr_models import MODEL_DIR, MODELS, file_sha256, main as download_models

FAKE_PROVIDERS = {"", "fake", "demo"}


def models_ready():
    return all((MODEL_DIR / name).exists() and file_sha256(MODEL_DIR / name) == expected
               for name, (_, expected) in MODELS.items())


def ensure_models():
    """模型齊全回傳 True；缺少就下載，下載失敗回傳 False。"""
    if models_ready():
        return True
    print("OCR 模型不齊全，從官方 ModelScope 下載（約 100 MB，會核對 SHA-256）……")
    try:
        download_models()
    except (OSError, SystemExit) as error:
        print(f"！！ OCR 模型下載失敗：{error}")
        return False
    return models_ready()


def real_ocr_provider(current):
    """目前設定是假辨識時改成 rapidocr；模型準備不好就維持原值並提示。"""
    if (current or "").lower() not in FAKE_PROVIDERS:
        return current
    if ensure_models():
        return "rapidocr"
    print("！！ 成績單與證照目前無法真的辨識。請連上網路後重新啟動，"
          "或手動執行 python scripts/download_ocr_models.py。")
    return current

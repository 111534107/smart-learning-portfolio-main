"""下載離線 OCR（RapidOCR PP-OCRv5 伺服器版與輕量版）模型到 instance/ocr-models，並核對 SHA-256。

來源：RapidAI 官方 ModelScope 模型庫（網址與雜湊取自 rapidocr 3.10.0 的 default_models.yaml）。
只需執行一次；之後辨識完全離線，原始圖片不會送出伺服器。
用法：python scripts/download_ocr_models.py
"""
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

BASE = "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx"
MODELS = {
    "ch_PP-OCRv5_det_mobile.onnx": (
        f"{BASE}/PP-OCRv5/det/ch_PP-OCRv5_det_mobile.onnx",
        "4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae",
    ),
    # PP-OCRv5 中文辨識模型同時支援簡體、繁體、英文與日文
    "ch_PP-OCRv5_rec_mobile.onnx": (
        f"{BASE}/PP-OCRv5/rec/ch_PP-OCRv5_rec_mobile.onnx",
        "5825fc7ebf84ae7a412be049820b4d86d77620f204a041697b0494669b1742c5",
    ),
    # 伺服器版：準確度較高、較慢、檔案較大（預設使用）
    "ch_PP-OCRv5_det_server.onnx": (
        f"{BASE}/PP-OCRv5/det/ch_PP-OCRv5_det_server.onnx",
        "0f8846b1d4bba223a2a2f9d9b44022fbc22cc019051a602b41a7fda9667e4cad",
    ),
    "ch_PP-OCRv5_rec_server.onnx": (
        f"{BASE}/PP-OCRv5/rec/ch_PP-OCRv5_rec_server.onnx",
        "e09385400eaaaef34ceff54aeb7c4f0f1fe014c27fa8b9905d4709b65746562a",
    ),
    "ch_ppocr_mobile_v2.0_cls_mobile.onnx": (
        f"{BASE}/PP-OCRv4/cls/ch_ppocr_mobile_v2.0_cls_mobile.onnx",
        "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",
    ),
}
MODEL_DIR = Path(__file__).resolve().parents[1] / "instance" / "ocr-models"


def file_sha256(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for name, (url, expected) in MODELS.items():
        target = MODEL_DIR / name
        if target.exists() and file_sha256(target) == expected:
            print(f"已存在且雜湊相符：{name}")
            continue
        partial = target.with_suffix(".part")
        with urlopen(url, timeout=120) as response:
            partial.write_bytes(response.read())
        actual = file_sha256(partial)
        if actual != expected:
            raise SystemExit(f"雜湊不符，未採用：{name}（預期 {expected}，實際 {actual}）；檔案留在 {partial}")
        partial.replace(target)
        print(f"下載完成並核對：{name}")


if __name__ == "__main__":
    main()

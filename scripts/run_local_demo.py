"""啟動本機合成資料展示站：python scripts/run_local_demo.py

預設用真實的本機 RapidOCR（組員 OCR 流程＋PP-OCRv5），上傳的圖片只在本機辨識；模型缺少會自動下載。
只想看畫面可加 --fake-ocr 改回模擬辨識（--ocr 仍可用，效果同預設）。
再加上 --gpu 編號 會用 Windows DirectML 顯示卡加速（需安裝 onnxruntime-directml）；
筆電的 0 多半是內建顯示，獨立顯示卡常是 1。不加 --gpu 就是 CPU。
.env 填好 GOOGLE_OAUTH_CLIENT_ID／SECRET／REDIRECT_URI 時自動開放「自傳在 Google 文件中編輯」；
沒填就完全不連 Google。設定步驟見 docs/03_開發紀錄/01_參考與環境設定/Google文件自傳編輯_設定步驟.md。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Config
from app.demo import create_local_demo_app


from real_ocr import real_ocr_provider


app = create_local_demo_app()
args = sys.argv[1:]
# 預設就用真實 OCR（--ocr 保留相容）；只想看畫面可加 --fake-ocr 改回模擬辨識
if "--fake-ocr" not in args:
    app.config["DOCUMENT_ANALYSIS_PROVIDER"] = real_ocr_provider(app.config["DOCUMENT_ANALYSIS_PROVIDER"])
# .env 有填好 Google OAuth 就直接開放（--google 保留相容）
if all(getattr(Config, key) for key in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET")):
    for key in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REDIRECT_URI"):
        app.config[key] = getattr(Config, key)
if "--gpu" in args:
    position = args.index("--gpu")
    app.config["OCR_DEVICE"] = "dml"
    app.config["OCR_DML_DEVICE_ID"] = int(args[position + 1]) if position + 1 < len(args) else 0

if __name__ == "__main__":
    print("本機展示站：http://127.0.0.1:5013/proposal-preview")
    print("合成帳號：student_demo / teacher_demo / staff_demo / admin_demo；密碼皆為 demo2026")
    print("資料庫為記憶體 SQLite，服務停止後資料即消失。")
    from app.services.google_docs_service import configured
    if configured(app.config):
        print("Google 文件：已開放自傳在 Google 文件中編輯（只要 drive.file；權杖只放記憶體）")
    else:
        print("Google：不連線（.env 填好 OAuth 設定才會開放）")
    if app.config["DOCUMENT_ANALYSIS_PROVIDER"] == "rapidocr":
        device = (f"顯示卡（DirectML 編號 {app.config['OCR_DML_DEVICE_ID']}）"
                  if app.config.get("OCR_DEVICE") == "dml" else "CPU")
        print(f"OCR 模式：真實本機 RapidOCR，執行裝置：{device}")
    else:
        print("OCR 模式：模擬 OCR（合成資料）")
    # 多執行緒：單執行緒時瀏覽器保留的連線會卡住其他請求；記憶體 SQLite 已設定 StaticPool 可跨執行緒，
    # RapidOCR 推論另有鎖保護
    app.run(host="127.0.0.1", port=5013, debug=False, threaded=True)

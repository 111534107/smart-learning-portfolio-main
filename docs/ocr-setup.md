# Optional local OCR setup

> **2026-10-19 合併說明（feat/teammate-ocr 分支）**：本文件由組員 111534107 撰寫。合併到本分支後，建議改用 `rapidocr` 引擎：
> 與 PaddleOCR 使用同一套 PP-OCRv5 伺服器版模型，但以 ONNX 執行，不需要 Python 3.12、PaddlePaddle 或 `.venv-ocr`。
> 步驟：在主要虛擬環境安裝 `requirements.txt` → 執行 `python scripts/download_ocr_models.py`（從 RapidAI 官方 ModelScope 下載並核對 SHA-256）
> → `.env` 設定 `DOCUMENT_ANALYSIS_PROVIDER=rapidocr`（可用 `OCR_MODEL_TIER=mobile` 切回輕量版）。
> 本分支沒有搬 `requirements-ocr.txt` 與 `start-ocr.ps1`；以下 PaddleOCR／Tesseract 說明保留作參考。
> Tesseract 的數字與等級補辨識在未安裝 Tesseract 時會自動略過，不影響主流程。

## 本專案的使用方式

安裝完成後，在專案 PowerShell 執行 `./start-ocr.ps1`，會以 `.venv-ocr`
啟動網站並使用 PaddleOCR；回退測試可用 `./start-ocr.ps1 -Provider tesseract`。
先關閉既有的 5000 埠開發網站，啟動器不會終止其他程序。啟動器只設定子程序
的 OCR provider，不修改全域 Python 或永久環境變數。

到「我的來源檔」按「重新分析」，會建立新草稿，保留已確認紀錄。
新草稿需明確按「確認並儲存」才替換該文件的已確認資料。
失敗會保留原草稿與紀錄；最多保留五份舊擷取快照（後台 JSON）。
每筆課程可核對科目、學分、成績、學期、年級及原圖區域。
0 學分與缺漏值分開處理，信心分數不是正確率。未識別的年級表頭保持空白。
不熟悉的版型和無法擷取的頁面會提示人工核對，不能當作完整擷取。

PDF 使用 PDFium 以 300 DPI 逐頁轉圖，最多 10 頁，每頁最多 2500 萬像素。
目前不讀取 PDF 文字層；加密／損毀／過大的 PDF 會要求重新整理後上傳。
本流程針對此校成績單的分年、雙學期表格定位，不是通用表格辨識器。

### 2026-10-08 本機驗證紀錄

- Windows／Python 3.12 專案環境完成安裝，`pip check` 無相依衝突。
- 兩個 PP-OCRv5 server 模型已下載，合成圖片及一張使用者成績單已實際推論。
- 該次整張測試：PaddleOCR 86 筆候選、7 筆零學分、1 筆缺課名、1 筆缺成績；
  Tesseract 新流程為 95 筆候選、7 筆零學分、10 筆缺課名、15 筆缺成績。
  這是未逐欄標註的單張測試，**不能轉換成正確率**；候選數也不代表課程總數。
- 完整 CPU 辨識約 8 分鐘。另測 MKL-DNN 開啟，合成 25 列反而耗時 387 秒，
  因此目前保持關閉。實際耗時依硬體、頁数及影像尺寸而變動。
- 上述整張數據取得後，另加入年級表頭辨識、未知版型保留、字框高度配對修正；
  這些有回歸測試，但不能拿前次整張數據當成最終版精確品質測量。

本機開發流程是同步辨識。正式部署前應改用背景工作佇列及逾時控制；
一般反向代理／WSGI 的短逾時不適合數分鐘的同步請求。

The standalone adapter is `app/services/ocr_engines.py`. It supports Tesseract
and PaddleOCR 3.x on the local machine. Installing Paddle is optional; importing
the adapter does not import either engine or load models. Selecting an unavailable
engine raises an actionable `RuntimeError`; there is no automatic fallback.

## Isolated Windows CPU environment

Use **64-bit CPython 3.12** and a project-local virtual environment. From the
repository root in PowerShell, an operator can run:

```powershell
py -3.12 -m venv .venv-ocr
.\.venv-ocr\Scripts\python.exe -m pip install -r requirements.txt -r requirements-ocr.txt
.\.venv-ocr\Scripts\python.exe -m pip check
```

If `.venv-ocr` already exists, reuse it after checking its Python version; do not
recreate an environment currently used by another process. No activation or
global Python installation changes are required. Run the application with this
environment's Python as well, for example `.\.venv-ocr\Scripts\python.exe run.py`.
The adapter does not edit environment variables, PATH, or application config.

`requirements-ocr.txt` pins PaddleOCR 3.3.2, PaddleX 3.3.2, PaddlePaddle 3.2.2
(CPU), NumPy 2.2.6, OpenCV contrib 4.10.0.84, Pillow 12.0.0, and pytesseract
0.3.13. PaddleOCR's declared PaddleX range is `>=3.3.0,<3.4.0`, and PaddleX
3.3.2 itself requires this OpenCV version. The PaddlePaddle release provides a
`cp312-cp312-win_amd64` wheel. NumPy 2.2.6 satisfies these packages' published
requirements (including OpenCV's NumPy >=1.26 requirement for Python 3.12).
These are stable release pins selected from upstream metadata. The dated local
validation section above records the native inference actually exercised on this
machine; it does not certify accuracy. Transitive dependencies are not fully locked; retain a successful
environment's resolved package list for reproducible deployment. `pip check`
and the local smoke test below are still required after installation.

## PaddleOCR PP-OCRv5

The adapter explicitly selects `PP-OCRv5_server_det` and
`PP-OCRv5_server_rec`, with `ocr_version="PP-OCRv5"` and `device="cpu"`.
This recognition model supports Traditional Chinese, Simplified Chinese,
English, and Japanese. It does not select a v3/v4 model via the legacy
`chinese_cht` language setting.

The first Paddle recognition call initializes the model and may download the
official model weights into PaddleX's local cache (normally
`%USERPROFILE%\.paddlex\official_models`). Package installation alone does not
provision the weights. An operator should warm up the engine with a synthetic,
non-sensitive image under the **same Windows account as the application** before
using it offline. Ensure that account can read and write its cache. For an
offline deployment, provision the matching complete model cache in advance;
this adapter does not expose arbitrary model-directory configuration. Never
resolve missing weights by silently selecting another OCR model or engine.

Document orientation classification, document unwarping, and text-line
orientation are all disabled. The caller must orient the PIL image before
recognition and handle any mapping back to source document coordinates. The
adapter converts RGB to a contiguous NumPy BGR array without changing dimensions.
Paddle's returned `rec_polys` are reduced to enclosing rectangles in those same
input-image coordinates. A process-local lock covers lazy model initialization,
prediction iteration, and result parsing. Each application process has its own
model instance and memory cost. CPU inference uses `cpu_threads=4` and
`enable_mkldnn=False`, a conservative Windows CPU configuration that may trade
speed for fewer native acceleration dependencies. Detection uses
`text_det_limit_type="max"` and `text_det_limit_side_len=2560`: it caps the long
side instead of enlarging a narrow numeric column to the default minimum short
side. The calling pipeline performs its own 2x upscaling and white padding;
Paddle maps detector coordinates back to that supplied image. The 2560 cap can
still reduce very tall crops, so benchmark small digits and split overly tall
columns upstream if needed. Paddle prediction has no adapter-level timeout;
deployments needing a hard deadline should isolate inference in a worker process.

## Tesseract

For Tesseract-only use, the application's base requirements already include
Pillow, pytesseract, NumPy (table geometry), and PDFium; Paddle is unnecessary. Tesseract's native
executable and the **`chi_tra` and `eng` traineddata** are separate installations.
The technician-certificate grade fallback also uses **`chi_sim` traineddata**;
without it, the grade remains marked for manual confirmation.
Use a local installation from the sources linked by the Tesseract project.

Verify the executable and language files with its absolute path, for example:

```powershell
& 'C:\Program Files\Tesseract-OCR\tesseract.exe' --version
& 'C:\Program Files\Tesseract-OCR\tesseract.exe' --list-langs
```

If Tesseract is not already on PATH, set the executable only within the launching
Python process before calling `recognize`:

```python
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

Store `chi_tra.traineddata`, `chi_sim.traineddata`, and `eng.traineddata` in that installation's tessdata
directory. This does not require a permanent system PATH or environment-variable
change. The adapter uses `image_to_data`, language `chi_tra+eng`, `--psm 6`, and a
60-second subprocess timeout. Page segmentation mode 6 assumes a block of text;
table reconstruction and alternative image preparation belong to the caller.

## Contract and local smoke test

```python
from PIL import Image, ImageDraw
from app.services.ocr_engines import recognize

image = Image.new("RGB", (640, 160), "white")
ImageDraw.Draw(image).text((20, 40), "OCR smoke test 123", fill="black", font_size=32)
tokens = recognize(image, engine="paddleocr")  # May download models on first call.
# tokens = recognize(image)                  # Tesseract is the default.
assert tokens, "No text detected; investigate the local runtime before deployment"
assert all(len(token["bbox"]) == 4 for token in tokens)
```

Each result is `{"text": str, "bbox": [left, top, right, bottom], "confidence":
float | None}`. Coordinates are floats, relative to the supplied PIL image, with
origin at its top left. Confidence is normalized to 0..1; negative, non-finite,
missing, or non-numeric confidence becomes `None`. Paddle generally returns
whole text lines and Tesseract words; callers must not assume equal segmentation.
Recognition scores are not probabilities of correctness or comparable across
engines. Low and zero confidence text is retained. Paddle's recognition threshold
is explicitly zero; detector thresholds still determine which regions exist.
Tesseract's blank structural TSV rows are excluded. A blank page can return `[]`;
malformed or incomplete results raise errors instead of silently truncating rows.

Public errors use Traditional Chinese setup hints, not the underlying exception text,
recognized text, or document paths. Do not print tokens for private documents or
log underlying exception contexts. Third-party libraries may emit their own
diagnostic logs; configure deployment logging separately.

Run the stub contract tests without invoking an OCR binary or downloading models:

```powershell
.\.venv-ocr\Scripts\python.exe -m pytest tests/test_ocr_engines.py -q
```

Paddle-specific tests require NumPy and skip if it is missing. These tests verify
adapter behavior, not recognition quality. **Actual accuracy must be benchmarked**
on representative, labelled Traditional Chinese school documents: include
low-resolution scans, tables, rotated pages, mixed English, numerals, and difficult
fonts. Measure text error rates and downstream course/score extraction accuracy,
as well as CPU latency, memory and review effort. A successful smoke test or an
upstream benchmark does not establish accuracy on this application's documents.

## Upstream references

- [PaddleOCR 3.3.2 API, result fields and model language support](https://www.paddleocr.ai/v3.3.2/en/version3.x/pipeline_usage/OCR.html)
- [PaddleOCR 3.3.2 dependency constraints](https://github.com/PaddlePaddle/PaddleOCR/blob/v3.3.2/pyproject.toml)
- [PaddleX 3.3.2 dependency pins](https://github.com/PaddlePaddle/PaddleX/blob/v3.3.2/setup.py)
- [PaddleX BGR ndarray reader](https://github.com/PaddlePaddle/PaddleX/blob/v3.3.2/paddlex/inference/common/reader/image_reader.py)
- [PaddleX recognition threshold comparison and input-coordinate result polygons](https://github.com/PaddlePaddle/PaddleX/blob/v3.3.2/paddlex/inference/pipelines/ocr/pipeline.py)
- [PaddlePaddle 3.2.2 Windows Python 3.12 wheel](https://pypi.org/project/paddlepaddle/3.2.2/#files)
- [pytesseract configuration and timeout API](https://github.com/madmaze/pytesseract)
- [Tesseract installation guidance](https://tesseract-ocr.github.io/tessdoc/Installation.html)
- [Official Tesseract language data](https://github.com/tesseract-ocr/tessdata)

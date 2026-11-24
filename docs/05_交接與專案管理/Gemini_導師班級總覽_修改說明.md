# 導師班級總覽與 Excel 匯出修改說明

## 1. 改了哪些檔案

### 新增檔案
- `app/services/teacher_export.py`：負責班級總覽資料組裝（`build_class_overview_rows`）以及產生 Excel（.xlsx）檔案之服務（`export_class_overview_xlsx`）。
- `app/static/js/teacher-roster.js`：純 JavaScript 實作的班級總覽表即時篩選（學號／姓名搜尋、「只看有待確認」核取方塊）與表頭點擊排序（支援字串語系排序與數值排序）。
- `docs/05_交接與專案管理/Gemini_導師班級總覽_修改說明.md`：本份修改與交接說明文件。

### 修改檔案
- `app/services/audit_service.py`：在 `ACTION_LABELS` 註冊導師匯出操作標籤 `"teacher.class_overview_export": "匯出班級總覽 Excel"`。
- `app/routes/teacher.py`：新增路由 `GET /teacher/class-overview.xlsx`，加入導師權限驗證、負責班級篩選檢查、操作紀錄登記與 .xlsx 檔案串流回傳。
- `app/routes/main.py`：調整 `teacher_dashboard` 路由，呼叫 `build_class_overview_rows` 統一提供頁面所需的完整 9 欄總覽資料，並完整保留原本之資料鍵值以維持現有功能相容性。
- `app/templates/dashboard.html`：將導師端首頁的「本班學生」名單改版為 9 欄「班級總覽表」，加入上方工具列（即時搜尋框、只看有待確認勾選框、匯出 Excel 按鈕），每列提供前往學生詳細頁面之連結，並引入 `teacher-roster.js`。
- `app/static/css/design-system.css`：於檔案結尾追加樣式，使用 `[data-page="teacher-dashboard"]` 與 `[data-page="work-dashboard"] [data-work-role="teacher"]` 選擇器，實作手機橫向捲動下的前兩欄（學號、姓名）`position: sticky` 固定、至少 44px 觸控點擊區域，並恪守無動畫、無漸層、無斜體、無膠囊圓角之工作層效率風格。

---

## 2. 做了什麼

### A. 班級總覽表（網頁端）
1. **九大欄位呈現**：
   - 學號：學生學號（`mono` 字體）。
   - 姓名：學生顯示名稱（粗體）。
   - 班級：學生所屬班級名稱。
   - 送審校系：多個校系以「、」分隔，點擊校系名稱可直接錨點跳轉至該學生對應校系，並完整保留 `data-target-progress` 屬性。
   - 自傳狀態：依據學生各目標校系之最新草稿（`latest_draft`）與最新審核紀錄（`latest_review`）判斷，分為「未起稿」、「草稿」、「已送審」、「導師請修改」、「導師已確認」；若無目標校系且無草稿則顯示為「—」。
   - 自傳字數：計算最新自傳草稿中所有段落之字元總數（排除空白字元與換行符號），無草稿時顯示為 `0`。
   - 學分缺口或畢業門檻狀態：嚴格沿用 `graduation_check_service.assess` 與 `graduation_check_service.overall_result` 現有判定結果，具體呈現「各項目都已達成」、「有缺口（列出缺口項目如必修差X學分）」、「有項目資料不足或待確認」或「修課中」，絕不自創審查規則。
   - 證照數：取自歷程累計之證照筆數（數值）。
   - 待確認送審數：若大於 0，顯示待審件數並提供直達送審區之連結標籤；若為 0 則顯示 `0`。
   - 操作：每列右側附有「前往」按鈕，連結至 `teacher.student_detail`。
2. **純 JavaScript 排序與篩選**（`teacher-roster.js`）：
   - 點擊任一欄位表頭按鈕，即可切換升冪（▲）與降冪（▼）排序。針對自傳字數、證照數、待確認數採用數值比較，針對學號、姓名等採用正體中文（`zh-Hant`）字串比對。
   - 上方即時文字搜尋框：輸入學號或姓名即時過濾顯示列。
   - 「只看有待確認」核取方塊：勾選後僅列出待確認送審數大於 0 的學生。
   - 篩選無符合條件時顯示「沒有符合篩選條件的學生。」友善提示列。
3. **響應式排版與 Sticky 固定欄**：
   - 表格放置於 `teacher-roster-wrap` 橫向捲動容器內。
   - 第一欄（學號）與第二欄（姓名）在手機或窄螢幕左右捲動時固定在畫面左側（`position: sticky`），第二欄右側加入邊框與輕微陰影區隔，提升導師查閱體驗。

### B. Excel 匯出（.xlsx）
1. **專屬路由**：
   - 路由為 `GET /teacher/class-overview.xlsx`，掛載 `@role_required("teacher")`。
   - 限制導師僅能匯出自身負責班級（`advised_classes`）。支援帶入 `?class_name=` 參數進行單班篩選，若帶入非負責班級則回傳 HTTP 400。
   - 回傳 `Content-Disposition: attachment; filename="class-overview.xlsx"`，以 ASCII 檔名確保跨平臺相容性。
2. **工作表「班級總覽」**：
   - 匯出 9 個欄位：學號、姓名、班級、送審校系、自傳狀態、自傳字數、學分缺口或畢業門檻狀態、證照數、待確認送審數。
   - 標題列粗體呈現。
   - 凍結首列與前兩欄（openpyxl `freeze_panes = "C2"`）。
   - 依欄位文字長度設定適中欄寬，並啟動 Excel 原生自動篩選（`auto_filter`）。
3. **工作表「統計」**：
   - 完全使用 Excel 動態公式，不寫死固定數值：
     - 總人數：`=COUNTA('班級總覽'!A2:A{last_row})`
     - 已送審人數：`=COUNTIF('班級總覽'!E2:E{last_row}, "已送審")`
     - 平均自傳字數：`=AVERAGE('班級總覽'!F2:F{last_row})`
     - 自傳字數標準差：`=STDEV('班級總覽'!F2:F{last_row})`
     - 尚未起稿人數：`=COUNTIF('班級總覽'!E2:E{last_row}, "未起稿")`
   - 公式參照「班級總覽」之資料儲存格範圍，導師日後在 Excel 中修改資料可即時自動重算。
4. **個資規範與操作紀錄**：
   - 匯出內容不含自傳全文、不含缺曠資料、不含電話或地址，嚴格恪守個資規範。
   - 匯出動作呼叫 `audit_service.record`，在 `audit_logs` 留下中文操作標籤「匯出班級總覽 Excel」及篩選班級代碼。

### C. 風格規範與相容性維護
- 不使用斜體標題、不使用米白背景、不使用圓角膠囊按鈕、不使用紫色漸層。
- 所有按鈕、輸入框、表頭排序按鈕之可點擊高度均達到至少 44px。
- 完整保留既有的 `data-tour` 屬性（如導覽順序 1～4）、`data-grad-overview`、`data-class-roster`、`data-target-statistics`、`data-pending-link` 以及 `<tr class="row-link">` 標籤結構，確保既有測試案例全數相容。

---

## 3. 沒做到什麼

1. **依限制未執行之操作**：
   - 本次作業遵守核心限制：未執行任何 `git` 指令、未進行 `git commit`、未執行測試指令（`pytest`）、未安裝外部套件、未修改資料庫模型（Models / Migrations）。
2. **業務範圍邊界**：
   - 依專案個資要求，未將自傳全文、出缺席缺曠紀錄、學生聯絡電話或戶籍地址納入 Excel 匯出或總覽表。
   - 未在導師總覽表加入裝飾性動畫、旋轉圖示或花俏統計圖卡，維持教師頁以工作效率為優先之純淨設計。

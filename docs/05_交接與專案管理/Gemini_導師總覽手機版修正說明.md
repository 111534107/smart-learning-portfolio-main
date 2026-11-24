# 導師班級總覽表手機版修正說明

## 1. 改了哪些檔案

### 修改檔案
- `app/templates/dashboard.html`：
  - 在導師班級總覽工具列（`.teacher-roster-toolbar`）新增手機專用的排序下拉選單（`#roster-sort-select`）與升降冪切換按鈕（`#roster-sort-order-btn`）。
  - 在班級總覽表（`#teacher-roster-table`）的各儲存格（`td`）提供標準短標籤 `data-label`（如「送審校系」、「自傳狀態」、「自傳字數」、「證照數」、「待確認」、「畢業門檻」），避免被全站腳本注入包含排序符號 `↕` 的長標籤。
  - 在姓名儲存格內嵌入手機專用行內學號與班級標記（`.roster-mobile-inline`），使卡片頂端可一行呈現完整學生身分。
  - 保留所有既有 `data-tour` 屬性、表單結構、連結與 Python 傳遞變數。

- `app/static/js/teacher-roster.js`：
  - 提取共用排序邏輯為 `executeSort(sortKey, sortType, sortDir)`。
  - 支援手機下拉選單（學號、姓名、待確認、自傳字數）與升降冪切換按鈕，並與桌機表頭排序按鈕雙向連動同步狀態。
  - 優化姓名與學號讀取機制（優先讀取 `data-name` 或姓名文字節點），確保即使在手機卡片模式下單獨的學號與班級儲存格隱藏時，即時搜尋與排序仍 100% 精準。

- `app/static/css/design-system.css`：
  - 重構導師總覽表（`[data-page="teacher-dashboard"]` 與 `[data-page="work-dashboard"] [data-work-role="teacher"]`）的響應式樣式。
  - **桌機斷點（≥ 768px）**：維持現有完整表格排版、水平滾動、左側學號與姓名固定欄（`position: sticky`）、表頭點擊排序；隱藏手機排序選單與行內重複資訊。
  - **手機斷點（< 768px）**：將每列轉換為約 200px 高度的緊湊卡片；消除外層雙重外框與虛線框；解決姓名直排擠壓問題；提供 2 欄格線排版與 44px 滿版操作按鈕；防止產生左右捲動或遮擋內容。

- `docs/05_交接與專案管理/Gemini_導師總覽手機版修正說明.md`：本份修正與交接說明文件。

---

## 2. 問題根因分析（全站表格卡片化衝突）

1. **姓名儲存格擠壓為極窄直排與虛線外框**：
   - 全站腳本 `components.js` 會自動對教職員頁面的表格加上 `.table--stack`，並在窄螢幕（全站預設 `@media (max-width: 640px)`）將 `td` 轉為 `display: grid; grid-template-columns: 5.5em 1fr;`。
   - 上一輪新增的桌機左側固定欄樣式（`sticky-col-2`）設定了 `min-width: 6.5rem; max-width: 6.5rem; position: sticky; left: 6.5rem; border-right: 1px solid; box-shadow: ...`。
   - 手機寬度下，姓名欄寬度被硬性鎖定在 `6.5rem`（約 104px），而在卡片內部 `::before` 佔去 `5.5em`（約 88px），剩下的 `1fr` 僅剩 16px，導致中文字「張小華」被擠成一字一行（張／小／華）的極窄直排；同時桌機的 `border-right`、`box-shadow` 與全站卡片的 `border-top: 1px dashed` 疊加，形成浮動的怪異虛線外框。

2. **每個欄位標籤皆帶有「↕」排序箭頭**：
   - `components.js` 會讀取 `thead th` 的 `textContent` 作為 `data-label`。因桌機表頭按鈕內含 `<span class="sort-indicator">↕</span>`，導致抓取到的標籤變成「學號 ↕」、「姓名 ↕」、「待確認送審數 ↕」。
   - 若 `td` 上原本未定義乾淨的 `data-label`，卡片內的標籤就會雜亂地帶著排序箭頭。

3. **「待確認送審數」標籤與數字擠壓、膠囊樣式過寬**：
   - 標籤「待確認送審數 ↕」（8 個字元）在全站預設的 `5.5em` 格線欄寬內無法容納，產生換行並與後方的膠囊按鈕擠壓。

4. **手機捲動長度過長（3 位學生達 4000px）**：
   - 全站 `.table--stack` 將 10 個欄位逐一垂直堆疊，每格均帶上下邊距與虛線分隔，一張卡片高度超過 1300px，3 位學生即佔用數千像素，造成導師閱覽負擔過大。

---

## 3. 具體修正作法

### A. 結構層（`app/templates/dashboard.html`）
1. **補齊乾淨的 `data-label` 短標籤**：
   - 送審校系：`data-label="送審校系"`
   - 自傳狀態：`data-label="自傳狀態"`
   - 自傳字數：`data-label="自傳字數"`
   - 證照數：`data-label="證照數"`
   - 待確認送審數：`data-label="待確認"`
   - 畢業門檻狀態：`data-label="畢業門檻"`
   - 姓名與操作欄位：透過 CSS 隱藏 `::before`，不顯示多餘標籤。
   - 由於 HTML 已明確定義 `data-label`，`components.js` 的 `if (!cell.dataset.label)` 判斷會主動跳過，徹底阻絕 `↕` 符號滲入。

2. **第一行身分資訊整合**：
   - 在姓名欄內增加 `.cell-student-name__text`（姓名）、`.cell-student-no-inline`（學號）與 `.cell-class-name-inline`（班級）。
   - 桌機模式下行內學號與班級隱藏；手機模式下顯示，讓學生身分在第一行完整呈現。

3. **手機專用排序工具區塊**：
   - 在工具列中加入 `<div class="teacher-roster-sort" id="roster-mobile-sort">`，提供學號、姓名、待確認、自傳字數 4 項主要排序依據之 `<select>`，以及切換升冪／降冪之 `<button>`。

### B. 行為層（`app/static/js/teacher-roster.js`）
1. **雙向排序同步**：
   - 抽取出核心 `executeSort(sortKey, sortType, sortDir)` 排序函式。
   - 桌機點選表頭按鈕時，同步更新手機端下拉選單的值與升降冪按鈕狀態。
   - 手機端改變下拉選單或點選升降冪按鈕時，同步更新桌機表頭的 `aria-sort` 與指標箭頭（▲／▼／↕）。
2. **精確資料讀取**：
   - 姓名排序與搜尋優先使用 `data-name` 或 `.cell-student-name__text`，不受手機行內學號與班級文字干擾。
   - 學號與數值欄位即使在手機模式下未單獨佔位，依然能從對應儲存格讀取資料，維持純前端即時搜尋與排序的 100% 正確性。

### C. 樣式層（`app/static/css/design-system.css`）
1. **桌機端（`@media (min-width: 768px)`）**：
   - 完全維持原標準表格排版與行為。
   - 左側學號（`sticky-col-1`）與姓名（`sticky-col-2`）固定於滾動視窗左側。
   - 手機專用排序選單與行內學號班級自動隱藏（`display: none !important`）。
2. **手機端（`@media (max-width: 767px)`）**：
   - **清除多餘雙重外框與水平捲動**：`.teacher-roster-wrap` 設為無邊框、無背景、`overflow: visible`，卡片外框回歸各列本身。
   - **重設全站干擾樣式**：
     - 重設 `table.teacher-roster-table td` 為 `display: flex; position: static !important; max-width: none !important; min-width: 0 !important;`。
     - 移除虛線分隔（`border: none !important;`）。
   - **緊湊卡片版面（高度控制在約 200px 內）**：
     - 卡片 `tr.row-link` 採用 CSS Grid：`grid-template-columns: minmax(0, 1fr) minmax(0, 1fr)`，內距 `0.65rem 0.75rem`。
     - 若有待確認資料，卡片左側加上微幅醒目提示（`border-left: 3.5px solid var(--warn)`），無任何雙重外框。
   - **卡片第一行（跨 2 欄）**：
     - 姓名粗體（1rem，`var(--ink)`）、學號（等寬字體，`var(--muted)`）、班級（`var(--muted)`）橫向排開，絕不換行擠成直排。
   - **中間 2 欄格線（6 項核心指標）**：
     - 左欄：送審校系（order: 2）、自傳字數（order: 4）、待確認送審數（order: 6）。
     - 右欄：自傳狀態（order: 3）、證照數（order: 5）、畢業門檻狀態（order: 7）。
     - 短標籤呈現（`attr(data-label) "："`），字級 `0.75rem`，顏色 `var(--muted)`。
     - 待確認膠囊縮小為適當尺寸（`fit-content`），不遮擋其他內容。
   - **最底滿版操作按鈕**：
     - 「前往」按鈕跨滿整行（`grid-column: 1 / -1; order: 8`），高度符合觸控標準 `min-height: 44px`，背景為深墨色（`var(--ink)`），字體為紙色（`var(--sheet)`）。
3. **外觀規範與色彩相容**：
   - 全面採用專案原生 CSS 變數（`var(--sheet)`, `var(--ink)`, `var(--line)`, `var(--muted)`, `var(--warn)` 等），淺色與深色主題皆清晰對比。
   - 杜絕 AI 預設風格（無紫色漸層、無斜體、無圓角膠囊按鈕、無多餘統計卡片）。
   - 全站無左右破版或水平捲動，無 `position: fixed` 橫條遮擋內容。

---

## 4. 變更驗證與相容性說明

- **Python 程式碼**：未修改任何 Python 檔案，既有路由、資料結構與權限邏輯未受影響。
- **導覽與輔助功能**：導師首頁既有 `data-tour` 屬性與各連結錨點（`#teacher-targets`, `#teacher-target-{id}`）完整保留。
- **其他表格相容性**：修改選擇器嚴格限定於導師班級總覽表（`[data-page="teacher-dashboard"]` 與 `[data-page="work-dashboard"] [data-work-role="teacher"]`），全站科辦端、主任端、管理員端之 `.table--stack` 行為保持不變。

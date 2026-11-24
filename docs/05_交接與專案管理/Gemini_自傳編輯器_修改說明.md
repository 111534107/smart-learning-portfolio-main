# Gemini 自傳編輯器（Canva 式操作動線）修改說明

## 1. 修改檔案清單
1. `app/templates/student_autobiography.html`
   - 重構「第二步：逐段修改草稿」區塊（有 draft 且非 asking 階段）。
   - 新增頂部固定工具列（含版本標示、字數、上一段／下一段、更多工具、固定置頂儲存按鈕、手機版編輯／預覽模式切換）。
   - 新增手機版橫向可捲動段落小標籤（`.canva-mobile-chips`）。
   - 建立三欄主工作區（`.canva-workspace`）：左欄段落目錄（`.canva-outline`）、中欄單段編輯區（`.canva-editor-column`）、右欄整份即時紙張預覽（`.canva-preview-column`）。
   - 將長篇說明（AI 不能做的事、已確認資料盤點、Google 文件、版本提示）整合進「說明與工具」摺疊抽屜（`.canva-aux-drawer`），預設收起。
   - 在 `scripts` 區塊載入 `canva-editor.js`。
2. `app/static/js/canva-editor.js`（全新建立）
   - 負責 Canva 編輯器的狀態管理與互動。
   - 漸進增強：JS 執行時在容器加上 `.has-canva-editor`，無 JS 時完全不影響原版佈局。
   - 支援桌機目錄切換、手機橫向標籤切換、工具列與段落下方的上一段／下一段跳轉。
   - 支援手機版「編輯」與「預覽」雙模式切換。
   - 監聽 `textarea` 輸入事件，即時同步更新右側紙張預覽文字與每段／全部字數統計。
   - 支援點擊預覽區段落直接跳至該段編輯，手機版點擊預覽段落會自動切換回編輯模式並聚焦輸入框。
   - 支援網址 hash 錨點（如 `#paragraph-2`）直接定位。
   - 與 `bio-pieces.js` 連動：切換段落時同步觸發 `focus`，確保素材庫點選「放進去」精準插入至當前段落。
3. `app/static/css/design-system.css`
   - 於檔案結尾追加專屬樣式，所有選擇器一律以 `[data-page="student-autobiography"]` 開頭，確保不影響其他頁面。
   - 實作桌機（≥ 900px）三欄式網格排版與黏性側欄（sticky outline & preview sheet）。
   - 實作手機（< 900px）首屏寫字排版（flex order 將工具列與段落置前、說明抽屜排於後方）。
   - 手機版底部留白：給予 `.page` 與 `.canva-container` 至少 180px 的底部 padding，避開底部固定列、小助手按鈕與導覽邀請條。
   - 手機版 `.tour-invite` 限制覆蓋：在此頁將 `.tour-invite` 設為 `position: static !important`，取消浮動覆蓋。
   - 樣式限制嚴格遵循：不使用斜體、不使用米白卡片、不使用 01/02 步驟編號、不使用圓角膠囊按鈕（`border-radius: 999px`）、不使用紫色漸層、無多餘統計卡片；色彩與字級全數取自系統設計變數。
   - 無障礙設計：所有可點擊元件（按鈕、標籤、目錄列、摘要抽屜）最小高度均符合 44px 觸控標準；支援 `@media (prefers-reduced-motion: reduce)` 取消動態轉場。
4. `docs/05_交接與專案管理/Gemini_自傳編輯器_修改說明.md`（本交接文件）

---

## 2. 做了什麼

### A. 桌機端（寬度 ≥ 900px）：Canva 式三欄佈局
- **左欄目錄（Table of Contents）**：
  - 清單呈現每個段落的序號、標題與目前即時字數。
  - 當前編輯中的段落具備醒目的強調樣式（`--accent-soft` 底色、`--accent` 邊線與加粗字體）。
  - 點擊任意項目即可切換至該段落，輸入框自動獲得焦點。
- **中欄編輯區（Single Paragraph Editor）**：
  - 一次只顯示選中的那一段，擺脫過往 8 個段落一口氣向下堆疊的壓迫感。
  - 段落頂部清楚顯示「第 X / Y 段」步驟指標與目前標題、段數字數。
  - 保留所有業務元件：主張標籤、`textarea` 輸入框、圖片上傳區（`data-image-box`）、導師意見引用區、師生討論區（`cm.paragraph_block`）、證據／疑點／建議分析卡片（`.paragraph-review`）、未歸屬討論（`cm.orphan_block`）、以及素材拖曳抽屜（`bio_pieces`）。
  - 段落底部提供直覺的「← 上一段」與「下一段 →」按鈕。
- **右欄即時預覽（Paper Sheet Live Preview）**：
  - 以紙張文件風格排版（`--sheet` 背景、`--shadow-sheet` 投影、襯線字體、微型抬頭），呈現完整自傳的成品質感。
  - 輸入文字時即時監聽並更新預覽內容與字數，打字零延遲。
  - 預覽中的每一段均為可點擊元件（提供懸浮提示與指標樣式），點擊即直接跳至中欄對應段落編輯。

### B. 手機端（寬度 < 900px）：首屏直接寫字
- **首屏立即可寫**：
  - 長篇說明與工具全部收進預設收起的抽屜，並在手機版排於編輯區後方，開啟頁面時直接看見當前段落輸入框。
- **橫向可捲動段落小標籤（Chips）**：
  - 位於頂端工具列下方，支援左右滑動，選中段落自動平滑捲動至水平置中位置。
  - 每個標籤顯示段落編號、標題與即時字數，高度均達 44px。
- **「編輯／預覽」雙模式切換**：
  - 頂端工具列內建分頁按鈕，可一鍵在「單段編輯」與「紙張全篇預覽」之間無縫切換。
  - 在預覽模式下點擊任一段落，會自動切回編輯模式並精準定位至該段輸入框。
- **避開底部固定覆蓋物**：
  - 透過 CSS 為手機版底部加入至少 180px 空白（`padding-bottom: max(180px, calc(180px + env(safe-area-inset-bottom)))`）。
  - 在本頁的手機版將 `.tour-invite` 覆蓋為 `position: static !important; transform: none !important;`，使其不再浮動於底部遮蔽輸入框。

### C. 儲存與導覽邏輯
- **工具列固定置頂**：
  - 儲存按鈕（`button[type="submit"][form="draft-form"]`）固定置於頂部工具列右側，隨時可按，不需滾動到底部。
  - 工具列整合版本序號、總字數統計、段落快速導航（上一段／下一段）與更多功能選單（版本紀錄、重新回答問題）。
- **保留導覽引導（Data Tour）**：
  - 完整保留 `data-tour` 與 `data-tour-order`（第一段輸入框為步驟 1、審查依據為步驟 2、固定儲存鈕為步驟 3）。

### D. 表單完整性與無 JavaScript 降級支援（Progressive Enhancement）
- 所有段落的 `textarea`（`name="paragraph_N"`、`data-char`、`data-autosize`、`aria-label`）均始終保留於 DOM 內，未選中段落僅以 CSS（`display: none`）隱藏，表單提交時 100% 完整送出所有段落數據。
- 無 JS 環境下，由於容器未被加上 `.has-canva-editor` class，頁面會自動保持原有全段落垂直展開的傳統模式，底部的儲存按鈕與說明文字皆完全正常運作。

---

## 3. 還沒做到什麼（保留限制與後續可擴充項目）
1. **本機離線即時快照（LocalStorage Auto-Draft）**：
   - 目前文字未儲存提醒由 `autobiography-unsaved.js` 與頂端狀態維持監控，尚未實作使用者斷網或不小心關閉分頁時的瀏覽器本機 LocalStorage 暫時快照恢復功能。
2. **預覽區圖片縮圖呈現**：
   - 目前右側紙張即時預覽著重於自傳內文字內容與結構的毫秒級同步排版，段落中已上傳的圖片目前僅在編輯區的圖片管理方塊中呈現，尚未鏡射縮圖至右側預覽紙張內。
3. **段落自由拖曳重排（Drag & Drop Reordering）**：
   - 目前自傳段落順序依據校系簡章評分加權引導題由高至低固定排列，尚未提供學生自由拖曳對調段落順序的自訂功能（若要支援需後端資料庫資料結構與儲存 API 擴充支援）。

---

## 4. 第二輪修正（針對手機 375px 尺寸與深色外觀的調優）

依據實際手機畫面（375px）與深色主題（`data-theme="dark"` / `data-ui="student-v2"`）檢視反饋，完成以下全面修正：

### 1. 深色外觀配色變數化（徹底消除寫死白色背景與淺色字對比不足）
- **問題根因**：既有 `shell.css` 中曾以 `html .draft__paragraph { background: #ffffff; color: #000000; }` 及 `textarea { background: #ffffff !important; }` 強制覆蓋，但在深色外觀下，系統文字變數 `--ink` 為淺米白色（`#ece3d6`），導致白底淺字難以辨認。
- **解決方案**：
  - 在 `app/static/css/design-system.css` 透過高特異性選擇器 `[data-page="student-autobiography"] .draft__paragraph` 全面重設。
  - 將卡片背景改為 `var(--sheet)`、主要文字為 `var(--ink)`、邊框為 `var(--line)`、textarea 背景為 `var(--paper)`、審查區塊為 `var(--paper)`。
  - 拔除所有新增樣式中的寫死顏色（不寫死 `#fff`、`#000`、`white`、`black`），儲存按鈕文字改用 `var(--on, var(--sheet))`，在淺色模式與深色外觀下皆自動呈現高對比度。

### 2. 手機版橫向段落標籤（.canva-mobile-chips）低調化與資訊精簡
- **問題根因**：原橫向標籤在選中時整條滿版呈現亮藍色，且標題過長易被邊界切斷。
- **解決方案**：
  - 調整 `app/templates/student_autobiography.html` 標籤模板結構：以 Jinja2 計算短標題，顯示格式統一為「序號＋短標題（最多 8 字，超過 8 字加…）＋字數」，完整標題保留於 `title` 屬性。
  - 樣式調整為與系統一致的低調卡片風格：平時底色為 `var(--sheet)`、線條為 `var(--line)`；選中（`.is-active`）時採用淡雅的 `var(--accent-soft)` 底色與底部 3px 的 `var(--accent)` 明顯底線，文字加粗，不再以大片飽和亮色刺激視覺。
  - 確保標籤觸控高度達到至少 44px（`min-height: 44px`），並維持流暢平滑的橫向捲動（`overflow-x: auto; scroll-snap-type: x mandatory`）。

### 3. 預覽模式（手機與桌機右欄）文件化與層級分明
- **問題根因**：預覽區段落標題與內文字級大小相近，缺乏正式文件的閱讀層級與舒適行距。
- **解決方案**：
  - 將 `.canva-preview-sheet` 打造為正式公文/備審紙張質感：頂部設置居中文件大標題（`var(--fs-lg)`）與加粗分隔線。
  - 段落標題（`.canva-preview-item__title`）字級提升至 `1.05rem`（加粗 700），並在下方加入微細分隔線，與內文拉開層次。
  - 內文字級設為標準閱讀尺寸（`var(--fs-base)`），行距擴充至 `line-height: 1.85`，字型採用 `var(--font-serif)`，排版支援兩端對齊（`text-align: justify`），顯著提升閱讀舒適感。
  - 當前選中段落採用 `var(--accent-soft)` 底色與左側 4px 邊線（`var(--accent)`），定位直覺明確。

### 4. 段落標題（.canva-paragraph-header__title）單行省略與手機字級約束
- **解決方案**：
  - 在 `app/templates/student_autobiography.html` 中為段落標題 `h2` 增加 `title="{{ paragraph.title }}"` 屬性，確保懸浮與無障礙讀取完整標題。
  - 在 CSS 中設定 `white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%;`，並將父層容器加上 `min-width: 0`，防止 flex 溢出導致文字折行。
  - 在手機螢幕寬度（< 900px）限制標題字級為 `1.05rem`，嚴格不超過 `1.1rem`。

### 5. 素材區塊手機響應式收合（避免 5000px 長頁面）
- **問題根因**：原素材庫（`bio_pieces`）資料量大時在手機垂直堆疊，導致整頁長度高達數千像素，嚴重影響使用者寫作專注力。
- **解決方案**：
  - 在 `app/templates/student_autobiography.html` 將素材庫包裹在 `<details class="canva-materials-details" data-canva-materials>` 抽屜內，標題為「素材：你自己寫的文字與已確認資料」。
  - 在 `app/static/js/canva-editor.js` 透過 `window.matchMedia("(min-width: 900px)")` 建立響應式狀態同步：
    - 桌機（≥ 900px）：自動設定 `materialsDetails.open = true`，CSS 隱藏 summary，外層無邊框無底色，完全維持桌機原有展開排版。
    - 手機（< 900px）：預設收合（`open = false`），summary 呈現獨立抽屜列（高度至少 44px，含展開指示符 ＋/－），展開後才可查看素材，有效杜絕長頁面問題。


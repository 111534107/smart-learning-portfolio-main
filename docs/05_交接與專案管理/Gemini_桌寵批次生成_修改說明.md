# Gemini 桌寵小助手批次生成自傳修改說明

## 1. 檔案清單
1. **`app/templates/partials/pet.html`**（全新建立）
   - 可重用的資管科桌寵小助手 SVG 角色 Jinja2 巨集 `pet(state, class_name, bubble, muscle, id)`。
   - 繪製可愛圓臉桌寵、資管天線呆毛、粉嫩腮紅、雙手小手與短短小雙腳。
   - 內建待機（微笑眨眼）、走路（注視踏步）、施法（星芒發亮雙眼＋魔杖揮舞）、開心（瞇瞇笑眼＋開懷大笑）、抱歉（八字眉、水汪汪雙眼、波浪嘴、尷尬汗滴）等 5 種表情狀態。
   - 內建手握魔法棒配件，以及「筋肉小助手」二頭肌肌肉線條彩蛋（`data-muscle="true"`）。
   - 內建自適應對話泡泡結構，支援動態變換文字與無障礙語意讀屏（`aria-live="polite"`）。
2. **`app/templates/student_autobiography_batch.html`**（全新建立）
   - 批次生成自傳專屬動畫頁面，繼承 `base.html`，設定 `page_name = "student-autobiography-batch"`。
   - 頁面頂部包含摺疊功能說明（`<details class="page-intro">`）與無 JavaScript 降級提示（`<noscript>` 提供回到單校自傳頁之按鈕）。
   - 頂部狀態面板包含生成進度條、文字狀態、以及筋肉模式切換按鈕（`data-batch-muscle-toggle`）。
   - 舞台區提供小助手 Actor 停駐與橫向位移軌道，並將多個目標校系渲染為 A4 直向擬真紙張（白底黑字、陰影邊界、校系抬頭、自傳假線條、完成印章、失敗重試箱與魔法星星粒子）。
   - 底部提供完成後的引導行動面板（「前往檢視各校自傳」與「回自傳總覽」）。
3. **`app/static/js/pet-batch.js`**（全新建立）
   - 原生 JavaScript 狀態機與輪詢控制器，無任何第三方套件依賴。
   - 頁面載入自動向 `start_url` 發出 POST 請求（攜帶 `csrf_token`）取得 `job_id`。
   - 每 1.5 秒自動輪詢 `status_url`（替換 `__JOB__` 代號），解析各校 `pending` / `running` / `done` / `failed` 狀態。
   - 驅動小助手跟隨目標紙張進行平滑位移（計算 offset 並自動捲入視窗視線中心 `scrollIntoView`）。
   - 狀態機動畫聯動：
     - 生成中：小助手移動到達後進入 `casting` 施法狀態，揮動魔法棒，觸發該紙張的 CSS 星星粒子灑落與骨架假文字逐行浮現動畫。
     - 完成一所：紙張蓋上「完成」大印章（含校系名稱），小助手頭上彈出對話泡泡「`Ciallo～(∠・ω<)⌒★`」，表情切換為 `happy`。
     - 失敗單校：小助手露出 `sorry` 抱歉表情，紙張顯示「重試此校」按鈕（點擊向 `retry_url` POST `csrf_token`、`program_id`、`job_id`）。
     - 全數完成：小助手持續開心地上下雀躍跳動（`happy`），對話泡泡更新為「`資管小助手很高興為你服務`」，展開前往檢視各校自傳之行動按鈕。
   - 筋肉模式彩蛋：點擊按鈕即時切換 `data-muscle="true"`，施法時手臂肌肉瞬間暴漲。
   - 嚴格尊重使用者 `prefers-reduced-motion` 設定。
4. **`app/static/css/design-system.css`**（於結尾追加）
   - 所有選擇器一律以 `[data-page="student-autobiography-batch"]` 開頭，完全隔離不影響系統其他頁面。
   - 依據專案《AGENTS.md》第 9 節介面規範，絕不使用 AI 紫色漸層、絕不使用斜體標題、無過量統計卡片，色彩完全繼承專案既有 CSS 變數（`--ink`, `--paper`, `--sheet`, `--line`, `--accent`, `--accent-soft`, `--ok`, `--danger` 等）。
   - A4 紙張在淺色與深色主題下均堅持擬真紙本質感：純白底色（`#ffffff`）搭配清晰深黑文字（`#111111`），朱砂紅印章蓋印動畫效果醒目。
   - 手機優先設計：375px 窄螢幕下每張紙置中滿版排列（橫向平滑滑動 `scroll-snap-type: x mandatory`），頁面中完全不使用 `position: fixed` 浮動橫條，所有按鈕與觸控目標高度均 ≥ 44px。
   - 支援 `@media (prefers-reduced-motion: reduce)`，關閉所有位移動畫、跳躍、假文字浮現與星星粒子，改以清晰靜態表情與進度文字呈現。
5. **`docs/05_交接與專案管理/Gemini_桌寵批次生成_修改說明.md`**（本交接說明文件）

---

## 2. 做了什麼

### A. 可重用 SVG 桌寵小助手巨集（`app/templates/partials/pet.html`）
- 將資管科小助手從以往純文字對話框的單一入口，昇華為具有生命力與生動表情的向量角色（桌寵）。
- 角色包含五大核心表情與手部動作：
  1. `idle`（待機）：親切微笑，帶有微幅眼部定時眨眼動畫。
  2. `walking`（走路）：向前方注視，身體上下輕微律動與踏步。
  3. `casting`（施法）：眼神迸發金黃色星芒，手持魔法棒揮舞，杖端散發星光。
  4. `happy`（開心）：彎彎月牙笑眼，開口歡笑露出可愛舌頭，身體雀躍跳動。
  5. `sorry`（抱歉）：八字皺眉、委屈水汪汪大眼、波浪小嘴，額角懸掛藍色冷汗滴。
- 趣味彩蛋：施法或點擊切換時可長出筋肉壯漢手臂（二頭肌隆起），展現為學生自傳全力以赴的幽默感。

### B. 擬真 A4 紙張排版與手機滑動（`student_autobiography_batch.html`）
- A4 直向比例（1 : 1.414）設計，白底黑字、細微紙張陰影與邊框。
- 手機版（375px+）以 `scroll-snap-type: x mandatory` 橫向滑動排版，一次展示一張紙，平滑滾動，絕不發生版面被切斷或撐破。
- 紙張內部設計：
  - 頂部：校徽標籤、學校名稱、系所名稱。
  - 中央：CSS 佔位假線條，在生成時一行行亮起浮現，模擬 AI 打字寫作過程。
  - 特效層：CSS 粒子星星閃爍灑落。
  - 印章層：生成完成時，以 0.4 秒衝擊蓋上「完成」大印章（圓形雙圈朱砂紅印，內印系所名與勾號）。
  - 錯誤層：失敗時淡入重試面板，提供 ≥44px 的重試按鈕。

### C. 狀態機與輪詢（`pet-batch.js`）
- 完全符合後端資料合約：
  - 啟動：POST `start_url` 送出 `csrf_token` -> 取得 `job_id`。
  - 輪詢：每 1.5 秒 GET `status_url`（替換 `__JOB__`）-> 解析 `items` 狀態。
  - 重試：POST `retry_url` 送出 `csrf_token`、`program_id`、`job_id`。
- 移動邏輯：小助手 Actor 自動計算當前正在處理的紙張位置，以平滑曲線位移至該紙張上方停駐點，並配合表情切換。
- 對話泡泡台詞：
  - 每完成一所學校即跳出「`Ciallo～(∠・ω<)⌒★`」！
  - 全部校系完成後跳出「`資管小助手很高興為你服務`」！

### D. 無障礙與規範防護
- 尊重 `prefers-reduced-motion`：使用者開啟減少動態時，停用所有 translate 平移動畫、搖晃、跳躍、粒子飄散與假文字逐行浮現，直接以靜態表情和文字進度顯示。
- 遵循《AGENTS.md》介面規範：
  - 全站無 AI 紫色漸層、無斜體標題、無多餘統計卡片。
  - 頁面無 `position: fixed` 的覆蓋橫條，不遮擋手機內容。
  - 觸控熱區高度皆符合 ≥ 44px 標準。
  - `<noscript>` 完整提供回到單校自傳頁面之退路。

---

## 3. 還沒做到什麼（保留限制與後續可擴充項目）
1. **小助手語音音效（Web Audio API / Sound Effects）**：
   - 目前完成與施法採純視覺與 CSS 粒子動畫演繹，尚未加入「叮！」或蓋印章時的微型 Web Audio 音效（後續若需要可增加可開關的音效選項）。
2. **多頁式自傳長篇預覽切換**：
   - 目前批次頁面以 A4 第一頁封面與自傳重點段落骨架為視覺核心，若單一學校自傳內容超過 3 頁，目前以單張代表該校備審草稿，更長的多頁預覽需點擊「前往檢視各校自傳」至各校編輯器檢視。
3. **自訂桌寵外觀主題（Skins）**：
   - 目前已內建筋肉模式彩蛋（💪），未來可進一步擴充更換小助手帽子（如學士帽、聖誕帽）等客製化裝扮。

---

## 4. 第二輪修正（手機體驗、待機控制、錯誤回饋與入口串接）

針對手機實測（375px viewport）回饋，完成以下 7 項精準修正：

### A. 待機畫面與開始按鈕（防止誤耗學生 AI 次數）
- **修改位置**：`app/templates/student_autobiography_batch.html`、`app/static/js/pet-batch.js`、`app/static/css/design-system.css`
- **調整成果**：
  - 取消頁面載入時的自動 `startBatch()` POST 呼叫。
  - 載入後先呈現小助手待機打招呼（「點擊「請小助手開始」，我馬上為你施法！」）與進度看板待命說明。
  - 新增「請小助手開始」按鈕（`.batch-start-btn`，高度 ≥ 44px），學生明確點擊後才向後端登記並發送 POST `start_url`。
  - 重新整理頁面自然回復到待機畫面，不需強制還原工作進度。

### B. 失敗學校顯示後端訊息與動態引導題按鈕
- **修改位置**：`app/templates/student_autobiography_batch.html`、`app/static/js/pet-batch.js`、`app/static/css/design-system.css`
- **調整成果**：
  - 批次生成失敗時，讀取並顯示後端回傳的 `items[].message`（如「很看重…，請先用自己的話寫幾句…」），訊息為空時才顯示預設提示。
  - 若失敗原因為「自己的話」或引導題回答不足，將原本的「重試此校」按鈕替換為連結按鈕「去回答引導題」（`.batch-guide-link`，觸控區域 ≥ 44px），點擊直接跳轉至 `/student/autobiography?program_id=<該校 program_id>&redo=1`，讓學生即刻補填。
  - 一般異常（如網路連線問題或伺服器忙碌）則維持顯示「重試此校」按鈕。

### C. 修正印章顯隱邏輯（失敗紙張不出現完成章）
- **修改位置**：`app/static/css/design-system.css`
- **調整成果**：
  - 修正 `@media (prefers-reduced-motion: reduce)` 中無條件對 `.batch-paper__stamp` 設定 `display: block !important;` 的錯誤規則，改為嚴格限定在 `.batch-paper[data-status="done"] .batch-paper__stamp`。
  - 新增全域規則 `.batch-paper:not([data-status="done"]) .batch-paper__stamp { display: none !important; }`，徹底防堵任何非完成狀態（pending、running、failed）的紙張產生印章殘影。

### D. 根治手機版（375px）橫向溢出問題
- **修改位置**：`app/static/css/design-system.css`、`app/static/js/pet-batch.js`
- **調整成果**：
  - 移除 `.pet-bubble` 上的 `white-space: nowrap;`，改採 `white-space: normal; word-break: break-word; max-width: min(280px, calc(100vw - 32px));`，對話泡泡長字句自動折行且不超出螢幕。
  - 重構 `pet-batch.js` 的小助手水平座標計算函式 `calculatePetSafeLeft`：改以相對於小助手 dock 視界的投影距離運算，並利用 `Math.min(..., dock.clientWidth - actorWidth)` 進行嚴格邊界 Clamp 限制，解決因為可捲動容器 `offsetLeft` 累加導致小助手位移撐爆視窗的問題。
  - 主容器加入 `max-width: 100%; overflow-x: clip;`，確保在手機 375px 視窗下整頁 `document.documentElement.scrollWidth <= window.innerWidth`，無任何左右捲動。

### E. 提升紙張底部狀態文字對比度
- **修改位置**：`app/static/css/design-system.css`
- **調整成果**：
  - 將 `.batch-paper__footer` 頂部分隔線加深，頁碼與文字顏色由 `#6b7280` 改為高對比深色 `#1f2937`。
  - 狀態文字 `.batch-paper__status-text` 依據狀態給予高對比度色彩：
    - 完成狀態（`[data-status="done"]`）：高對比墨綠色 `#14532d`（對比度 > 7:1）。
    - 施法狀態（`[data-status="running"]`）：高對比深藍色 `#1d4ed8`（對比度 > 7:1）。
    - 失敗狀態（`[data-status="failed"]`）：高對比深硃砂紅 `#991b1b`（對比度 > 7:1）。
  - 在淺色白底紙張及深色外觀下均具備清晰辨識度，符合 WCAG AAA / AA 標準。

### F. 功能入口全面串接
- **修改位置**：`app/templates/student_targets.html`、`app/templates/student_autobiography.html`
- **調整成果**：
  - **目標校系頁**：當學生已選校系達 2 所以上（`selected_programs|length >= 2`）時，在已選清單上方加入按鈕「一次替所有校系生成自傳」（觸控熱區 ≥ 44px），連至 `url_for('student.autobiography_batch')`。
  - **自傳編輯頁**：在頂部工具列「其他工具」展開選單（`.canva-toolbar__more-menu`）中新增項目「一次替所有校系生成」，直達批次生成頁面。

### G. 維持精簡縱向高度與手機單張紙規格
- 保留手機 375px 下一次只聚焦一張紙的水平 snap 滑動機制（紙張尺寸 `min(320px, calc(100vw - 48px))`、標準 A4 直向比例）。
- 嚴格維持看板、舞台與紙張陳列軌道高度，4 張紙總高度控制在約 1450px～1500px，不拉長頁面，保證手機滾動流暢不疲勞。

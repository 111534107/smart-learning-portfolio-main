# 指導討論三畫面實作計畫（學生首頁拼圖、OCR 核對、校系排行）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 依核准的設計摘要，實作學生首頁「大桌板拼圖」、OCR 核對「左圖右表」、校系排行「一頁多校＋圖表切換＋篩選＋細項」，並新增管理員可維護的篩選選項。

**Architecture:** 三個工作流（A 首頁、B OCR 核對、C 排行）改寫既有頁面與模板，重用現有服務：`journey_home.py`（拼圖形狀）、`learning_profile_review`（信心與原圖）、`matching_service.rank_programs` 與 `gap_service.analyze_gap`（已符合／缺少）。工作流 G 以 `CourseRule` 的管理頁為樣板，新增一張篩選選項表。D 只做人工檢查，有問題才修。

**Tech Stack:** Flask、SQLAlchemy（`app/models/`）、Jinja 模板、`app/static/js/components.js`、pytest。Alembic 遷移位於 `migrations/`。

**Spec:** `docs/superpowers/specs/2026-10-28-guidance-screens-design.md`（設計摘要，已由使用者核准）；任務來源 `docs/05_交接與專案管理/代辦任務清單_2026-10-28_指導討論.md`。

## Global Constraints

- 所有百分比標示為「準備度／建議值」，不得出現「錄取保證」字樣。
- 未經學生確認的 OCR 資料不得進入 AI 分析（既有 `learning_profile_document_confirm` 為確認關卡，不得繞過）。
- 學生只能看到自己的資料；排行細項只列登入學生本人的已符合與缺少項目。
- 電腦版與 390px 手機版都不得出現水平捲動。
- 使用者介面為繁體中文。
- 測試指令使用 `--basetemp=logs/test-runs/<名稱>`（避免系統 Temp 權限問題）。

## Review Focus

1. 學生 A 看到學生 B 的拼圖、排行細項或 OCR 資料 → 測試：以 A 登入請求 B 的拼圖與排行細項，應回 403／404。
2. OCR 欄位未確認就送出或進入 AI 分析 → 測試：未確認的 `SourceDocument` 不出現在 AI 輸入中。
3. 管理員停用篩選選項後，前台仍顯示 → 測試：停用後排行頁篩選清單不含該選項。
4. 篩選條件組合後無結果 → 測試：空結果顯示「沒有符合的校系」，不報錯。
5. 390px 下排行列表或 OCR 表格出現水平捲動 → 驗證：瀏覽器 390px 寬度檢查 `document.documentElement.scrollWidth <= 390`。

## Blockers（開工前必須有答案）

以下是設計摘要或現有程式無法決定的問題。**相關任務不得自行假設，必須先回報使用者或老師。**

| 編號 | 問題 | 影響任務 |
|---|---|---|
| Q2 | 「主任」與「科主」是否同一角色 | E（本計畫不含） |
| Q3 | 統計表：使用者統計或管理者統計 | E（本計畫不含） |
| Q4 | 排行是否隨資料自動更新排序 | C3 |
| Q5 | 拼圖完成狀態的具體畫面 | A2 |
| B-1 | 大桌板格數：草圖為 2×6＝12 格；五年累積若每年六類則為 5×6＝30 格。現有 `journey_home.py` 只有當年 3×2＝6 片。需使用者確認格數與排列 | A1、A3 |
| B-2 | 「地區」篩選需要資料：`AdmissionProgram` 目前沒有地區欄位，`admission_category` 與 `school_name` 無法代替 | C1、G1 |
| B-3 | 兩套拼圖並存：`PuzzlePiece`（`piece_key` 為 course／work 等）與 `journey_home` 的六類拼圖鍵（`CATEGORY_KEYS`）不一致。需決定以哪一套為準 | A1 |

**2026-10-28 決定（使用者沒有定見，核准 Claude 的建議）：**
- B-1：格數＝走過的年級數 × 6 類（專一 6 格、專三 18 格、專五 30 格），每個年級一塊 3×2 拼圖。手機版一個年級一塊、上下排列，不水平捲動。
- B-3：以 `CATEGORY_KEYS` 為準；`PuzzlePiece` 不動。
- Q5：有資料的格亮起，亮起的格也能再上傳；走過年級的格全部亮起時顯示「拼圖完成！」，並開放生成自傳。

## 工作流 A：學生首頁大桌板

**現況：** `app/services/journey_home.py` 的 `journey_home()` 產生「今年 6 片」與「五年 stops」；`app/templates/student_home.html` 顯示；`app/static/js/components.js` 約 536–623 行處理拼上動畫。`PuzzlePiece` 模型未被首頁使用。

### Task A1: 大桌板資料（依 B-1、B-3 決定）

**Files:**
- Modify: `app/services/journey_home.py`（`jigsaw_pieces()`、`journey_home()`）
- Test: `tests/test_journey_home.py`

**Interfaces:**
- Consumes: `journey_service.build_journey(user)` 的 `years[].categories[key]`
- Produces: `journey_home(user) -> dict` 新增 `board`：`{"slots": [{"grade": int, "key": str, "filled": bool, "href": str}], "total": int, "filled": int, "complete": bool}`；`complete` 為 True 時才可觸發自傳（A3 使用）

- [ ] **Step 1: 寫失敗測試**：學生有 2 個年級各自填入不同類別，`board["filled"]` 應等於已填格數，`board["complete"]` 為 False；全部格填滿時 `complete` 為 True。測試名稱：`test_board_counts_filled_slots_across_years`、`test_board_complete_only_when_all_slots_filled`。
- [ ] **Step 2: 執行確認失敗**：`python -m pytest tests/test_journey_home.py -k board --basetemp=logs/test-runs/a1 -v`，預期 FAIL（`board` 不存在）。
- [ ] **Step 3: 實作**：依 B-1 的格數決定 `slots` 的長度與排列；`jigsaw_pieces()` 的形狀資料沿用，不另寫一套。
- [ ] **Step 4: 執行確認通過**：同上指令，預期 PASS；再跑 `pytest tests/test_journey_home.py --basetemp=logs/test-runs/a1-all`，全部通過。
- [ ] **Step 5: Commit**（等使用者核准後再提交）

### Task A2: 大桌板頁面與拼上動畫

**Files:**
- Modify: `app/templates/student_home.html`、`app/static/js/components.js`（約 536–623 行）、`app/static/css/design-system.css`（`.puzzle-piece` 約 873–883 行）
- Test: `tests/test_css_integrity.py`（沿用既有檢查）、瀏覽器驗證

**Interfaces:**
- Consumes: A1 的 `board`
- Produces: 每個空格的連結指向 `href`；上傳後回到首頁時，新填的格以動畫飛入（沿用現有 `snap-in` 動畫，時序依 Q5 再定）

- [ ] **Step 1: 寫失敗測試**：首頁 HTML 含 `data-board-slot` 屬性，數量等於 `board["total"]`；空格有 `href`。測試名稱：`test_home_renders_board_slots`。
- [ ] **Step 2: 執行確認失敗**：`pytest tests/test_journey_home.py -k board_slots --basetemp=logs/test-runs/a2 -v`，預期 FAIL。
- [ ] **Step 3: 實作模板與樣式**：大桌板取代「今年六片」區塊；電腦版 6 欄，手機版縮成可捲動格子（`overflow-x` 只允許在格子容器內，頁面本身不得水平捲動）。
- [ ] **Step 4: 執行確認通過**：同上指令 PASS；`pytest tests/test_css_integrity.py --basetemp=logs/test-runs/a2-css`。
- [ ] **Step 5: 瀏覽器驗證**：`preview_start` 啟動開發伺服器，390px 與桌機寬度各截圖一次，確認無水平捲動。

### Task A3: 拼圖完成才生成自傳

**Files:**
- Modify: `app/routes/student.py`（`autobiography()` 約 1214 行、`autobiography_generate()` 約 1222 行）
- Test: `tests/test_autobiography.py`

**Interfaces:**
- Consumes: A1 的 `board["complete"]`
- Produces: 未完成時 `autobiography_generate()` 回傳提示「拼圖還沒完成，完成後才能生成自傳」，不呼叫 AI。

- [ ] **Step 1: 寫失敗測試**：`board["complete"]` 為 False 時 POST 生成，應不呼叫 AI 函式（以 monkeypatch 計數）且顯示提示。測試名稱：`test_autobiography_blocked_until_board_complete`。
- [ ] **Step 2: 執行確認失敗**：`pytest tests/test_autobiography.py -k blocked --basetemp=logs/test-runs/a3 -v`，預期 FAIL。
- [ ] **Step 3: 實作**：在生成入口加入 `board["complete"]` 檢查。
- [ ] **Step 4: 執行確認通過**：同上 PASS；`pytest tests/test_autobiography.py --basetemp=logs/test-runs/a3-all` 全部通過。

## 工作流 B：OCR 核對左圖右表

**現況：** `app/templates/learning_profile_review.html` 已有逐欄信心（低於 0.85 標為「偏低」）、原圖連結（`learning_profile_document_source`）與課程列；`student.py` 的 `learning_profile_document_confirm`（約 568 行）是確認關卡。缺的是左圖右表的並排版面、橘色標示與「剩餘待確認列數」。

### Task B1: 左圖右表版面

**Files:**
- Modify: `app/templates/learning_profile_review.html`
- Test: `tests/test_learning_profile_review_enhancements.py`

**Interfaces:**
- Consumes: 既有 `learning_profile_document_source(document_id)` 的圖片網址、課程列的 `field_confidence`
- Produces: 每列待確認（信心低於 0.85 或未知）加上 `class="needs-review"`；頁首顯示「還有 N 列待確認」（N 為待確認列數）

- [ ] **Step 1: 寫失敗測試**：兩列中一列信心低於 0.85，回應 HTML 含 `needs-review` 一次，且含「還有 1 列待確認」。測試名稱：`test_review_marks_low_confidence_rows`。
- [ ] **Step 2: 執行確認失敗**：`pytest tests/test_learning_profile_review_enhancements.py -k low_confidence --basetemp=logs/test-runs/b1 -v`，預期 FAIL。
- [ ] **Step 3: 實作**：左側放原圖（沿用既有圖片網址），右側放現有表格；電腦版並排，手機版改為一列一張卡片，原圖收合在卡片內。
- [ ] **Step 4: 執行確認通過**：同上 PASS；`pytest tests/test_learning_profile_review_enhancements.py --basetemp=logs/test-runs/b1-all`。
- [ ] **Step 5: 瀏覽器驗證**：390px 寬度確認無水平捲動。

### Task B2: 確認關卡不被繞過

**Files:**
- Test: `tests/test_learning_profile_confirmation.py`（既有檔，新增測試）
- Modify: 僅在測試失敗時修 `app/routes/student.py`

**Interfaces:**
- Consumes: `learning_profile_document_confirm`
- Produces: 未確認文件不會出現在 AI 輸入（既有 `SourceDocument.status` 為 `confirmed` 才算）

- [ ] **Step 1: 寫測試**：未確認的文件在 AI 輸入的組裝函式中不出現。先找出組裝 AI 輸入的函式名稱（`grep -rn "confirmed" app/services/agent_advisor.py app/services/matching_service.py`），再寫測試。測試名稱：`test_unconfirmed_document_excluded_from_ai_input`。
- [ ] **Step 2: 執行**：若 PASS 表示既有行為正確，直接記錄；若 FAIL 則修正並重跑。

## 工作流 C：校系排行

**現況：** `app/services/matching_service.py` 的 `rank_programs()`（約 212–259 行）回傳已排序的列，含 `status`（`eligible`／`needs_check`／`ineligible`）、`fit`（準備度）、`reasons`、`gap`（`gap["items"]` 的 `have`／`missing`）。`app/templates/student_matching.html` 目前是純列表。

### Task C1: 排行頁：圖表切換與篩選

**Files:**
- Modify: `app/templates/student_matching.html`、`app/routes/student.py`（`matching()` 約 1044 行）
- Create: `app/static/js/matching-chart.js`（長條與橫條切換，只做顯示）
- Test: `tests/test_matching_service.py`（新增）、`tests/test_matching_page.py`（新檔）

**Interfaces:**
- Consumes: `rank_programs(student, programs)` 的列；篩選選項來自 G1 的 `match_filter_options`（科系、地區、學制、是否可報）
- Produces: `matching()` 傳入 `filters`（各類別的啟用選項）與 `active_filters`（URL 查詢參數）；篩選以查詢參數 `?department=&region=&level=&eligible=` 套用，在伺服器端過濾列

- [ ] **Step 1: 寫失敗測試**：`GET /student/matching?eligible=eligible` 只回傳 `status == "eligible"` 的列；`?department=X` 只回傳科系名稱符合的列。測試名稱：`test_matching_filter_by_eligibility`、`test_matching_filter_by_department`。
- [ ] **Step 2: 執行確認失敗**：`pytest tests/test_matching_page.py --basetemp=logs/test-runs/c1 -v`。
- [ ] **Step 3: 實作**：伺服器端過濾；頁面加入篩選列與「長條／橫條」切換按鈕（預設橫條，Q 已在草圖暫定）；圖表以 CSS 寬度呈現，不引入新函式庫。
- [ ] **Step 4: 執行確認通過**：同上 PASS；`pytest tests/test_matching_service.py tests/test_matching_page.py --basetemp=logs/test-runs/c1-all`。
- [ ] **Step 5: 瀏覽器驗證**：電腦與 390px 各截圖一次。

### Task C2: 點入細項（已符合／缺少）

**Files:**
- Modify: `app/templates/student_matching.html`
- Test: `tests/test_matching_page.py`（新增）

**Interfaces:**
- Consumes: 列的 `gap["items"]`，每項的 `have`、`missing`（類別鍵）、`name`、`weight`；類別鍵以 `CATEGORY_LABELS` 轉成中文
- Produces: 電腦版點入某校展開兩欄「已符合」與「缺少」；手機版點入整頁（`/student/matching/<program_id>`）

- [ ] **Step 1: 寫失敗測試**：學生 A 請求 B 的細項路由應回 404；A 的細項頁包含「已符合」「缺少」兩個標題。測試名稱：`test_matching_detail_owner_only`、`test_matching_detail_shows_have_and_missing`。
- [ ] **Step 2: 執行確認失敗**。
- [ ] **Step 3: 實作**：細項一律以登入者為準，不接受 URL 中的學生編號。
- [ ] **Step 4: 執行確認通過**。

### Task C3: 排序是否自動更新（依 Q4）

**Blocked:** Q4 未定。`rank_programs` 每次請求即時計算，本身已會隨資料變動更新排序；若使用者決定「不自動更新」，才需要快取與手動更新按鈕。答覆前不實作。

## 工作流 D：AI 比分檢查

### Task D1: 人工檢查比分

**Files:** 無程式變更；產出 `docs/superpowers/plans/2026-10-28-score-check-notes.md`

- [ ] **Step 1:** 用 `tests/` 既有的測試資料（`tests/test_matching_service.py` 與 `app/content/` 的條件資料）列出 3–5 位虛構學生的準備度，人工檢查是否合理（例如完全沒有資料卻顯示高準備度即為不合理）。
- [ ] **Step 2:** 寫下檢查結果與不合理處原因。
- [ ] **Step 3: 若有不合理：** 先寫失敗測試（以不合理案例為輸入），再修 `analyze_gap`，記錄測試數字。若無，記錄「未發現不合理」。

## 工作流 G：篩選選項後台維護

**現況：** `app/routes/admin.py` 的 `course_rules()`（約 40–85 行）與 `app/templates/admin_course_rules.html` 是可直接參考的管理頁樣板。

### Task G1: 資料表與遷移（依 B-2 決定地區欄位）

**Files:**
- Create: `app/models/match_filter.py`（`MatchFilterOption`）
- Modify: `app/models/__init__.py`（匯出）、新增 `migrations/versions/<rev>_match_filter_options.py`
- Test: `tests/test_match_filter_options.py`（新檔）

**Interfaces:**
- Produces: `MatchFilterOption`：`id`、`category`（`department`／`region`／`level`／`eligible`）、`label`、`value`、`sort_order`、`is_active`、`created_at`、`updated_at`；唯一約束 `(category, value)`

- [ ] **Step 1: 寫失敗測試**：建立兩筆選項、停用一筆後，`active_options("department")` 只回啟用中的。測試名稱：`test_inactive_options_hidden`。
- [ ] **Step 2: 執行確認失敗**。
- [ ] **Step 3: 實作模型與遷移**；遷移指令依 `migrations/README` 的既有方式執行。
- [ ] **Step 4: 執行確認通過**。

### Task G2: 管理頁

**Files:**
- Modify: `app/routes/admin.py`（新增 `match_filters()`、`create_match_filter()`、`toggle_match_filter()`）
- Create: `app/templates/admin_match_filters.html`
- Test: `tests/test_match_filter_admin.py`（新檔，樣板參考 `tests/test_course_rule_admin.py`）

**Interfaces:**
- Consumes: G1 的模型
- Produces: 路由 `GET /admin/match-filters`、`POST /admin/match-filters`、`POST /admin/match-filters/<id>/toggle-active`；均需 `@role_required("admin")` 與 CSRF

- [ ] **Step 1: 寫失敗測試**：非管理員 POST 應 403；管理員新增後，列表含該選項；停用後列表狀態為停用。測試名稱：`test_match_filter_admin_only`、`test_match_filter_create_and_toggle`。
- [ ] **Step 2: 執行確認失敗**。
- [ ] **Step 3: 實作**，照 `course_rules` 的寫法（含重複值檢查與 `abort(400)`）。
- [ ] **Step 4: 執行確認通過**。

## 驗證（全部工作流完成後）

- [ ] `pytest --basetemp=logs/test-runs/final -q`，結果如實記錄通過與失敗數字。
- [ ] 三個畫面在電腦與 390px 寬度下截圖，確認無水平捲動。
- [ ] 逐條核對 Review Focus 五項，每項有對應測試或驗證紀錄。
- [ ] 更新 `docs/05_交接與專案管理/checklist.md` 與 `docs/03_開發紀錄/development-log.md`。

## 不在本計畫範圍

- 工作流 E（主任權限與統計）：等 Q2、Q3。
- Q5 拼圖完成狀態細節：A2 的動畫時序等答覆。
- 送出後能否回頭修改 OCR（設計摘要列為未決）。
- `.superpowers/` 加入 `.gitignore`（需使用者同意改動該檔）。

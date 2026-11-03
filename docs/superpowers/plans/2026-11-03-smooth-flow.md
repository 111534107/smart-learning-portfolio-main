# 學生端動線與版型簡化（參考 iOS「內容先、一個主要動作」）實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 首頁以外的學生頁面：內容提早出現、每頁只有一個主要按鈕、切換不重新載入、看得到「我在備審流程的第幾步」，操作起來順。

**Architecture:** 建在 `feat/campus-theme` 上（同一套 `data-theme="campus"` 範圍）。共用的東西放 `partials/nav.html` 的巨集與 `theme-campus.css`；頁面只換 class、包 `<details>`，不改資料邏輯。即時搜尋用少量 JS，沒有 JS 時原本的表單照常運作。

**Tech Stack:** Flask 3、Jinja2、純 CSS、少量原生 JS（`app/static/js/components.js`）、pytest。

**Spec:** 本文件「量測結果」一節（2026-11-03 在展示站實測，量測腳本 `docs/superpowers/plans/2026-11-03-ui-audit.js`）。

## 量測結果（改之前，1280×800 桌機；手機 390×844）

| 頁面 | 高度（螢幕數） | 按鈕／連結按鈕 | 實心主要按鈕 | 標籤與灰字 | 問題 |
| --- | --- | --- | --- | --- | --- |
| 目標校系 `/student/targets` | **7.5** | 48 | 3 | 58 | 「我的目標」下面又嵌一整份「準備度排行」，跟推薦排序頁重複 |
| 推薦排序 `/student/matching` | 1.9 | 28 | **4** | **191** | 二技／插大、橫條／長條、找、請小助手都是同一種實心黑按鈕 |
| 活動與經歷 `/student/portfolio` | 4.2 | 23 | 1 | 28 | 首屏 7 個動作搶注意力 |
| 招生時程、自傳 | 1.5～1.9 | 1～2 | 0 | 25～34 | 頁面沒有主要動作 |

手機實測：
- 首屏有約一半被頂部列＋分頁列＋藍色標題塊＋麵包屑佔掉，內容從畫面中間才開始。
- 每頁開頭先是 2～3 段說明文字（「本機展示使用示範校系資料…」「目標校系不限所數…」），之後才是內容。
- 同一頁有三套導覽：上方分頁、麵包屑「首頁／推薦排序」、內文的「← 回目標校系」。
- 搜尋要按「找」、篩選要按「顯示排行」，每次都整頁重新載入。
- 右下角「資管科小助手」按鈕蓋住卡片文字。

## 跟 iOS 的差別（給使用者看的白話版）

1. **內容先出現**：iOS 只有一個大標題，說明收在「ⓘ」裡；我們每頁先講一堆免責說明。
2. **一個畫面一個主要動作**：iOS 只有一個藍色主要按鈕，切換用「分段控制」；我們把切換、搜尋、主要動作都做成一樣的黑按鈕，眼睛不知道先看哪。
3. **導覽只有一套**：iOS 左上角返回＋底部分頁；我們同時有分頁、麵包屑、內文返回鈕。
4. **即時回應**：iOS 搜尋邊打邊篩；我們要按按鈕、整頁重載，這就是「不流暢」。
5. **知道自己在流程哪一步**：iOS 的設定流程會有步驟；我們的備審流程（選校→補缺件→寫自傳→導師確認與下載）分散在 5 頁，只有首頁看得到進度。
6. **同一件事只在一個地方做**：準備度排行同時在目標校系頁與推薦排序頁。

## Global Constraints

- 首頁不動：`data-page` 是 `student-dashboard`、`public-home` 的頁面不改。
- 說明文字不能刪（學校驗收要看得到免責與資料來源），只能收進 `<details>`。
- 沒有 JavaScript 時，所有表單、連結照原本方式運作。
- 點擊區域至少 44×44px；尊重 `prefers-reduced-motion`。
- 不做膠囊按鈕、斜體標題、紫色漸層（專題 `AGENTS.md` §9）；分段控制用 10px 圓角外框。
- 不改資料計算與路由行為（測試數字照舊）。
- 在 `feat/campus-theme` 合併 GPT 的驗收修改之後再開工，避免衝突。

## 需要使用者先決定

1. **目標校系頁的「探索校系／準備度排行」**（組員整合進來的區塊）：
   A. 目標校系頁只留「我的目標」，加一顆「找更多校系 →」到推薦排序頁（建議，頁高預計從 7.5 降到 2 螢幕以內）；
   B. 保留。選 B 就跳過 Task 5。
2. **時機**：GPT 正在照現有畫面做學校驗收紀錄；畫面改了，紀錄要重做。建議先做完本計畫，再讓 GPT 錄驗收。

## Review Focus

1. 搜尋打字時，第 21 名以後的校系也要能找到（目前只輸出前 20 名）→ Task 4 要輸出全部，再用「看更多」收起。
2. 關掉 JavaScript 時，二技／插大切換、搜尋、看更多都要能用 → Task 3、4 測試沒有 JS 的網址參數。
3. 說明收進 `<details>` 後，報讀軟體要能讀到「說明」並展開 → Task 2 用原生 `<details><summary>`。
4. 手機上小助手按鈕不能蓋住最後一張卡片的按鈕 → Task 6 頁面底部留空，Task 7 實測。
5. 全新學生（沒有成績、沒有目標校系）時，步驟列也要正常顯示，而且第 1 步「收集資料」是「目前」→ Task 1 測試。

---

### Task 1: 備審流程步驟列（知道自己在第幾步）

**Files:**
- Modify: `app/templates/partials/nav.html`（新增巨集 `flow_steps()`）
- Modify: `app/templates/student_targets.html`、`student_matching.html`、`student_gap.html`、`student_autobiography.html`、`student_schedule.html`（標題下方呼叫）
- Modify: `app/static/css/theme-campus.css`
- Test: `tests/test_flow_steps.py`

**Interfaces:**
- Consumes: `student_progress`（`app/routes/main.py::inject_student_progress` 已注入）：`steps`（4 筆，`no`、`title`、`href`、`state` 為 `done`／`current`／`todo`）、`next`（`text`、`href`）。
- Produces: `<ol class="flow-steps">`，目前那一步的 `<li>` 有 `aria-current="step"`；下面一顆實心按鈕 `class="button flow-steps__next"`，文字是 `student_progress.next.text`。

- [ ] **Step 1: Write the failing test**

`tests/test_flow_steps.py` 開頭定義本計畫所有任務共用的 fixture：`app`（照 `tests/test_autobiography.py` 的寫法：記憶體 SQLite、`import_seed_programs()`、一個全新學生 `stu`）、`student_client`（已登入 `stu`）、`program_id`（`program_code="208003"` 的 id）、`twotech_total`（二技已發布校系數，用和推薦排序頁相同的查詢算）、`THEME_CSS`（`app/static/css/theme-campus.css` 路徑）。

```python
def test_targets_page_shows_four_flow_steps_with_current_step(student_client):
    html = student_client.get("/student/targets").get_data(as_text=True)
    assert html.count('class="flow-steps__item') == 4
    assert html.count('aria-current="step"') == 1
    assert "選目標校系" in html and "flow-steps__next" in html

def test_new_student_has_step_one_current(student_client):
    html = student_client.get("/student/schedule").get_data(as_text=True)
    current = html.split('aria-current="step"')[1][:200]
    assert "收集資料" in current

def test_home_page_has_no_flow_steps(student_client):
    assert "flow-steps" not in student_client.get("/student/dashboard").get_data(as_text=True)
```

- [ ] **Step 2: Run** `D:\democase\ai\.venv\Scripts\python.exe -m pytest tests/test_flow_steps.py -q --basetemp=logs/test-runs/flow-1`，Expected: FAIL
- [ ] **Step 3: 實作** 巨集輸出 4 個小圓點＋標題（手機只顯示目前那一步的標題，其他只留圓點），完成的打勾、可點回去；下面一顆「下一步：…」實心按鈕。五個頁面在標題下呼叫。
- [ ] **Step 4: Run** 同 Step 2，Expected: 3 passed
- [ ] **Step 5: Commit** `git commit -m "備審頁加流程步驟列：看得到自己在第幾步，只給一個下一步"`

### Task 2: 精簡頁首：大標題＋說明收合

**Files:**
- Modify: `app/templates/partials/nav.html`（`page_band` 巨集：學生頁不輸出只有一層的麵包屑）
- Modify: `app/templates/student_targets.html`、`student_matching.html`、`student_schedule.html`（開頭說明包成 `<details class="page-intro">`）
- Modify: `app/static/css/theme-campus.css`
- Test: `tests/test_flow_steps.py`

**Interfaces:**
- Produces: `<details class="page-intro"><summary>說明</summary>…</details>`；`.band` 在校園主題下變成大標題（無色塊）。

- [ ] **Step 1: Write the failing test**

```python
def test_disclaimers_are_folded_but_still_present(student_client):
    html = student_client.get("/student/matching").get_data(as_text=True)
    assert '<details class="page-intro">' in html
    assert "目標校系由你自己決定" in html  # 文字還在，只是收起來

def test_single_level_pages_have_no_breadcrumb(student_client):
    html = student_client.get("/student/schedule").get_data(as_text=True)
    assert 'class="band__crumbs"' not in html

def test_nested_pages_keep_breadcrumb(student_client, program_id):
    html = student_client.get(f"/student/matching/{program_id}").get_data(as_text=True)
    assert 'class="band__crumbs"' in html
```

- [ ] **Step 2: Run**（同上，basetemp `flow-2`），Expected: FAIL
- [ ] **Step 3: 實作** `page_band`：`crumbs` 是空的就不輸出麵包屑（`student_progress is defined` 時）。CSS：校園主題下 `.band__title` 改成透明底、`var(--ink)` 字、`var(--fs-display)` 大小，手機時頁首上下內距減半。每頁開頭的說明段落保留第一句當可見的一行副標，其餘放進 `<details class="page-intro">`。
- [ ] **Step 4: Run**，Expected: passed
- [ ] **Step 5: Commit** `git commit -m "頁首精簡：大標題、單層頁不顯示麵包屑、說明收合"`

### Task 3: 按鈕分級與分段控制

**Files:**
- Modify: `app/templates/student_matching.html:15-50`、`app/templates/partials/target_explorer.html`（二技／插大）
- Modify: `app/static/css/theme-campus.css`（新增 `.segmented`）
- Test: `tests/test_flow_steps.py`

**Interfaces:**
- Produces: `<nav class="segmented" aria-label="…">`，裡面是 `<a class="segmented__item" aria-current="page">`；不再用 `.button`。

- [ ] **Step 1: Write the failing test**

```python
def test_matching_has_one_filled_button_and_segmented_switches(student_client):
    html = student_client.get("/student/matching").get_data(as_text=True)
    assert html.count('class="segmented"') == 2          # 二技／插大、橫條／長條
    assert html.count('class="button button--small"') <= 1  # 只留一顆實心主要按鈕
    assert 'href="/student/matching?track=transfer' in html  # 沒有 JS 也能切換
```

- [ ] **Step 2: Run**（basetemp `flow-3`），Expected: FAIL
- [ ] **Step 3: 實作** 二技／插大、橫條／長條改成分段控制（外框 10px 圓角、選中那格白底＋淡陰影、未選中透明）；「找」「回目標校系」改 `button--line`／移除（返回交給上方分頁）；「請小助手幫我規劃升學」維持唯一實心按鈕。
- [ ] **Step 4: Run**，Expected: passed
- [ ] **Step 5: Commit** `git commit -m "按鈕分級：切換改分段控制，每頁只留一顆實心主要按鈕"`

### Task 4: 推薦排序邊打邊篩

**Files:**
- Modify: `app/routes/student.py`（推薦排序：輸出全部校系，前 20 名以外標 `data-extra`）
- Modify: `app/templates/student_matching.html`（每列 `data-match-row data-match-text="校名 科系"`；搜尋框加 `data-live-filter`；「看更多」改成按鈕＋原連結當後備）
- Modify: `app/static/js/components.js`（`initLiveFilter()`）
- Test: `tests/test_flow_steps.py`

**Interfaces:**
- Produces: `data-live-filter`（輸入框）、`data-match-row`、`data-match-text`、`data-extra`、`[data-filter-empty]`（「沒有符合的校系」）。

- [ ] **Step 1: Write the failing test**

```python
def test_matching_renders_all_rows_for_live_filter(student_client, twotech_total):
    html = student_client.get("/student/matching").get_data(as_text=True)
    assert html.count("data-match-row") == twotech_total   # 41 間都輸出
    assert html.count("data-extra") == twotech_total - 20  # 20 名以後先收起
    assert "data-live-filter" in html and "data-filter-empty" in html

def test_search_still_works_without_javascript(student_client):
    html = student_client.get("/student/matching?q=北商").get_data(as_text=True)
    assert "國立臺北商業大學" in html
```

- [ ] **Step 2: Run**（basetemp `flow-4`），Expected: 第 1 項 FAIL
- [ ] **Step 3: 實作** JS：輸入時（150ms 去抖動）把關鍵字用空白拆開，每個都要出現在 `data-match-text` 才顯示；有關鍵字時忽略 `data-extra` 收合；全部隱藏時顯示 `[data-filter-empty]`；按 Enter 照常送出表單。CSS 以 `[hidden]` 控制，不加動畫。
- [ ] **Step 4: Run**，Expected: passed
- [ ] **Step 5: Commit** `git commit -m "推薦排序邊打邊篩：不用按找、不重新載入"`

### Task 5（使用者選 A 才做）：目標校系頁只留「我的目標」

**Files:**
- Modify: `app/templates/student_targets.html:67`（拿掉 `partials/target_explorer.html` 的排行與篩選，改一顆連到推薦排序的按鈕）
- Modify: `app/routes/student.py`（`target_list` 不再計算排行與篩選選項）
- Modify: 依賴舊畫面的測試（`tests/test_matching_page.py`、`tests/test_teammate_admission_eligibility.py` 裡斷言目標校系頁出現排行的項目，改成斷言推薦排序頁）
- Test: `tests/test_flow_steps.py`

- [ ] **Step 1: Write the failing test**

```python
def test_targets_page_no_longer_duplicates_ranking(student_client):
    html = student_client.get("/student/targets").get_data(as_text=True)
    assert "顯示排行" not in html and "準備度排行" not in html
    assert 'href="/student/matching' in html and "找更多校系" in html
```

- [ ] **Step 2: Run**（basetemp `flow-5`），Expected: FAIL
- [ ] **Step 3: 實作**；組員的「資格比對」結果改在推薦排序細項頁顯示（原本就有），不要刪掉功能本身。
- [ ] **Step 4: Run** 完整測試，Expected: 全部通過
- [ ] **Step 5: Commit** `git commit -m "目標校系頁只留我的目標，排行集中在推薦排序（不重複）"`

### Task 6: 手機小助手按鈕不擋內容

**Files:**
- Modify: `app/static/css/theme-campus.css`
- Test: `tests/test_flow_steps.py`

- [ ] **Step 1: Write the failing test**

```python
def test_assistant_button_collapses_on_phones():
    text = THEME_CSS.read_text(encoding="utf-8")
    assert '[data-theme="campus"] .assistant__toggle' in text
    assert "@media (max-width: 480px)" in text
```

- [ ] **Step 2: Run**，Expected: FAIL
- [ ] **Step 3: 實作** 480px 以下：小助手按鈕變 56px 圓形只留圓點圖示（文字視覺隱藏但報讀讀得到），`main` 底部留 5.5rem。
- [ ] **Step 4: Run**，Expected: passed
- [ ] **Step 5: Commit** `git commit -m "手機版小助手按鈕縮成圓鈕，不蓋住內容"`

### Task 7: 前後對照量測、瀏覽器實測、紀錄

**Files:**
- 已有：`docs/superpowers/plans/2026-11-03-ui-audit.js`（本次量測腳本，和計畫書一起提交）
- Modify: `docs/03_開發紀錄/development-log.md`、`docs/05_交接與專案管理/handoff.md`

- [ ] **Step 1: 完整測試** `D:\democase\ai\.venv\Scripts\python.exe -m pytest -q --basetemp=logs/test-runs/flow-full`，Expected: 全部通過
- [ ] **Step 2: 用量測腳本重量**（在展示站登入 `student_demo` 後，把腳本貼進瀏覽器主控台），目標：目標校系頁高度 ≤ 3 螢幕（選 A 時）、推薦排序實心按鈕 ≤ 1、手機首屏內容從 844px 的上方 35% 以內開始。
- [ ] **Step 3: 瀏覽器實測** 390px 手機與桌機：步驟列、說明展開、分段切換、邊打邊篩（含第 21 名以後的校系）、關掉 JS 後表單仍可用、小助手按鈕不擋按鈕；截圖前後對照放進日誌。
- [ ] **Step 4: 日誌與交接**（前後數字表），Commit `git commit -m "開發日誌：學生端動線與版型簡化"`

## 不在本計畫內

- 首頁「我的五年」（量到 19 種字級、44 個按鈕，是最複雜的一頁，但使用者決定先不動）。
- 頁面切換動畫（View Transitions）：先把版型和動作簡化，效果比動畫大。

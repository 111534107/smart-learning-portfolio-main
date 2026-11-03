# 學生端長期乾淨的版型系統（守門測試＋共用元件＋頁面骨架）實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓學生端畫面「現在變乾淨、以後亂不起來」：每年換人維護也只能用固定的頁面骨架與元件，違反規則的修改會被測試擋下。

**Architecture:** 三層。① 守門測試：把現況數字當上限（只准變好、不准變差），每次 `pytest` 都檢查。② 共用元件：`partials/ui.html` 的 Jinja 巨集＋`components.css`，頁面只用元件不寫新樣式。③ 頁面骨架：`layouts/` 四種版型，頁面只填內容。先搬目標校系、推薦排序、招生時程、自傳四頁；其他頁之後逐頁搬，每搬一頁就調低上限。

**Tech Stack:** Flask 3、Jinja2（`extends`、巨集）、純 CSS、少量原生 JS（`app/static/js/components.js`）、pytest。

**Spec:** 本文件「量測結果」與「設計規範」兩節（2026-11-03 實測；量測腳本 `docs/superpowers/plans/2026-11-03-ui-audit.js`）。

## 量測結果（改之前）

畫面（1280×800 桌機；手機 390×844）：

| 頁面 | 高度（螢幕數） | 按鈕 | 實心主要按鈕 | 標籤與灰字 |
| --- | --- | --- | --- | --- |
| 目標校系 | **7.5** | 48 | 3 | 58 |
| 推薦排序 | 1.9 | 28 | **4** | **191** |
| 活動與經歷 | 4.2 | 23 | 1 | 28 |

手機首屏約一半被頂部列＋分頁＋藍色標題塊＋麵包屑佔掉；每頁先有 2～3 段說明才是內容；同頁三套導覽（分頁、麵包屑、內文返回鈕）；搜尋與篩選都要按按鈕整頁重載；小助手按鈕蓋住卡片。

程式（亂的根源）：

| 指標 | 現況 |
| --- | --- |
| `design-system.css` 行數 | 1611 |
| 只給某一頁用的規則（`[data-page=…]`） | 128 |
| 寫死的顏色（不重複） | 66 |
| 寫死的字級（`font-size: 數字`） | 26 |
| 模板裡的 `style="` | 38 |
| 頂層樣式名稱種類 | 201 |
| 預設 `.button` 就是實心黑 | 隨手加一顆就多一個「主要按鈕」 |

## 設計規範（守門測試依據，也寫進給維護者的文件）

1. 每頁只有一個 `h1`（大標題）＋一句副標；其他說明收進 `<details class="page-intro">`。
2. 每頁最多一顆**主要按鈕**；其他用次要（外框）或文字按鈕。切換選項用**分段控制**，不用按鈕。
3. 導覽只有兩種：上方分頁＋（兩層以上才有的）麵包屑；內文不放「← 回…」。
4. 搜尋、篩選邊打邊更新；沒有 JavaScript 時表單照常可送出。
5. 顏色、字級、間距、圓角只能用設計變數；模板不准寫 `style=`；不新增只給某一頁用的規則。
6. 備審流程頁顯示步驟列（第幾步、下一步）。
7. 點擊區域 ≥ 44×44px；尊重減少動態效果；不做膠囊按鈕、斜體標題、紫色漸層（專題 `AGENTS.md` §9）。

## Global Constraints

- 首頁不動：`student_home.html`（`student-dashboard`）、`index.html`（`public-home`）排除在守門與搬遷之外。
- 說明文字不能刪（學校驗收要看得到免責與資料來源），只能收進 `<details>`。
- 沒有 JavaScript 時，所有表單、連結照原本方式運作。
- 不改資料計算與路由行為。
- 建在 `feat/campus-theme` 上；開工前先合併 GPT 在 `feat/google-docs-autobiography` 的驗收修改。

## 需要使用者先決定

1. ✅ **目標校系頁的「探索校系／準備度排行」**：使用者 2026-11-03 決定**拿掉，只留「我的目標」**，加「找更多校系 →」到推薦排序頁（Task 6 照 A 做）。
2. **時機**：GPT 照現在畫面錄驗收紀錄，畫面改了要重錄；建議本計畫做完再錄。

## Review Focus

1. 已經被搬過的頁面，之後有人又加一顆實心按鈕 → Task 1 的逐頁上限會擋下（測試要能指出是哪一頁、哪個數字）。
2. 搜尋時第 21 名以後的校系也要找得到（目前只輸出前 20）→ Task 5 輸出全部、用「看更多」收起。
3. 關掉 JavaScript：分段切換、搜尋、看更多仍可用 → Task 5 測沒有 JS 的網址參數。
4. 全新學生（沒有成績、沒有目標）步驟列正常，第 1 步「收集資料」是目前 → Task 3 測試。
5. 手機上小助手按鈕不能蓋住最後一張卡片的按鈕 → Task 8 頁面底部留空＋實測。

---

### Task 1: 守門測試（只准變好、不准變差）

**Files:**
- Create: `tests/test_design_guardrails.py`
- Create: `tests/design_budget.py`（上限數字，集中一處，之後只准調低）

**Interfaces:**
- Produces: `design_budget.CSS_PAGE_RULES`、`CSS_HEX_COLORS`、`CSS_LITERAL_FONT_SIZES`、`TEMPLATE_INLINE_STYLES`（整數）；`PAGE_PRIMARY_BUTTONS: dict[str, int]`（學生頁網址 → 上限）；`MIGRATED_PAGES: set[str]`（已搬到骨架的頁，規則全套強制）。後面每個搬遷任務都會改這個檔。

- [ ] **Step 1: 寫計數函式與測試**

計數範圍：`app/static/css/*.css`、`app/templates/**/*.html`，排除 `student_home.html`、`index.html`、`proposal_preview.html` 以及首頁專用的 CSS 規則（`[data-page="student-dashboard"]`、`[data-page="public-home"]`）。

```python
def test_css_page_specific_rules_do_not_grow():
    assert count_page_rules() <= design_budget.CSS_PAGE_RULES

def test_css_hardcoded_colors_do_not_grow():  # :root 與 [data-theme="campus"] 的變數定義區不算
    assert count_hex_colors_outside_tokens() <= design_budget.CSS_HEX_COLORS

def test_css_literal_font_sizes_do_not_grow():
    assert count_literal_font_sizes() <= design_budget.CSS_LITERAL_FONT_SIZES

def test_templates_inline_styles_do_not_grow():
    assert count_inline_styles() <= design_budget.TEMPLATE_INLINE_STYLES

@pytest.mark.parametrize("path", sorted(design_budget.PAGE_PRIMARY_BUTTONS))
def test_primary_buttons_per_page_within_budget(student_client, path):
    html = student_client.get(path).get_data(as_text=True)
    assert count_primary_buttons(html) <= design_budget.PAGE_PRIMARY_BUTTONS[path], path

@pytest.mark.parametrize("path", sorted(design_budget.MIGRATED_PAGES))
def test_migrated_pages_follow_all_rules(student_client, path):
    html = student_client.get(path).get_data(as_text=True)
    assert html.count("<h1") == 1, path
    assert count_primary_buttons(html) <= 1, path
    assert "← 回" not in html, path
```

`count_primary_buttons(html)`：`<main>` 裡 class 含 `button` 但不含 `button--line`、`button--quiet`、`button--secondary`、`button--text` 的 `<a>`／`<button>` 數（用 `html.parser`，不加新套件）。`student_client` 照 `tests/test_autobiography.py` 的 fixture 建（專五學生、已選一個目標 `208003`）。

- [ ] **Step 2: 量現況、填上限** 執行計數函式，把結果原樣寫進 `design_budget.py`（每個數字旁註明量測日期）；`PAGE_PRIMARY_BUTTONS` 先放 `/student/targets`、`/student/matching`、`/student/schedule`、`/student/autobiography`、`/student/portfolio`、`/student/learning-profile` 的現況；`MIGRATED_PAGES` 先是空集合。
- [ ] **Step 3: Run** `D:\democase\ai\.venv\Scripts\python.exe -m pytest tests/test_design_guardrails.py -q --basetemp=logs/test-runs/guard-1`，Expected: 全部 passed（上限就是現況）
- [ ] **Step 4: 驗證守門有效** 暫時在 `student_schedule.html` 加一個 `style="color:red"`，再跑一次，Expected: `test_templates_inline_styles_do_not_grow` FAIL；改回去。
- [ ] **Step 5: Commit** `git commit -m "設計守門測試：現況當上限，只准變好不准變差"`

### Task 2: 共用元件（巨集＋樣式）

**Files:**
- Create: `app/templates/partials/ui.html`
- Create: `app/static/css/components.css`（`base.html` 在 `design-system.css` 後、`theme-campus.css` 前載入）
- Modify: `app/templates/base.html`
- Modify: `app/__init__.py`（註冊 Jinja 全域函式 `ui_fail(message)`，丟 `ValueError`）
- Test: `tests/test_ui_components.py`

**Interfaces（巨集簽名，後面任務都用這些）:**
- `button(label, href=None, kind="secondary", type="submit", attrs={})`：`kind` 只能是 `primary`／`secondary`／`text`，輸出 `button button--primary`／`button button--line`／`button button--text`；`href` 有值時輸出 `<a>`，否則 `<button>`。
- `segmented(label, items)`：`items` 是 `[(文字, href, 是否選中)]`；輸出 `<nav class="segmented" aria-label="{label}">`，選中那格有 `aria-current="page"`。
- `page_intro(summary)` 呼叫區塊：`{% call page_intro("說明") %}…{% endcall %}` 輸出 `<details class="page-intro"><summary>說明</summary>…</details>`。
- `notice(text, tone="info")`：`tone` 只能是 `info`／`ok`／`warn`／`danger`。
- `empty_state(title, text, action=None)`：`action` 是 `(文字, href)`，用主要按鈕。
- `flow_steps(progress)`：輸入 `student_progress`；輸出 `<ol class="flow-steps">`，4 個 `<li class="flow-steps__item">`，目前那一步 `aria-current="step"`，下面一顆主要按鈕 `flow-steps__next`（文字 `progress.next.text`）。

- [ ] **Step 1: Write the failing test**（用 `app.jinja_env.get_template("partials/ui.html").module` 直接呼叫巨集）

```python
def test_button_kinds_map_to_three_tiers(ui):
    assert 'class="button button--primary"' in str(ui.button("送出", kind="primary"))
    assert 'class="button button--line"' in str(ui.button("取消"))
    with pytest.raises(ValueError):
        str(ui.button("x", kind="danger-big"))

def test_segmented_marks_current(ui):
    html = str(ui.segmented("學制", [("二技", "/a", True), ("插大", "/b", False)]))
    assert html.count('aria-current="page"') == 1 and 'class="segmented"' in html

def test_flow_steps_has_four_items_and_one_current(ui, progress_fixture):
    html = str(ui.flow_steps(progress_fixture))
    assert html.count('class="flow-steps__item') == 4 and html.count('aria-current="step"') == 1
```

- [ ] **Step 2: Run**（basetemp `guard-2`），Expected: FAIL
- [ ] **Step 3: 實作** 巨集遇到不允許的 `kind`／`tone` 直接 `raise ValueError`（Jinja 用一個註冊到 `app.jinja_env.globals` 的小函式 `ui_fail(message)`）。`components.css` 只用設計變數；`.button--primary` 實心深藍、`.button--line` 外框、`.button--text` 無框；分段控制外框 10px 圓角、選中那格白底淡陰影；流程步驟列手機只顯示目前那一步的標題。
- [ ] **Step 4: Run**，Expected: passed；再跑 Task 1 守門，Expected: passed（新 CSS 沒有寫死顏色）
- [ ] **Step 5: Commit** `git commit -m "共用元件：三級按鈕、分段控制、說明收合、提示、空白狀態、流程步驟列"`

### Task 3: 頁面骨架（四種版型）

**Files:**
- Create: `app/templates/layouts/list.html`、`detail.html`、`form.html`、`flow.html`（都 `extends "base.html"`）
- Test: `tests/test_ui_components.py`

**Interfaces（骨架提供的區塊）:**
- 必填：`{% block page_title %}`（唯一 `h1`）、`{% block page_subtitle %}`（一句話）、`{% block body %}`。
- 選填：`{% block primary_action %}`（只能放一個 `button(kind="primary")`）、`{% block intro %}`（自動包進 `page_intro`）、`{% block crumbs %}`（兩層以上的頁才用）。
- `flow.html` 額外在標題下輸出 `flow_steps(student_progress)`；`list.html` 有 `{% block filters %}`（放分段控制與搜尋）。
- 骨架自己處理 `masthead`、`footer`、`data-page`（頁面設 `page_name`）。

- [ ] **Step 1: Write the failing test**（建一個只在測試用的子模板字串，繼承各骨架後渲染）

```python
@pytest.mark.parametrize("layout", ["list", "detail", "form", "flow"])
def test_layout_renders_one_h1_and_folded_intro(render_child, layout):
    html = render_child(layout, title="測試頁", subtitle="一句話", intro="很長的說明")
    assert html.count("<h1") == 1 and '<details class="page-intro">' in html

def test_flow_layout_shows_steps_for_new_student(render_child_as_new_student):
    html = render_child_as_new_student("flow")
    assert "收集資料" in html.split('aria-current="step"')[1][:200]
```

- [ ] **Step 2: Run**（basetemp `guard-3`），Expected: FAIL
- [ ] **Step 3: 實作** 骨架；手機時標題區上下內距減半，校園主題下大標題不用藍色色塊。
- [ ] **Step 4: Run**，Expected: passed
- [ ] **Step 5: Commit** `git commit -m "四種頁面骨架：清單、細項、表單、流程"`

### Task 4: 元件說明頁＋維護者設計規範

**Files:**
- Create: `app/templates/dev_styleguide.html`（用 `detail` 骨架，列出所有元件與一句用法）
- Modify: `app/routes/main.py`（`GET /dev/styleguide`：只有 `LOCAL_DEMO_MODE` 或 `TESTING` 時回 200，否則 404）
- Create: `docs/04_圖表與介面/AI_學生端設計規範_2026-11-03.md`（本文件「設計規範」七條＋骨架與元件怎麼選＋守門測試失敗時怎麼辦＋怎麼調低上限）
- Test: `tests/test_ui_components.py`

- [ ] **Step 1: Write the failing test**

```python
def test_styleguide_only_in_demo_or_test(app_factory):
    assert app_factory(LOCAL_DEMO_MODE=True).test_client().get("/dev/styleguide").status_code == 200
    assert app_factory(LOCAL_DEMO_MODE=False, TESTING=False).test_client().get("/dev/styleguide").status_code == 404
```

- [ ] **Step 2～4:** Run FAIL → 實作 → Run passed（basetemp `guard-4`）
- [ ] **Step 5: Commit** `git commit -m "元件說明頁與學生端設計規範文件"`

### Task 5: 搬「推薦排序」到清單骨架（含邊打邊篩）

**Files:**
- Modify: `app/templates/student_matching.html`（改 `extends "layouts/list.html"`）
- Modify: `app/routes/student.py`（推薦排序輸出全部校系，前 20 名以外標 `data-extra`）
- Modify: `app/static/js/components.js`（`initLiveFilter()`）
- Modify: `tests/design_budget.py`（`/student/matching` 加入 `MIGRATED_PAGES`；`PAGE_PRIMARY_BUTTONS` 調成 1；CSS 上限照實際減少後的數字調低）
- Test: `tests/test_matching_page.py`（新增項目）

- [ ] **Step 1: Write the failing test**

```python
def test_matching_uses_segmented_and_one_primary(student_client):
    html = student_client.get("/student/matching").get_data(as_text=True)
    assert html.count('class="segmented"') == 2   # 二技／插大、橫條／長條
    assert 'href="/student/matching?track=transfer' in html  # 沒有 JS 也能切換

def test_matching_renders_all_rows_for_live_filter(student_client, twotech_total):
    html = student_client.get("/student/matching").get_data(as_text=True)
    assert html.count("data-match-row") == twotech_total
    assert html.count("data-extra") == twotech_total - 20
    assert "data-live-filter" in html and "data-filter-empty" in html

def test_search_still_works_without_javascript(student_client):
    assert "國立臺北商業大學" in student_client.get("/student/matching?q=北商").get_data(as_text=True)
```

- [ ] **Step 2: Run**（basetemp `guard-5`），Expected: FAIL
- [ ] **Step 3: 實作** 主要按鈕只留「請小助手幫我規劃升學」；「找」改次要；拿掉「← 回目標校系」；開頭說明放 `intro`。JS：輸入 150ms 去抖動，關鍵字以空白拆開、每個都要出現在 `data-match-text`；有關鍵字時忽略 `data-extra` 收合；全部隱藏時顯示 `[data-filter-empty]`；Enter 照常送出。這頁原本的 `[data-page="student-matching"]` CSS 規則改用元件後刪掉。
- [ ] **Step 4: Run** 本檔＋守門測試，Expected: passed
- [ ] **Step 5: Commit** `git commit -m "推薦排序改清單骨架：分段控制、單一主要按鈕、邊打邊篩"`

### Task 6: 搬「目標校系」到流程骨架

**Files:**
- Modify: `app/templates/student_targets.html`（改 `extends "layouts/flow.html"`）
- Modify（使用者已選 A）： `app/templates/partials/target_explorer.html` 拿掉排行與篩選、`app/routes/student.py::target_list` 不再算排行；依賴舊畫面的測試（`tests/test_matching_page.py`、`tests/test_teammate_admission_eligibility.py` 斷言目標校系頁有排行的項目）改成斷言推薦排序頁。
- Modify: `tests/design_budget.py`（加入 `MIGRATED_PAGES`、調低上限）

- [ ] **Step 1: Write the failing test**

```python
def test_targets_page_is_flow_layout(student_client):
    html = student_client.get("/student/targets").get_data(as_text=True)
    assert 'class="flow-steps"' in html

def test_targets_page_no_longer_duplicates_ranking(student_client):
    html = student_client.get("/student/targets").get_data(as_text=True)
    assert "顯示排行" not in html and "準備度排行" not in html
    assert 'href="/student/matching' in html and "找更多校系" in html
```

- [ ] **Step 2～4:** Run FAIL → 實作（組員的資格比對結果仍在推薦排序細項頁顯示，不刪功能）→ 完整測試 passed（basetemp `guard-6`）
- [ ] **Step 5: Commit** `git commit -m "目標校系改流程骨架；排行集中在推薦排序"`

### Task 7: 搬「招生時程」（細項骨架）與「小助手寫自傳」（流程骨架）

**Files:**
- Modify: `app/templates/student_schedule.html`、`app/templates/student_autobiography.html`
- Modify: `tests/design_budget.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.parametrize("path", ["/student/schedule", "/student/autobiography"])
def test_pages_use_layouts(student_client, path):
    html = student_client.get(path).get_data(as_text=True)
    assert html.count("<h1") == 1 and "← 回" not in html
    assert 'class="flow-steps"' in html if path.endswith("autobiography") else True
```

- [ ] **Step 2～4:** Run FAIL → 實作（自傳頁原本的 `[data-page="student-autobiography"]` 規則改用元件，能刪就刪）→ Run passed（basetemp `guard-7`）
- [ ] **Step 5: Commit** `git commit -m "招生時程、自傳改用骨架"`

### Task 8: 手機小助手按鈕不擋內容

**Files:**
- Modify: `app/static/css/components.css`
- Test: `tests/test_ui_components.py`

- [ ] **Step 1: Write the failing test**

```python
def test_assistant_button_collapses_on_phones():
    text = COMPONENTS_CSS.read_text(encoding="utf-8")
    assert ".assistant__toggle" in text and "@media (max-width: 480px)" in text
```

- [ ] **Step 2～4:** FAIL → 480px 以下縮成 56px 圓鈕（文字視覺隱藏、報讀讀得到）、`main` 底部留 5.5rem → passed
- [ ] **Step 5: Commit** `git commit -m "手機版小助手按鈕縮成圓鈕，不蓋住內容"`

### Task 9: 前後對照、實測、紀錄

**Files:**
- 已有：`docs/superpowers/plans/2026-11-03-ui-audit.js`
- Modify: `docs/03_開發紀錄/development-log.md`、`docs/05_交接與專案管理/handoff.md`

- [ ] **Step 1:** 完整測試 `D:\democase\ai\.venv\Scripts\python.exe -m pytest -q --basetemp=logs/test-runs/guard-full`，Expected: 全部通過
- [ ] **Step 2:** 量測腳本重量，目標：目標校系 ≤ 3 螢幕（選 A）、四頁實心主要按鈕各 ≤ 1、手機首屏內容從上方 35% 以內開始；程式指標（頁面專屬規則、寫死顏色、`style=`）比量測表少。
- [ ] **Step 3:** 390px 手機與桌機實測：步驟列、說明展開、分段切換、邊打邊篩（含第 21 名以後）、關掉 JS 後表單可用、小助手不擋按鈕；前後截圖放日誌。
- [ ] **Step 4:** 日誌與交接（前後數字表、`design_budget.py` 新上限），Commit `git commit -m "開發日誌：學生端版型系統第一批"`

## 之後（不在本計畫內）

- 其他頁逐頁搬：每搬一頁，加入 `MIGRATED_PAGES` 並調低 `design_budget.py`。建議順序：活動與經歷（4.2 螢幕）→ 成績單／證照 → 教師端。
- 首頁「我的五年」：使用者決定先不動；之後要改也走同一套骨架與元件。
- 頁面切換動畫：版型穩定後再評估。

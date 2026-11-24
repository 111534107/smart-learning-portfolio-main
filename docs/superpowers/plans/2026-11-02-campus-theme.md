# 校園招生風主題（參考臺中科大招生網站）實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 非首頁的學生、教師、科辦、管理員頁面改成「暖奶油底＋深藍／焦糖色標題帶＋大圓角白卡」的校園招生風，學生頁右側加快捷鈕（招生時程、寫自傳、回到頂端）。

**Architecture:** 新增一個主題樣式檔 `theme-campus.css`，排在 `design-system.css` 後面載入；`base.html` 在非首頁的 `<body>` 加 `data-theme="campus"`，主題檔只在這個屬性底下覆寫設計變數和少數元件外觀。不改任何頁面模板的結構，所以跟 GPT 正在改的頁面不會衝突；要撤掉只要拿掉一個屬性。

**Tech Stack:** Flask 3、Jinja2、純 CSS（`color-mix`、CSS 變數）、pytest。

**Spec:** 使用者 2026-11-02 指定的參考 https://admission.nutc.edu.tw/ ；本計畫「設計取樣」一節就是規格。

## 設計取樣（2026-11-02 實際量測該網站）

| 元素 | 網站做法 | 我們採用的值 |
| --- | --- | --- |
| 頁面底色 | 暖奶油 `rgb(253,243,226)` | `--paper: #fdf3e2`、`--paper-deep: #f6e6c8` |
| 卡片 | 白底、大圓角、淡陰影 | `--sheet: #fffdf8`、`--radius-card: 14px` |
| 卡片標題帶 | 深藍漸層、焦糖漸層交替，白字 | 深藍 `#1f3a5f→#2c5282`；焦糖 `#94652a→#9c6a2c`（白字對比要 ≥ 4.5:1，原站的 `#ca9954` 不夠，所以加深） |
| 區塊標題 | 置中，前面一小段橫線「— 近期招生及活動訊息」 | `.sheet__head h2::before` 一段 1.2em × 3px 焦糖線 |
| 強調色 | 焦糖 `#ca9954`、赤陶 `#cd815b` | `--accent-warm: #ca9954`（只用在線條、底線，不當文字底色）、`--accent-terra: #cd815b` |
| 右側浮動鈕 | 行事曆、筆，圓形；右下 TOP | 學生頁：招生時程、小助手寫自傳、回到頂端 |
| 字型 | 微軟正黑體 | 沿用現有 `--font-sans`（已含微軟正黑體） |

## Global Constraints

- 首頁不動：`data-page` 是 `student-dashboard` 或 `public-home` 的頁面**不得**有 `data-theme="campus"`。
- 只借配色與版面節奏；**不得**使用臺中科大的校徽、名稱、插圖、照片或任何素材。
- 白字底色的對比 ≥ 4.5:1（WCAG AA）。
- 按鈕維持現有圓角 `var(--radius)`，不做膠囊按鈕（專題 `AGENTS.md` §9）。
- 動畫要尊重 `prefers-reduced-motion: reduce`。
- 不改頁面模板結構；只動 `base.html`、新增 `theme-campus.css`、新增一個 partial。
- 用 git worktree 在 `bfbaa58` 之後的最新提交上做，不要碰 GPT 尚未提交的檔案；完成後不推送、不合併。

## 使用者決定（2026-11-02）

1. 底色用奶油色 `#fdf3e2`（使用者選定；`AGENTS.md` §9「避開米白背景」以這次最新指示為準，之後要改只需改 `--paper` 一行）。
2. 快捷鈕只給學生（教師之後再說）。
3. 執行方式：Claude 在本對話逐項實作，工作資料夾 `D:\democase\_worktrees\ai-wt-campus-theme`，分支 `feat/campus-theme`（從 `bfbaa58` 開出）。

## Review Focus

1. 標題帶裡有按鈕或連結（例如「看全部校系的推薦排序 →」）時，文字要是白色且看得見 → Task 2 測樣式規則存在，Task 4 瀏覽器實測。
2. 390px 手機寬度：右側浮動鈕不能擋住內容或表單送出鈕 → Task 3 規則、Task 4 實測。
3. 第一個子元素不是 `.sheet__head` 的白卡（例如只有一段文字）不能被套上標題帶 → Task 2 選擇器只對 `:first-child`。
4. 未登入、教師、管理員頁面不應出現學生快捷鈕 → Task 3 測試。
5. 列印（學校要印功能表、備審）：主題的底色與浮動鈕不能印出來 → Task 3 加 `@media print` 隱藏，Task 4 用列印預覽確認。

---

### Task 1: 主題開關與設計變數

**Files:**
- Modify: `app/templates/base.html:12-14`（加樣式檔連結、`<body>` 加 `data-theme`）
- Create: `app/static/css/theme-campus.css`
- Test: `tests/test_theme_campus.py`

**Interfaces:**
- Produces: `<body data-theme="campus">`（非首頁）；CSS 變數 `--radius-card`、`--band-navy`、`--band-caramel`、`--accent-warm`、`--accent-terra`，Task 2、3 使用。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_theme_campus.py：沿用 tests/test_ui_shell.py 的 ui_app() 寫法（另建 teacher 帳號）
def test_home_pages_keep_classic_look():
    client = ui_app().test_client()
    html = client.get("/").get_data(as_text=True)
    assert 'data-theme="campus"' not in html

def test_student_dashboard_keeps_classic_look():
    client = login(ui_app(), "ui-student")
    html = client.get("/student/dashboard").get_data(as_text=True)
    assert 'data-page="student-dashboard"' in html
    assert 'data-theme="campus"' not in html

def test_other_pages_use_campus_theme_after_design_system():
    client = login(ui_app(), "ui-student")
    html = client.get("/student/targets").get_data(as_text=True)
    assert 'data-theme="campus"' in html
    assert html.index("css/design-system.css") < html.index("css/theme-campus.css")

def test_theme_css_has_balanced_braces_and_scoped_rules():
    text = THEME_CSS.read_text(encoding="utf-8")
    assert text.count("{") == text.count("}")
    assert '[data-theme="campus"]' in text
    assert "--paper: #fdf3e2" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\democase\ai\.venv\Scripts\python.exe -m pytest tests/test_theme_campus.py -q --basetemp=logs/test-runs/theme-1`
Expected: FAIL（找不到 `data-theme`、檔案不存在）

- [ ] **Step 3: 實作**

`base.html`：在 `design-system.css` 後加 `theme-campus.css` 連結（全站都載入，靠屬性限定範圍）；`<body>` 加
`{% if page_name|default('workspace') not in ('student-dashboard', 'public-home') %} data-theme="campus"{% endif %}`。
`theme-campus.css` 開頭寫一段註解說明來源與撤除方式，接著 `[data-theme="campus"] { ... }` 覆寫：`--paper: #fdf3e2; --paper-deep: #f6e6c8; --sheet: #fffdf8; --line: #ead9b8; --radius-card: 14px; --band-navy: linear-gradient(90deg, #1f3a5f, #2c5282); --band-caramel: linear-gradient(90deg, #94652a, #9c6a2c); --accent-warm: #ca9954; --accent-terra: #cd815b;`，並讓 `.sheet` 用 `border-radius: var(--radius-card)`。`<meta name="theme-color">` 不動。

- [ ] **Step 4: Run test to verify it passes**

Run: 同 Step 2。Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add app/templates/base.html app/static/css/theme-campus.css tests/test_theme_campus.py
git commit -m "非首頁加校園招生風主題開關與設計變數（首頁不動）"
```

### Task 2: 卡片標題帶與區塊標題橫線

**Files:**
- Modify: `app/static/css/theme-campus.css`
- Test: `tests/test_theme_campus.py`

**Interfaces:**
- Consumes: Task 1 的 `--band-navy`、`--band-caramel`、`--radius-card`、`--accent-warm`。

- [ ] **Step 1: Write the failing test**

```python
def test_sheet_heads_become_bands_with_white_links():
    text = THEME_CSS.read_text(encoding="utf-8")
    assert '[data-theme="campus"] .sheet > .sheet__head:first-child' in text
    assert "var(--band-navy)" in text and "var(--band-caramel)" in text
    assert '[data-theme="campus"] .sheet > .sheet__head:first-child a' in text  # 標題帶裡的連結要白字

def test_band_colours_pass_contrast_with_white_text():
    # 漸層兩端的顏色都要 ≥ 4.5:1
    for hex_colour in ("#1f3a5f", "#2c5282", "#94652a", "#9c6a2c"):
        assert contrast_with_white(hex_colour) >= 4.5, hex_colour
```

`contrast_with_white(hex) -> float` 寫在測試檔裡，用 WCAG 相對亮度公式。（已先算過：`#9c6a2c` 約 4.7:1、`#94652a` 約 5.0:1；原站 `#ca9954` 只有約 2.6:1。）

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\democase\ai\.venv\Scripts\python.exe -m pytest tests/test_theme_campus.py -q --basetemp=logs/test-runs/theme-2`
Expected: FAIL（找不到標題帶規則）

- [ ] **Step 3: 實作**

在主題檔加：
- `.sheet` 設 `--sheet-pad: clamp(1.1rem, 2.5vw, 1.75rem)`、`padding: var(--sheet-pad)`、`overflow: hidden`。
- `.sheet > .sheet__head:first-child`：負外距 `calc(-1 * var(--sheet-pad))` 貼滿卡片上緣，內距 `.9rem var(--sheet-pad)`，`background: var(--band-navy)`、白字；`.sheet:nth-of-type(even) > .sheet__head:first-child` 改 `var(--band-caramel)`。
- 標題帶內的 `a`、`.button`、`.tag`、`.muted` 改白字或白框；`.button` 改透明底白框。
- `.sheet__head h2::before`（不在標題帶裡的、以及 `.page-head h1`）：前面一段 `1.2em × 3px` 的 `var(--accent-warm)` 橫線，`display: inline-block; vertical-align: middle; margin-right: .5em`。
- `.record-card`、`.program-card` 改 `border-radius: var(--radius-card)`、`border-color: var(--line)`、淡陰影 `0 6px 18px -12px rgb(60 40 10 / 35%)`；hover 上浮 2px，`prefers-reduced-motion: reduce` 時不動。

- [ ] **Step 4: Run test to verify it passes**

Run: 同 Step 2。Expected: 全部 passed

- [ ] **Step 5: Commit**

```bash
git add app/static/css/theme-campus.css tests/test_theme_campus.py
git commit -m "校園主題：卡片標題帶（深藍／焦糖交替）與區塊標題橫線"
```

### Task 3: 學生頁右側快捷鈕（招生時程、寫自傳、回到頂端）

**Files:**
- Create: `app/templates/partials/quick_dock.html`
- Modify: `app/templates/base.html`（`</main>` 後 include）
- Modify: `app/static/css/theme-campus.css`
- Test: `tests/test_theme_campus.py`

**Interfaces:**
- Consumes: 模板變數 `user`（各學生頁已傳入）、`page_name`；路由 `student.schedule`、`student.autobiography`。
- Produces: `<nav class="quick-dock" aria-label="快捷功能">`，內含 3 個連結。

- [ ] **Step 1: Write the failing test**

```python
def test_student_pages_show_quick_dock():
    client = login(ui_app(), "ui-student")
    html = client.get("/student/targets").get_data(as_text=True)
    assert 'class="quick-dock"' in html
    assert 'href="/student/schedule"' in html
    assert 'href="/student/autobiography"' in html
    assert 'href="#main-content"' in html

def test_quick_dock_hidden_on_home_and_for_teachers():
    client = login(ui_app(), "ui-student")
    assert 'class="quick-dock"' not in client.get("/student/dashboard").get_data(as_text=True)
    teacher = login(ui_app(), "ui-teacher")
    assert 'class="quick-dock"' not in teacher.get("/teacher/dashboard").get_data(as_text=True)
    assert 'class="quick-dock"' not in ui_app().test_client().get("/login").get_data(as_text=True)

def test_quick_dock_is_not_printed_and_respects_small_screens():
    text = THEME_CSS.read_text(encoding="utf-8")
    assert "@media print" in text and ".quick-dock" in text
    assert "@media (max-width: 480px)" in text
```

（教師首頁路由請以 `app/routes/teacher.py` 實際網址為準；`/student/schedule` 也以 `url_for("student.schedule")` 實際輸出為準。）

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\democase\ai\.venv\Scripts\python.exe -m pytest tests/test_theme_campus.py -q --basetemp=logs/test-runs/theme-3`
Expected: FAIL（找不到 `quick-dock`）

- [ ] **Step 3: 實作**

`quick_dock.html` 只在 `user is defined and user and user.role == "student"` 且有 `data-theme="campus"` 的同一條件下輸出；三個連結用文字＋`aria-hidden` 的簡單符號（📅、✎、↑），每個都有可見的中文提示（`title` 不夠，用滑過時展開的文字標籤，鍵盤 focus 也展開）。
CSS：`position: fixed; right: 0; top: 40vh;` 深藍、深焦糖（`#94652a`）交替的半圓角標籤，赤陶 `#cd815b` 只當左邊框線（赤陶配白字對比不到 4.5:1）（只有左邊圓角，貼齊右緣，不是膠囊按鈕）；`@media (max-width: 480px)` 改成右下角一排小圓鈕並留出 `padding-bottom` 給頁面，避免擋住送出鈕；`@media print` 隱藏，並把 `[data-theme="campus"]` 底色改白。

- [ ] **Step 4: Run test to verify it passes**

Run: 同 Step 2。Expected: 全部 passed

- [ ] **Step 5: Commit**

```bash
git add app/templates/partials/quick_dock.html app/templates/base.html app/static/css/theme-campus.css tests/test_theme_campus.py
git commit -m "學生頁右側快捷鈕：招生時程、寫自傳、回到頂端（列印時隱藏）"
```

### Task 4: 完整測試、瀏覽器實測、紀錄

**Files:**
- Modify: `docs/03_開發紀錄/development-log.md`（最上面加一節）
- Modify: `docs/05_交接與專案管理/handoff.md`（最上面狀態加一行）

- [ ] **Step 1: 完整測試**

Run: `D:\democase\ai\.venv\Scripts\python.exe -m pytest -q --basetemp=logs/test-runs/theme-full`
Expected: 全部通過（數字照實記錄）

- [ ] **Step 2: 瀏覽器實測**（`scripts/run_local_demo.py`，`student_demo`／`demo2026`、`teacher_demo`）

逐頁截圖：目標校系、推薦排序、校系細項、缺什麼、自傳、招生時程、教師學生頁；各看桌機與 390px。確認：首頁（`/student/dashboard`、`/`）外觀和改之前一樣；標題帶裡的連結看得見；浮動鈕不擋送出鈕；列印預覽沒有底色和浮動鈕；系統「減少動態效果」開啟時卡片不上浮。

- [ ] **Step 3: 寫開發日誌與交接**（日期、開發者、目標、修改檔案、驗證結果、下一步；不用英文詞）

- [ ] **Step 4: Commit**

```bash
git add docs/03_開發紀錄/development-log.md docs/05_交接與專案管理/handoff.md
git commit -m "開發日誌：校園招生風主題"
```

## 不在本計畫內

- 原神「灰眸訊息」風格的小助手對話介面（左側主題清單＋紅點、右側對話泡泡、「這是哪來的資料…」）：另寫一份計畫，可沿用本計畫的變數。
- 首頁改版。

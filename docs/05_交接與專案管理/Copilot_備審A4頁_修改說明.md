# 備審 A4 頁面預覽修改說明

## 完成內容

- 新增 `app/templates/student_portfolio_view.html`，沿用學生頁的 base、導覽與頁尾，提供封面、依校系加權排序的目錄，以及各章節 A4 預覽。
- 新增 `app/static/css/portfolio-view.css`，設定白底黑字的 A4 紙面、紙張間距與陰影、手機等比例縮放、列印版面、減少動態效果偏好。
- 在備審資料頁 Word 下載旁新增「預覽備審 A4 頁面」按鈕，連到 `student.portfolio_view`。

## 資料呈現

- 章節內容取自 `portfolio_view.build()` 傳入的 `data`：求學歷程、自傳、讀書計畫與履歷項目均依 `data.toc` 順序呈現。
- 目錄連結使用章節代碼錨點；紙面頁碼使用目錄頁碼，求學歷程按年級、自傳與讀書計畫按段落長度分頁遞增。
- 空資料顯示對應提示，自傳空白時提供前往小助手撰寫的連結；Word 下載與返回連結使用路由傳入的 `word_url`、`gap_url`。

## 本次檔案

- `app/templates/student_portfolio_view.html`（新增）
- `app/static/css/portfolio-view.css`（新增）
- `app/templates/student_gap.html`（新增預覽入口）
- `docs/05_交接與專案管理/Copilot_備審A4頁_修改說明.md`（新增）

## 專案內檔名差異

任務提到的 `app/templates/student_target_gap.html` 在工作目錄中不存在；實際備審資料頁是 `app/templates/student_gap.html`，因此預覽按鈕加在該頁。工作目錄中也找不到 `AGENTS.md`，無法依要求閱讀第 9 節。

依任務限制，本次未修改 Python，亦未執行指令、測試或安裝套件。

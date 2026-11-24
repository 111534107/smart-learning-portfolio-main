# 自傳字數預算提示修改說明

## 做法

- 在自傳編輯畫面的段落標題、目錄項目、手機小標籤與段落區塊加入逐段字數預算，顯示「現有字數／上限」。
- 輸入時即時更新段落字數、整份字數、警示文字與預覽數字；超段上限或全份超過 120% 會使用既有警示色與 `⚠` 圖示。
- 應用後端提供的 `budgets`、`budget_total` 與 `data_updates`；資料更新提示放在工具列下方、段落小標籤上方，並依校系與更新筆數儲存在 `localStorage`。
- 手機版維持工具列單列與 44px 可點元件，並保留 `prefers-reduced-motion` 與既有深淺色 CSS 變數。

## 修改檔案

- `app/templates/student_autobiography.html`
- `app/static/js/canva-editor.js`
- `app/static/css/design-system.css`
- `docs/05_交接與專案管理/Copilot_字數預算提示_修改說明.md`

## 未修改

- 未修改 Python、列印／Word 路徑、套件或第三方相依。
- 未執行終端機指令、Git 操作、測試或安裝。

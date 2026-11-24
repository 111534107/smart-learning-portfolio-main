# Gemini 手機打字模式修改說明

## 做法

- 新增全站 `typing-mode.js`：偵測文字輸入焦點與 `visualViewport` 高度變化，在手機螢幕加上 `body.is-typing`，失焦延遲 250 毫秒移除。
- 手機輸入時隱藏底部功能列、小助手入口、導覽邀請及偵測到的底部固定／黏著橫條；輸入框在手機會延遲 300 毫秒置中捲動。
- 實習履歷抽屜改為手機預設收合，最高高度 40dvh；打字時整個抽屜隱藏，桌機及 900px 以上版面維持既有模式。
- 自傳與實習履歷頁新增捲動閱讀模式：頁首捲動到中間會隱藏，接近頁面最上／最下 80px 時恢復顯示；實習履歷下載按鈕同步套用。
- 加入 `prefers-reduced-motion` 支援，啟用時不使用轉場動畫。

## 修改檔案

- `app/static/js/typing-mode.js`
- `app/static/css/design-system.css`
- `app/static/css/student-v2/home-desk.css`
- `app/templates/base.html`

## 尚未做到

- 尚未在瀏覽器與實機進行視覺驗收；依要求未執行測試、安裝套件或 Git 指令。

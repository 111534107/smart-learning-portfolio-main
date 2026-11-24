# 缺曠自動填入修改說明

## 完成項目

- 缺曠記錄頁的 `曠課`、`遲到`、`事假`、`病假`、`生理假`、`公假`、`喪假`、`總計` 時數欄已改為可編輯輸入框，欄位沿用 `abs_0` 到 `abs_7`。
- 輸入時只保留數字，失焦時自動補上「節」；總計格提供滑過或點 `?` 顯示的說明。
- 在表格上方加入頁面內的自動填入按鈕，含截圖／PDF 選檔與已登錄合計讀取。
- 截圖／PDF 成功讀取後會預填八格與查詢區間；查詢區間原本有值時會詢問是否覆蓋。
- 成功與失敗狀態會顯示在頁面內，原本數值在失敗時不會被覆蓋。
- 加入手機 375px 的換行與至少 44px 高度按鈕樣式，並尊重 `prefers-reduced-motion`。
- 編輯用按鈕、說明與狀態使用 `rz-editonly` 或對應容器，列印／匯出時隱藏；紙面仍維持白底黑字與原有表格版型。
- 選取的截圖／PDF 會沿用既有 `abs_image` 圖片槽機制：透過既有 `[data-slot-file]` 變更事件上傳或轉 PDF 分頁並放入槽位。

## 修改檔案

- `app/templates/student_internship_resume.html`
- `app/static/js/resume-editor.js`
- `app/static/css/student-v2/home-desk.css`
- `docs/05_交接與專案管理/Gemini_缺曠自動填入_修改說明.md`

## API 串接狀態

- 已串接同站端點 `POST /student/internship-resume/absence/read`，multipart 欄位為 `file`，並帶入既有表單的 `csrf_token`。
- 已串接同站端點 `GET /student/internship-resume/absence/saved`。
- 缺曠讀取與已登錄合計端點已存在於後端；本次未改動 Python。
- 缺曠圖片／PDF、數字只經目前系統的同站路徑處理，不新增其他外部網址。

## 還沒接上的部分

- 無。前端已沿用既有圖片／PDF slot 機制接上 `abs_image`。

# Copilot 彩蛋修改說明

## 做法
- 新增學生端彩蛋樣式與腳本，僅在學生登入頁載入。
- 畢業門檻量表加入 `data-meter-*` 屬性，以瀏覽器 localStorage 比對進展。
- 備審下載頁偵測下載／寄送連結、檔案送出與既有檢核清單，顯示可跳過的信封提示。
- 新增里程碑資料片段與可手動呼叫的 `window.showMilestone(item)`。
- 新增致謝名單資料檔、三擊校徽對話框及焦點處理。
- 所有動畫皆會依 prefers-reduced-motion 或 `.reduced-motion` 改為靜態提示。

## 檔案清單
- `app/static/css/easter-eggs.css`
- `app/static/js/easter-eggs.js`
- `app/templates/partials/milestones.html`
- `app/content/credits.py`
- `app/templates/base.html`
- `app/templates/student_graduation_check.html`
- `docs/05_交接與專案管理/Copilot_彩蛋_修改說明.md`

## 還沒做到／後續要確認
- 現有後端未提供動態里程碑資料；片段目前為空陣列，未來可由後端填入 JSON。
- 致謝清單目前僅為佔位資料；尚無真實姓名。
- 打包下載成功無統一下載完成事件，因此以連結／表單操作及已存在的 `mailed` 回傳參數偵測顯示；實際檔案是否成功交付仍由既有後端頁面回應判定。

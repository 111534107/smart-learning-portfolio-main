# 履歷自傳一鍵生成修改說明

## 做法

- 在實習履歷自傳頁的編輯工具列與紙面頂端增加「請小助手依我勾選的資料生成自傳」主要按鈕，按鈕高度至少 44px。
- 前端以整份 `resume-form` 建立 `FormData`，POST 至 `/student/internship-resume/bio/generate`；沿用表單的 CSRF 欄位。
- 「參考學校建議段落」模式會把回傳的四段填入對應欄位；欄位已有內容時逐段詢問是否取代。
- 「自由撰寫」模式會把四段依序以空一行連接並填入；已有內容時詢問是否取代。
- 回傳的 hints 會在家庭生活與未來生涯規劃欄位下方顯示為引導文字，不使用錯誤色。
- 生成成功時顯示小助手說明與逐段修改、儲存草稿提示；生成中停用按鈕並顯示整理中文字；失敗時顯示友善中文訊息。
- 家庭生活與未來生涯規劃欄位上方加入固定項目說明，抽屜中的家庭生活輸入區改為說明，不再要求學生在抽屜自行撰寫。
- 自由撰寫模式下方會依勾選的經歷與證照顯示「會列在自傳後面」合併清單。
- 「清空重填」移到上方工具列旁，保留原有重置表單 action 與 data-confirm 確認視窗，外觀使用既有 danger 色、紅色外框、垃圾桶圖示與 44px 以上高度。
- 新增編輯畫面樣式、375px 手機版調整、列印隱藏與 prefers-reduced-motion 支援；紙面字型與白底黑字規則維持原有標楷體設定。

## 修改檔案

- `app/templates/student_internship_resume.html`
- `app/static/js/resume-editor.js`
- `app/static/js/home-desk.js`
- `app/static/css/student-v2/home-desk.css`
- `docs/05_交接與專案管理/Copilot_履歷自傳一鍵生成_修改說明.md`

## 未修改

- 未修改任何 Python 檔案；既有的 `/student/internship-resume/bio/generate` 路由與 `app/services/resume_bio_ai.py` 邏輯直接沿用。

## 尚未做到

- 未執行瀏覽器操作驗證、前端測試或終端機指令；依本次任務限制僅進行檔案讀取與修改。

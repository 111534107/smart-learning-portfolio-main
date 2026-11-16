# Google Drive 雲端主線展示原型與可行性評估

> 狀態：展示原型／可行性驗證，不是已核准的正式規格。  
> 專案落點：`D:\democase\ai-wt-story`，分支 `feat/journey-home`。  
> 目的：先用可操作畫面向組員和指導老師說明，再依 OAuth 實測與團隊決策排定是否納入專題主線。

## 一頁會議摘要

### 想解決的問題

學生的課程、作品和證明檔案散落在不同位置。準備升學資料時，常要重新找檔案、回想成果對應哪個要求。提案是讓 Google Drive 保存原始檔，學習歷程系統把已選檔案連到成果紀錄，再整理目標、目前資料和待補項目。

### 展示流程

1. 以假學生和假校系資料展示「選目標 → 整理成果 → 看見待補資料 → 知道下一步」。
2. 使用者按「用 Google Drive 選一份檔案」，在 Google Picker 親自選取一個無個資的測試檔。
3. 原型向 Drive 查詢所選檔案的名稱、類型與原始檔連結，將它暫時顯示在展示成果旁。
4. 重新整理頁面後展示連結消失；原始檔仍留在 Google Drive，系統不複製或移動它。

### 初步評估

| 面向 | 判斷 | 根據與限制 |
|---|---|---|
| 技術可行性 | 可做小型驗證 | Google Picker 可讓使用者挑選 Drive 檔案，Drive API 可查詢單一檔案中繼資料；目前尚未完成 OAuth 實際授權。 |
| 時間可控性 | 範圍縮小後可控 | 先只做授權、挑一個檔案、顯示中繼資料與原始連結；不接 Docs、Calendar、Gmail、OCR、批量同步或檔案上傳。 |
| 學校帳號限制 | 尚待確認 | Google Workspace 管理政策、OAuth 測試使用者設定或未驗證應用提示可能影響學校信箱登入，需用本人帳號實測；必要時詢問學校管理員。 |
| 隱私與權限 | 原型可限制，正式版仍需設計 | 使用 `drive.file`，由使用者挑選檔案；原型只呼叫讀取中繼資料的 API，不保存長期 token、不保存所選檔案。此 OAuth scope 對使用者選取／開啟的檔案仍包含建立或修改能力，因此不能把它描述成 Google 層級的唯讀權限。 |
| 正式上線準備度 | 尚未達成 | 目前是本機展示原型；正式功能還需決定帳號對應、token 保存與撤銷、檔案連結授權、資料保存期限、部署 HTTPS 與學校核准。 |

### 建議決策

先完成一次本機真實選檔，驗證 OAuth、Picker、Drive API 及學校帳號政策。成功後請組員與老師決定是否將「連結 Drive 原始證明」列入正式規格；驗證前不承諾全面改寫系統，也不把其他 Google 服務排入本期。

## 原型範圍與資料邊界

- 公開 `/proposal-preview` 仍可匿名瀏覽，畫面中的學生、校系、成果與缺件均為假資料。
- Google 連線只有使用者主動按鈕並完成授權後才會開始；Picker 只讓使用者選檔，不列出整個雲端硬碟。
- 後端只向 `files.get` 查詢所選檔案的 `id`、`name`、`mimeType`、`webViewLink`；不下載檔案內容、不上傳、不修改、不刪除、不改分享權限。
- Access token 只存在當次頁面記憶體，隨檔案 ID 一起送往本機 Flask 路由作即時驗證；不寫入資料庫、Flask session、瀏覽器 localStorage 或日誌。展示狀態不跨頁面重新整理保存。
- Drive 檔名可能包含個人資訊。會議展示前請先選不含姓名、學號、成績或證件資料的測試檔。
- 本原型不判斷學生身分或校系資格、不執行 AI 分析，也不把 115 學年度資料說成現行招生條件。

## Google Cloud 設定檢查表

OAuth 設定值目前尚未提供；請由專案擁有人在自己的 Google Cloud 專案完成設定，不要把秘密貼到對話、文件或 Git：

1. 啟用 Google Drive API 與 Google Picker API。
2. 設定 OAuth 同意畫面為測試用途，將本人準備用來展示的 Google 帳號加為測試使用者。
3. 建立 OAuth 網頁用戶端並允許本機來源 `http://127.0.0.1:5000`。
4. 建立 API 金鑰，限制可用 API 與本機來源；Picker iframe 的來源限制依 Google 官方設定說明檢查。
5. 把用戶端 ID、API 金鑰、Cloud 專案編號填入本機 `.env`，並將 `GOOGLE_DRIVE_PREVIEW_ENABLED=true`。這些真實值不得複製到 `.env.example` 或提交到 Git。
6. 在本機啟動系統並開啟 `http://127.0.0.1:5000/proposal-preview`，實際完成授權、選檔與開啟 Drive 原始檔。

若學校 Workspace 阻擋測試應用或 Drive scope，請先向管理員確認；不要改用廣泛雲端硬碟權限繞過學校限制。

官方設定參考：[Drive API 授權範圍](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)、[Google Picker 網頁整合](https://developers.google.com/workspace/drive/picker/guides/web-picker)、[OAuth 應用程式驗證與測試使用者](https://support.google.com/cloud/answer/13461325?hl=zh-Hant)。

## 報告時可以這樣說

> 我想先驗證一個範圍有限的 Google Drive 流程。Drive 保存原始證明，學生自己選檔後，學習歷程系統只把它連到一筆成果，讓目標、證明和待補資料能放在同一個脈絡中。畫面用假學生資料，實際連線只讀取我親自選的一個測試檔之中繼資料，不會搬動檔案。若學校帳號授權和權限管理實測可行，我再和大家確認是否納入正式規格。

## 需要組員與指導老師決定

1. 正式功能是否採「Drive 保存原檔、系統保存檔案連結與分類」？是否另需要系統上傳副本？
2. 正式登入是否只允許學校 Google Workspace 帳號？由誰確認在學身分與停用離校帳號？
3. 若學生刪除或取消 Drive 分享，系統顯示什麼狀態、如何重新連結？
4. OAuth token、檔案 ID、檔名和連結要保存多久？學校要求誰可檢視或撤銷？
5. Drive 驗證通過後，是否先納入單一證明連結；Docs、OCR 或批量匯入另開決策？

## 後續驗收門檻

### 目前驗收狀態（2026-10-13）

- 原型自動測試：`13 passed`；JavaScript 語法檢查通過。
- 完整測試：`322 passed, 6 failed`。6 個失敗在 Flask-Migrate CLI／資料庫 migration 測試；本機 Python 缺少 `Flask-Migrate`，測試使用的暫存相容 shim 不含 migration CLI。安裝專案依賴後需重跑完整測試。
- 桌面與手機瀏覽器畫面尚未實際檢視：本機 Flask 測試伺服器啟動成功，但瀏覽器工具連線被沙箱拒絕。
- 真實 Google 授權與選檔尚未驗收：OAuth 設定值未提供。

- 本機 OAuth 可由指定 Google 帳號完成；使用者可以取消並安全返回。
- Google Picker 可只選一個一般檔案，Drive API 回傳的 ID 與使用者選擇一致，畫面顯示檔名、類型和 Google 原始檔連結。
- 權限拒絕、token 失效、網路逾時、資料夾或無效檔案 ID 都有清楚訊息，不洩漏 token 或伺服器錯誤。
- 在 DevTools/network 與 Git 差異檢查中確認沒有 token 持久化、沒有檔案內容下載、沒有 Drive 寫入呼叫，也沒有真實個人資料進入截圖或日誌。
- 桌面與手機寬度可操作，鍵盤焦點可見，啟用減少動態效果時沒有必要動畫。

## 來源

- 專案內 UI 方向：[UI/UX 視覺素材盤點與首頁方向](../../04_圖表與介面/03_檢查與圖表規範/AI_檢查報告_UIUX視覺素材盤點.md)；以自製 CSS／SVG 重新表達路徑、拼圖和檔案意象，不直接搬用參考圖。
- 原型入口：`/proposal-preview`。
- 任務交接：[`handoff.md`](../../05_交接與專案管理/handoff.md)。

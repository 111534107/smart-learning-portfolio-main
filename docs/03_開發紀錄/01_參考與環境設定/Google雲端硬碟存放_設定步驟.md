# 學生上傳檔案改存 Google 雲端硬碟：設定步驟（個人帳號測試版）

日期：2026-10-22（台灣時間）

適用：本機展示站（例如 `http://localhost:5019`），用**你自己的個人 Google 帳號**測試（還沒有學校 Workspace 管理權限，依 V1 開發規格 D3、V2 決策 3）。正式導入時改用學校 Workspace 帳號，並在學生自己的學校帳號建立備份（還沒做）。

## 這個功能做什麼

1. 學生在網站上傳成績單、證照、獎懲記錄、佐證檔案 → 後端存進 Google 雲端硬碟裡系統自己建立的資料夾「智慧學習歷程系統上傳檔」→ 資料庫（MySQL／展示用 SQLite）沿用原本的 `file_path` 欄位，記成 `drive:<檔案 ID>/<存檔名稱>`。本機存放的檔案仍是原本的路徑寫法（沒有前綴），兩種可以並存。
2. 權限只要 `drive.file`：系統只碰**自己建立的**檔案與資料夾，看不到這個帳號 Drive 裡其他檔案。
3. 整個系統共用一組連線：由**系統管理員**在「檔案存放設定」頁連上 Google。權杖（含更新權杖）**只放伺服器記憶體**，不寫進資料庫、`.env` 或日誌；網站重開後要請管理員再連一次。
4. OCR、預覽、裁切都讀本機快取 `instance/uploads/drive-cache/`：上傳時順便留一份，快取不見時由後端用檔案 ID 向 Drive 取回。
5. 刪除只標記：本機檔案旁邊寫 `.deleted.json`；Drive 檔案寫 `appProperties`（`slp_deleted_at`、`slp_deleted_reason`），**不丟垃圾桶、不永久刪除**。資料庫沒存進去的孤兒檔（上傳到一半出錯）才丟掉：本機直接刪、Drive 移到垃圾桶（Google 30 天後才清除）。
6. 升學 Agent 不直接瀏覽 Drive：只能用工具「查我的檔案」「取檔案內容」依檔案編號取**學生自己的**檔案中辨識／確認過的欄位，去識別化後才交回 AI；不拿原始檔。
7. 任何一步不能用（`.env` 沒填齊、管理員還沒連線、Google 連不上、上傳失敗），新上傳的檔案一律改存本機，畫面照常。已經存在 Drive 又沒有快取的檔案，在重新連線前預覽會顯示找不到（404）、OCR 顯示「雲端檔案暫時拿不到」。

## 使用者要準備的 Google Cloud 設定

在 <https://console.cloud.google.com/> 用你要測試的個人 Google 帳號登入。若已經依「Google文件自傳編輯_設定步驟.md」做過，可以沿用同一個專案與 OAuth 用戶端，只要做第 4 步的「多加一個重新導向 URI」。

1. **建立專案**（或沿用）：上方專案選單 →「新增專案」→ 名稱例如 `smart-learning-portfolio-demo`。
2. **啟用 Google Drive API**：「API 和服務」→「程式庫」→ `Google Drive API` →「啟用」。
3. **OAuth 同意畫面**（Google Auth Platform）：
   - 使用者類型「**外部**」，發布狀態保持「**測試**」。
   - 範圍只加 `https://www.googleapis.com/auth/drive.file`。
   - 「測試使用者」加入要存放檔案的那個 Google 帳號。
   - 測試模式會顯示「Google 尚未驗證這個應用程式」，按「繼續」即可。
4. **OAuth 用戶端**（類型「網頁應用程式」），在「已授權的重新導向 URI」加：
   - `http://localhost:5019/admin/storage/google/callback`（埠號和你開的展示站一致；用 `127.0.0.1` 開站就另外加 `127.0.0.1` 的版本）。
5. **填到自己的 `.env`**（`.env` 不提交 Git，也不要貼到對話或文件裡）：

   ```
   STORAGE_BACKEND=google_drive
   GOOGLE_OAUTH_CLIENT_ID=（用戶端 ID）
   GOOGLE_OAUTH_CLIENT_SECRET=（用戶端密鑰）
   GOOGLE_STORAGE_REDIRECT_URI=http://localhost:5019/admin/storage/google/callback
   ```

   `GOOGLE_OAUTH_CLIENT_ID`、`GOOGLE_OAUTH_CLIENT_SECRET` 和自傳 Google 文件共用；`STORAGE_BACKEND` 不填或填 `local` 就是本機（預設）。
6. **重新啟動展示站** → 用系統管理員帳號登入 →「檔案存放設定」→「連上 Google 雲端硬碟」→ 登入第 3 步加入的測試帳號並同意。回到設定頁顯示「目前存在：Google 雲端硬碟」就完成了。
7. **實測**：用學生帳號上傳一份合成的成績單（不要用真實個資）→ 到該 Google 帳號的 Drive 看「智慧學習歷程系統上傳檔」資料夾裡有沒有新檔案 → 回網站確認辨識中縮圖、確認頁原圖預覽都正常 → 刪除一個佐證檔案，Drive 裡的檔案應該還在（只多了標記）。

## 如何移除

1. `.env` 刪掉 `STORAGE_BACKEND` 與 `GOOGLE_STORAGE_REDIRECT_URI`（或把 `STORAGE_BACKEND` 改回 `local`），重開網站：新上傳的檔案改存本機。
2. 也可以先在「檔案存放設定」按「中斷 Google 雲端硬碟」，伺服器記憶體裡的權杖會清掉。
3. 到 <https://myaccount.google.com/permissions> 移除本系統的存取權。
4. 已經存在 Drive 的檔案：資料庫仍記著 `drive:` 位置。要完全不用 Drive，請先把那些檔案搬回本機並更新資料庫位置（目前沒有自動搬移工具，屬於後續工作）；只是暫停的話保留即可，本機快取 `instance/uploads/drive-cache/` 仍可讀。
5. 不再使用時，可在 Google Cloud 刪除 OAuth 用戶端或整個專案；Drive 裡的「智慧學習歷程系統上傳檔」資料夾可以自己刪除。

## 限制（測試版）

- 權杖只在記憶體：網站重開後要管理員重新連線，連線前新上傳的檔案存本機、雲端檔案靠本機快取。
- 本機快取不會自動清除；多程序或多台伺服器部署時要改成共用的工作階段儲存並重新評估權杖保存方式。
- 依學校政策到期才永久清除（V2 第 7 頁）還沒做；目前只有標記。
- 還沒做：學生學校帳號備份、把本機舊檔搬到 Drive、Google 選檔視窗匯入多個檔案。

# 自傳在 Google 文件中編輯：Google Cloud 設定步驟（示範版）

日期：2026-10-20（台灣時間）

適用：本機展示站 `http://localhost:5013`，用**學生個人 Google 帳號**示範（沒有學校 Workspace 管理權限）。

## 這個功能做什麼

1. 自傳頁按「在 Google 文件中編輯」：第一次會先到 Google 登入並同意權限，之後系統在**你自己的 My Drive** 建立一份 Google 文件，內容是目前的自傳草稿，每段標題後方有來源標記（例如 `## 學習歷程與具體經驗 [來源 F1 F2]`）。之後再按，開的都是同一份。
2. 在 Google 文件改完，回系統按「從 Google 文件取回」：系統匯出純文字，存成**新的一版**（舊版不動），並重新檢查來源標記；不存在的來源編號會在該段標示「引用了不存在的來源」。
3. 送導師確認一樣用系統內的版本快照，Google 文件只是編輯工具。
4. 權限只要 `drive.file`：系統只能碰它自己建立的那份文件，看不到你 Drive 裡其他檔案。權杖只放在伺服器記憶體，瀏覽器只拿到隨機編號；伺服器重啟或約 1 小時後過期，就要重新連結 Google。
5. Google 任何一步失敗（沒設定、沒同意、過期、連不上），都回到自傳頁顯示提示，仍可在系統內直接編輯與儲存。

## 使用者要準備的 Google Cloud 設定

以下步驟在 <https://console.cloud.google.com/> 操作，用你要示範的個人 Google 帳號登入。

1. **建立專案**：上方專案選單 →「新增專案」→ 名稱例如 `smart-learning-portfolio-demo` → 建立，並切換到這個專案。
2. **啟用 Google Drive API**：左側「API 和服務」→「程式庫」→ 搜尋 `Google Drive API` →「啟用」。（不需要啟用 Google Docs API；建立與匯出都走 Drive API。）
3. **設定 OAuth 同意畫面**（新版介面叫「Google Auth Platform」）：
   - 使用者類型選「**外部**」（個人帳號沒有「內部」可選）。
   - 填應用程式名稱（例如「資管科學習歷程系統（示範）」）、使用者支援電子郵件、開發人員聯絡電子郵件。
   - 範圍（資料存取）加入 `https://www.googleapis.com/auth/drive.file`，**只加這一個**。
   - 發布狀態保持「**測試**」，在「測試使用者」加入要示範登入的 Google 帳號（測試模式最多 100 個；沒加入的帳號會被擋下）。
   - 測試模式下 Google 會顯示「Google 尚未驗證這個應用程式」，示範時按「繼續」即可；不需要送審。
4. **建立 OAuth 用戶端**：「API 和服務」→「憑證」（或 Google Auth Platform →「用戶端」）→「建立憑證」→「OAuth 用戶端 ID」：
   - 應用程式類型：「**網頁應用程式**」。
   - 已授權的重新導向 URI：`http://localhost:5013/student/google/callback`（埠號要和展示站一致；若用 `127.0.0.1` 開站，這裡也要另外加 `http://127.0.0.1:5013/student/google/callback`，並讓 `.env` 的值和你實際開的網址一致）。
   - 若同時使用公開展示頁的 Drive Picker 原型，同一個用戶端的「已授權的 JavaScript 來源」可加 `http://localhost:5013`。
   - 建立後會看到「用戶端 ID」與「用戶端密鑰」。
5. **填到自己的 `.env`**（`.env` 不提交 Git，也不要貼到對話或文件裡）：

   ```
   GOOGLE_OAUTH_CLIENT_ID=（用戶端 ID）
   GOOGLE_OAUTH_CLIENT_SECRET=（用戶端密鑰）
   GOOGLE_OAUTH_REDIRECT_URI=http://localhost:5013/student/google/callback
   ```

   三個值都有填，自傳頁的按鈕才會出現；少一個就顯示「Google 尚未設定」，其他功能照常。
6. **重新啟動展示站**，用學生帳號登入 → 自傳 → 「在 Google 文件中編輯」。

## 示範結束後

- 可到 <https://myaccount.google.com/permissions> 移除本系統的存取權。
- 建立的 Google 文件在你自己的 My Drive，可直接刪除；系統資料庫只記文件 ID、連結、建立時間與對應的自傳版本。
- 不再使用時，可在 Google Cloud 刪除該 OAuth 用戶端或整個專案。

## 限制（示範版）

- 權杖不長期保存，所以沒有背景同步；Google 文件裡的修改要手動按「取回」。
- 建立 Google 文件之後在系統內做的修改，不會自動寫回同一份 Google 文件。
- 取回時依「## 標題」拆段；標題行被刪掉時會拒絕取回，系統內版本不變。
- 伺服器記憶體裡的權杖只適用單一程序的本機展示；正式多人部署需改成伺服器端工作階段儲存（例如資料庫或 Redis），並重新評估權杖保存方式。

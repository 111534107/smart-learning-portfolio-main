# 會議室 Discord 雙層導覽與全域搜尋實作計畫

> **給代理執行者：** 逐項執行本計畫；每項完成後先驗證、再本機提交，不推送。不可呼叫 AI 發言。

**目標：** 將 `ai-meeting-room` 改成 Discord 式雙層資料夾／會議導覽，加入拖曳分類與合併、資料夾名稱／圖示／顏色編輯，以及最外層全域搜尋。

**架構：** 保留現有 Python 內建 `http.server` 與單頁 `static/index.html`。後端負責資料夾狀態、歷史追加、時間排序與搜尋；前端負責雙層導覽、拖曳事件、面板編輯、篩選器與結果定位。資料夾合併以 `merged_into` 保留來源，不刪除任何資料。

**技術：** Python 3、內建 JSON／JSONL／`threading.Lock`、原生 HTML／CSS／JavaScript、既有 `pytest` 測試。

**規格：** `ai/docs/09_AI會議室/02_設計規格/AI_設計規格_會議室Discord雙層導覽與全域搜尋_2026-10-10.md`

## 全域硬性規則

- 不做會議、資料夾、發言或歷史紀錄刪除功能。
- 不修改既有發言文字或發言時間。
- 會議清單依 `meta.json.created` 新到舊；新增發言不改變清單排序。
- 搜尋結果依 `messages.jsonl` 的 `time` 新到舊；會議資訊結果才使用會議啟動時間。
- 所有分類、合併、改名、改色與編輯都驗證學號並記錄學號、姓名與操作時間。
- 不回傳或顯示本機絕對路徑；新增檔案與顯示路徑使用相對路徑。
- 只修改 `ai-meeting-room` 與 `ai/docs` 文件；不修改 `ai` 專案程式碼，不推送。
- 測試使用隔離資料目錄與 `8766`；不在真實會議留下測試資料，不按任何 AI 發言按鈕。

## 檔案責任分工

- `ai-meeting-room/server.py`：資料夾資料模型、鎖定寫入、合併、排序、搜尋接口與錯誤回應。
- `ai-meeting-room/static/index.html`：Discord 雙層導覽、拖曳、資料夾編輯面板、最外層搜尋面板與結果跳轉。
- `ai-meeting-room/meetings/folders.json`：可版本控制的資料夾共同資料。
- `ai-meeting-room/tests/test_room_features.py`：資料夾、合併、時間排序、搜尋與權限測試。
- `ai-meeting-room/tests/test_layout_and_preview.py`：前端元素、拖曳入口、搜尋入口與時間顯示的靜態回歸測試。
- `ai-meeting-room/tests/test_server_document_preview.py`：維持相對路徑顯示回歸測試。
- `ai-meeting-room/README.md`、`ai-meeting-room/docs/操作手冊.md`：更新使用方式、拖曳與搜尋說明。
- `ai/docs/03_開發紀錄/development-log.md`：每項完成後在最上方追加繁體中文日誌。
- `ai/docs/AI_代理協作_工作佇列.md`：完成後追加回報，不覆寫既有回報。

### Task 1：建立隔離資料與時間排序基礎

**檔案：**

- 修改：`ai-meeting-room/server.py`
- 修改：`ai-meeting-room/tests/test_room_features.py`
- 修改：`ai-meeting-room/meetings/folders.json`

**接口：** `load_folders()`、`save_folders(folders)`、`meeting_sort_key(meta)`；會議列表接口回傳依 `created` 由新到舊的資料。

- [ ] 寫失敗測試：建立兩場不同 `created` 的測試會議，追加較晚發言，確認列表仍依 `created` 排序。
- [ ] 執行 `python -m pytest tests/test_room_features.py -q -p no:cacheprovider --basetemp=.test-tmp-task1`，確認測試因排序接口不存在或順序錯誤而失敗。
- [ ] 實作 `save_folders`，以既有全域鎖保護 `folders.json`，空檔案回傳空陣列；列表排序只使用 `meta.created`。
- [ ] 重跑該測試並確認通過；檢查 `messages.jsonl` 的 `time` 沒有被改寫。
- [ ] 開隔離伺服器 `MEETING_ROOM_PORT=8766`，瀏覽器確認新建立時間較新的會議在上方，即使舊會議有新發言也不移動。
- [ ] 更新開發日誌，提交：`git add ... && git commit -m "會議清單依啟動時間排序"`。

### Task 2：資料夾名稱、圖示、顏色與歷史紀錄

**檔案：**

- 修改：`server.py`
- 修改：`tests/test_room_features.py`
- 修改：`static/index.html`

**接口：** `create_folder(name, member_id, icon, color)`、`update_folder(folder_id, changes, member_id, version)`、`folder_history()`。

- [ ] 寫失敗測試：新增資料夾後改名、圖示、顏色，確認欄位保存且歷史含 `time`、`member`、`member_name`、修改前後。
- [ ] 執行該測試確認失敗。
- [ ] 實作資料夾 `color` 與 `merged_into` 欄位的預設值；更新接口只允許名稱、圖示、顏色，拒絕未知學號。
- [ ] 前端新增資料夾編輯面板，使用表單與顏色選擇器，不再用 `prompt`；保留取消與版本衝突時的輸入。
- [ ] 重跑測試與 JavaScript 語法檢查：`node -e "...new Function(...)"`。
- [ ] 瀏覽器點擊新增資料夾、開啟編輯面板、改名、換圖示、換顏色、重新整理確認保存。
- [ ] 寫日誌並提交：`git commit -m "新增資料夾名稱圖示與顏色編輯"`。

### Task 3：Discord 雙層導覽與會議拖曳分類

**檔案：**

- 修改：`static/index.html`
- 修改：`server.py`
- 修改：`tests/test_room_features.py`
- 修改：`tests/test_layout_and_preview.py`

**接口：** `move_meeting(meeting_id, folder_id, member_id)`；前端 `renderFolderRail()`、`renderMeetingList()`、`onMeetingDrop()`。

- [ ] 寫失敗測試：會議搬移後 `meta.folder` 改變、分類歷史追加，清單仍依啟動時間排序。
- [ ] 執行測試確認失敗。
- [ ] 實作左側第一層資料夾圖示列與第二層會議清單；「全部」只作篩選入口，不是可放置目標。
- [ ] 為會議列加入 `draggable=true`、`dragstart`、`dragend`、資料夾 `dragover`／`drop`；放置前顯示目標資料夾提示。
- [ ] 完成搬移後重新載入目前資料夾，不改會議啟動時間與發言資料。
- [ ] 瀏覽器拖曳一場會議到資料夾、切換資料夾、重新整理確認仍在正確資料夾；確認畫面沒有刪除按鈕。
- [ ] 寫日誌並提交：`git commit -m "建立Discord雙層會議導覽與拖曳分類"`。

### Task 4：資料夾拖曳合併與來源導向

**檔案：**

- 修改：`server.py`
- 修改：`static/index.html`
- 修改：`tests/test_room_features.py`
- 修改：`tests/test_layout_and_preview.py`

**接口：** `merge_folders(source_id, target_id, member_id)`；回傳來源資料夾的 `merged_into` 與移入目標的會議數量。

- [ ] 寫失敗測試：兩資料夾合併後來源仍存在、`merged_into` 指向目標、來源會議全部改指目標、歷史有合併操作；相同來源／目標被拒絕。
- [ ] 執行測試確認失敗。
- [ ] 實作合併接口，使用鎖一次完成資料夾與會議資料更新；不得刪除來源資料夾。
- [ ] 前端資料夾圖示支援拖曳到另一圖示，放置後顯示確認面板；合併成功後自動開啟目標資料夾編輯面板。
- [ ] 已合併來源顯示「已合併至○○」，點擊導向目標；避免同一場會議重複顯示。
- [ ] 瀏覽器建立兩個資料夾與測試會議，拖曳合併，確認名稱、圖示、顏色可修改且重新整理仍保留。
- [ ] 寫日誌並提交：`git commit -m "新增資料夾拖曳合併與導向"`。

### Task 5：最外層全域搜尋與可點選篩選

**檔案：**

- 修改：`server.py`
- 修改：`static/index.html`
- 修改：`tests/test_room_features.py`
- 修改：`tests/test_layout_and_preview.py`

**接口：** `search_meetings(query, filters=None, limit=200)`；結果包含 `meeting_id`、`message_id` 或 `result_type`、會議名稱、資料夾、發言者、業務時間與片段。

- [ ] 寫失敗測試：兩場會議有不同啟動時間與訊息時間，確認全域搜尋不受目前資料夾限制，訊息依 `message.time` 排序，結果不含絕對路徑；篩選發言者、資料夾、附件與日期。
- [ ] 執行測試確認失敗。
- [ ] 實作後端結構化篩選，支援畫面篩選條件與既有文字語法；會議資訊、發言、附件檔名分開標記。
- [ ] 前端把搜尋入口移到應用程式最外層標題列；搜尋面板提供發言者、資料夾、會議、附件、日期篩選，不要求手打語法。
- [ ] 點結果切換會議、定位 `m-<message_id>` 並短暫標亮；無結果顯示清楚訊息。
- [ ] 瀏覽器在「全部」與任一資料夾各試一次搜尋，選擇篩選器，點結果跳到正確發言，確認搜尋結果包含跨資料夾內容。
- [ ] 寫日誌並提交：`git commit -m "新增Discord式全域搜尋與篩選"`。

### Task 6：相對路徑、文件、導覽與回歸驗收

**檔案：**

- 修改：`server.py`
- 修改：`static/index.html`
- 修改：`README.md`
- 修改：`docs/操作手冊.md`
- 修改：`tests/test_server_document_preview.py`
- 修改：`ai/docs/03_開發紀錄/development-log.md`
- 修改：`ai/docs/AI_代理協作_工作佇列.md`

- [ ] 寫測試確認搜尋結果、資料夾資訊與檔案面板不露出 `D:\`、`C:\Users\` 或其他絕對路徑。
- [ ] 執行修改範圍測試並確認失敗。
- [ ] 修正操作手冊、README、網頁導覽文字；導覽步驟要能找到新的資料夾列、搜尋入口、編輯面板與合併提示。
- [ ] 使用隔離資料目錄的另一份複製資料啟動 `8766`，瀏覽器完成寬版與窄版驗收並保存截圖到暫存區；不使用真實會議新增測試資料。
- [ ] 執行相關完整驗證：`python -m pytest tests/test_room_features.py tests/test_layout_and_preview.py tests/test_server_document_preview.py -q -p no:cacheprovider --basetemp=.test-tmp-final`、`python -m py_compile server.py agents.py`、內嵌 JavaScript 語法檢查。
- [ ] 確認沒有 AI 正在發言，再依 README 查 PID，停止舊版 `8765` 並啟動新版；若 PID 無法確認或有活動發言，停止並記錄，不強制結束。
- [ ] 在工作佇列追加角色、日期、修改檔案、驗證結果、截圖位置、未完成項目與下一步；將 ROOM-01 狀態改為「待使用者確認」或「完成」。
- [ ] 寫最終日誌並提交：`git commit -m "完成會議室Discord導覽與搜尋文件"`。

## 完成檢查表

- [ ] 每項任務都有先失敗後通過的自動測試。
- [ ] 每項任務都有瀏覽器實際操作與截圖，或明確記錄環境阻塞。
- [ ] 會議啟動時間與對話紀錄時間沒有混用。
- [ ] 沒有刪除功能、沒有改發言內容、沒有 AI 發言。
- [ ] 沒有本機絕對路徑暴露。
- [ ] `ai-meeting-room` 本機提交清單與 `ai/docs` 文件提交清單已記錄。
- [ ] 沒有推送。

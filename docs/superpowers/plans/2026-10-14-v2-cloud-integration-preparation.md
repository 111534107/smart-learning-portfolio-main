# V2 雲端附件整合：標準開發準備與首切片計畫

## 目標

把 V2 報告增補的 Google 雲端附件流程整理成可審查、可追溯、可逐階段驗收的需求與實作計畫。先完成不需外部帳號的本機假服務垂直切片；Google OAuth／Drive、MySQL 8.0.39、Docs 等真實服務需各自滿足決策與環境前置條件後再驗收。

## 架構與約束

- 正式規格仍以 `D:\democase\ai\docs\01_正式規格\` 為準。V2 是使用者選定的開發目標，但仍待老師／組員審查。
- `ai-wt-story` 是唯一工作樹。保留所有既有修改與未追蹤資料；不合併、不推送、不清理，不修改 `ai-personal`、`ai-team`、`ai-meeting-room`。
- 現行帳號／權限、`SourceDocument`、`PortfolioEvidence`、OCR 確認、`evidence_id`、Evidence Package 和教師審閱快照優先重用。未有決議前不重複建模、不改資料表、不執行遷移。
- 首個可開發切片使用合成附件與測試替身，不讀取真實檔案、不連外、不使用個資。假服務結果不可宣稱是真實 Drive／OCR 驗收。
- 每次改檔後更新 `docs/03_開發紀錄/development-log.md` 頂端區段、`docs/05_交接與專案管理/handoff.md` 與任務清單。依專案規則不用子代理。

## 技術棧與追溯文件

- Flask 3、SQLAlchemy、Alembic、Jinja2、純 HTML/CSS/少量 JavaScript；測試用 `pytest` 與 SQLite 記憶體資料庫。真實 DB 目標是隔離 MySQL 8.0.39。
- 需求提案追溯：[`AI_V2需求追蹤與現況對照_2026-10-14.md`](../../02_需求與設計/AI_V2需求追蹤與現況對照_2026-10-14.md)
- 整合診斷／決策：[`AI_V2增補篇整合診斷與開發前規格_2026-10-14.md`](../../02_需求與設計/AI_V2增補篇整合診斷與開發前規格_2026-10-14.md)
- 相關程式：`app/models/learning_profile.py`、`app/models/portfolio.py`、`app/routes/student.py`、`app/services/document_analysis_service.py`、`app/services/autobiography_service.py`、`app/services/package_service.py`、`app/services/review_snapshot_service.py`、`app/routes/proposal_preview.py`、`app/services/google_drive_preview.py`、`app/static/js/proposal-preview-drive.js`。
- 相關測試：`tests/test_learning_profile_upload.py`、`tests/test_learning_profile_confirmation.py`、`tests/test_learning_profile_e2e.py`、`tests/test_learning_profile_models.py`、`tests/test_google_drive_preview.py`、`tests/test_proposal_preview.py`、`tests/test_document_analysis_demo.py`、`tests/test_review_workflow.py`、`tests/test_package_docx.py`。

## 前置決策閘門

下列決策未完成前，不新增正式 Drive schema、不改登入方式、不接真實服務：

- D-01：選取既有 Drive 檔案或系統上傳；本機首切片可用假附件契約繼續。
- D-02：Google OIDC 是否取代／補充現行登入及帳號連結規則。
- D-03：My Drive／Shared Drive、檔案擁有權與離校後管理者。
- D-04：OAuth scopes、token 生命週期、撤銷及秘密保管。
- D-05：檔案主體、資料庫引用和刪除／封存／復原責任。
- D-06：維持單校或跨校；教師／科辦資料可見範圍。
- D-07：送審與審閱狀態轉換如何對應現況。
- D-08：功能 ID、V1 優先級及正式期中分母。
- D-09：非功能數值、個資保存期限及事件處理方式。
- D-10：Google 授權帳號與應用程式帳號如何連結、解除，及附件如何歸屬到學生。

## 執行步驟

### A. 需求與文件整併（決策閘門）

1. 對 V2 正文與增補篇逐項抽出需求 ID、原文位置、正式規格來源、優先級、現況證據、驗收方式及決策人。
2. 建立 F-35–F-40 缺號對照表；不重用缺號，釐清 F-10–F-15、F-22–F-24 的內容及優先級。
3. 將 V2 對 Drive、Docs、Sheets、Calendar、Gmail、OIDC 的架構提及與 MUST／SHOULD／V2 狀態分開，記錄提案衝突。
4. 由老師／組員裁定正式納入的需求、分母和資料政策；每項保留來源、核准日期與決議者。沒有回覆時繼續假資料契約設計，但不得升格正式規格。

**完成條件**：正式要求與提案有明確標記；所有衝突有追溯項目及決策狀態；不再用架構圖提及推論為已承諾功能。

### B. As-Is／To-Be 領域與資料設計

1. 逐一對照 V2 提案實體與現行 ORM，覆核現有 Student、Teacher、PortfolioFile、Evidence、Submission 等重疊概念。
2. 對照 `SourceDocument`、`DocumentExtraction`、`PortfolioEvidence`、現有送審快照，畫出附件、學習證據和學生／教師的擁有及引用關係。
3. 寫出檔案來源與狀態表：本機上傳、假附件、Drive 選檔分開；包含正常、未授權、外部檔案刪除、重複引用、過期授權和同步失敗情境。
4. 將 V2 狀態機與現行 `PortfolioSubmission` 狀態逐一映射；先定合法轉換，不直接改狀態值。
5. 更新 As-Is／To-Be ERD 與資料字典草稿，清楚標示現有欄位、提案新增欄位和未核准欄位。

**完成條件**：資料來源、權限、生命週期及舊資料相容性可審查；未核准的新表／欄位不進入遷移。

### C. 本機假服務契約與測試（可先執行）

1. 不先假定新模組名稱或 API；先依現行服務分層界定最小契約與結果型別，並記錄在設計文件。
2. 以測試替身提供附件來源 ID、顯示名稱、MIME 類型、來源狀態及已登入者歸屬；使用合成值。現行公開 `/proposal-preview/drive-file` 不具備應用程式帳號，因此不得直接重用為此契約的正式入口。
3. 先寫並執行紅燈測試：不同使用者不可讀取／引用彼此附件、未知或失效附件拒絕、重複引用有明確行為、錯誤資訊不洩漏秘密。
4. 測試附件可經學生編輯確認後連到既有 `evidence_id`，自傳引用及教師快照保留同一來源 ID。
5. 驗證本機展示標示「模擬」，不呼叫外部網路、不讀取附件內容、不讀取真實個資。

**完成條件**：新增測試先失敗再因實作通過；現有回歸測試通過；新增契約未造成 schema 變更。

### D. 一個 Drive 附件用例（決策後實作）

1. 僅在 D-01、D-03、D-04、D-05、D-06 決議後，指定唯一用例（選檔或上傳）。
2. 先定最小 OAuth scopes、登入者與校務使用者映射、檔案所有權、token 是否只存在當次流程及撤權處理。
3. 使用明確隔離的 Google 測試帳號和合成文件；不得使用學生真實檔案。
4. 針對未授權、外部刪檔、檔案類型錯誤、配額限制、網路逾時及撤權建立服務測試和操作說明。
5. 真實呼叫與假服務分開設定、分開記錄驗收證據；測試日誌不可輸出 token 或檔案個資。

**完成條件**：真實帳號驗收有記錄；只讀／上傳權限符合核准範圍；撤權後行為可預期；回歸測試通過。

### E. OCR、學生確認與證據包接線

1. 確認檔案來源不會繞過現有 `DocumentExtraction`、學生修正與確認規則。
2. OCR 失敗時保留來源狀態與可重試方式，不建立錯誤的已確認學習證據。
3. 人工確認後才建立／更新 `evidence_id`；草稿、未確認內容不得輸入送審證據包。
4. 確認自傳草稿、教師快照和 Word 輸出可沿來源 ID 回查；外部檔案失效時畫面不得冒稱附件仍可用。

### F. 分層驗收與報告回填

1. 自動測試：權限、跨使用者隔離、重複／失效檔案、OCR 修正、學生確認、證據引用、教師快照。
2. 靜態檢查：程式編譯、`git diff --check`、秘密掃描與資料遷移檢查。
3. SQLite 自動測試後，另於隔離 MySQL 8.0.39 驗證遷移、登入、CRUD、外鍵；不可把 SQLite 記錄為 MySQL 通過。
4. 瀏覽器：桌機、390px 手機、鍵盤、減少動態效果、角色及失效附件操作。瀏覽器結果與測試用戶端結果分開記錄。
5. Google 真實服務：OAuth、Picker／上傳、檔案權限、撤權及配額的實際帳號測試獨立回報。
6. 老師／組員核准後才更新正式成果報告正文、正式需求追溯、ERD、資料字典、操作手冊及驗收清單。

**完成條件**：每個 V2 條目可追到決議、程式／文件、測試和實際驗收狀態；未完成明列原因，不把「有程式」報成「已驗收」。

## 依賴與不納入首切片

- **外部前置條件**：老師／組員對 V2 優先級與資料政策的決議；Google Workspace 測試帳號、OAuth 設定與安全審查；隔離 MySQL 8.0.39 可安全連線的測試環境。
- **不納入本機首切片**：OIDC 登入、跨校租戶、Shared Drive、Docs 共編、Sheets、Calendar、Gmail、商用維運，以及未核定的錄取機率／招生規則。
- 本計畫是前期與首個切片的工作計畫，不承諾八小時內完成 V2 全系統，不預設學校期中百分比分母。

## 本輪準備成果

- V2 增補篇的整合診斷：[`AI_V2增補篇整合診斷與開發前規格_2026-10-14.md`](../../02_需求與設計/AI_V2增補篇整合診斷與開發前規格_2026-10-14.md)
- 現行追蹤矩陣：[`AI_V2需求追蹤與現況對照_2026-10-14.md`](../../02_需求與設計/AI_V2需求追蹤與現況對照_2026-10-14.md)
- 本計畫本輪只補文件，不修改功能程式；公開提案頁的 Drive 中繼資料端點沒有登入者／學生資料歸屬，不能直接當正式學生附件入口。真實 Drive、MySQL、OAuth 及 UI 驗收仍待各自環境和決議。

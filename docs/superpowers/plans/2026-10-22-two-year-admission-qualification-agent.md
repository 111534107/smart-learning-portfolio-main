# 二技入學資格查詢 Agent 實作計畫

> **給 AI 開發代理的指示：** 必須使用 `superpowers:subagent-driven-development`（建議）或 `superpowers:executing-plans` 子技能，逐項執行本計畫。步驟使用核取方塊（`- [ ]`）追蹤進度。

**目標：** 讓學生能詢問自己可能符合哪些已公告的二技校系申請資格，並取得明確的規則判斷結果及可追溯的官方來源。

**架構：** 沿用 `AdmissionProgram`、學生已確認的學習紀錄、小助手的工具呼叫流程，以及既有的候選資料至正式發布審核流程。新增每個校系可使用的結構化資格規則與確定性的比對服務；語言模型只負責說明服務結果。第一階段支援二技技優甄審及資管相關校系。

**技術：** Python、Flask、SQLAlchemy、Alembic、既有 Gemini 函式呼叫小助手、pytest 專案慣例。

**設計規格：** `docs/superpowers/specs/2026-10-22-two-year-admission-qualification-agent-design.md`

## 全域限制

- 招生資格以當年度官方招生簡章為準；歷年資料僅供參考。
- AI 擷取出的資格規則一律先標示待確認，管理者核對官方來源後才能確認。
- 只有已確認的學生資料及已發布的校系規則，才能產生確定的比對結果。
- 資格狀態由比對服務決定，不由語言模型自行判斷。
- 不把結果說成正式審查結論或錄取機率。
- 沿用既有校系、證照、經歷及學生資料，不建立重複資料。
- 未備份資料庫且未取得使用者明確同意前，不對使用者的 MySQL 資料庫執行遷移。

## 審查時特別留意

- 多個替代資格不可誤判成全部都必須符合；明確維持「同一組條件全部符合、不同組符合任一組」的邏輯。
- 待確認規則不可產生「符合目前已知條件」的確定結果。
- OCR 尚未確認的資料、缺少學籍資料及目前不支援的比對欄位，必須回報「資料不足／需人工確認」。
- 即使小助手工具呼叫帶入學生識別資料，也不可比對或回傳其他學生的資料。
- 官方來源資訊缺漏時，必須清楚呈現缺漏，不可當成已查證的依據。

---

### 任務 1：新增結構化資格規則模型與資料庫遷移

**檔案：**
- 修改：`app/models/admission.py`
- 修改：`app/models/__init__.py`
- 新增：`migrations/versions/` 下的下一個 Alembic 遷移檔
- 修改：`tests/test_migration_setup.py`

**介面：**
- 新增 `AdmissionEligibilityRule`，透過 `rule_version_id` 關聯一筆 `AdmissionProgram`。
- 欄位：`rule_group`（整數）、`condition_type`（字串）、`operator`（字串）、`value_json`（JSON）、`description`（文字）、`source_url`（字串）、`source_location`（字串）、`mapping_status`（`pending`／`confirmed`）、`is_required`（布林值）、`sort_order`（整數）。
- 群組邏輯：同一組中的必要條件必須全部符合（AND）；不同組之間符合任一組即可（OR）。非必要條件僅供參考，不會阻擋符合結果。

- [x] 新增 SQLAlchemy 模型及 `AdmissionProgram.eligibility_rules` 關聯，並從 `app.models` 匯出模型。
- [x] 新增可升級及降級的資料庫遷移，建立 `admission_eligibility_rules`、校系版本外鍵，以及依 `rule_version_id` 和 `mapping_status` 查詢的索引。
- [x] 確認既有 SQLite 遷移流程可以建立和移除新資料表，且不會移除較早建立的招生資料表。

### 任務 2：實作確定性的資格比對

**檔案：**
- 新增：`app/services/admission_eligibility_service.py`
- 必要時修改：`app/services/journey_service.py`，僅用於重用年級推導介面
- 新增：`tests/test_admission_eligibility_service.py`

**介面：**
- `evaluate_program(student, program) -> dict` 回傳 `program_code`、`admission_year`、`status`、`matched_groups`、`conditions` 和 `sources`。
- 第一版支援的條件類型：`student_status`、`credential`、`competition`。
- 支援的運算子及 `value_json` 格式，必須先以模組層級驗證器明確定義：`student_status` 接受允許的身分清單；`credential` 可接受標準化名稱、最低級別、發證單位和取得日期範圍；`competition` 可接受類別、獎項／名次門檻及日期範圍。
- 未知條件類型／運算子、格式錯誤、待確認規則或缺少學生欄位，皆回傳 `needs_review`／`insufficient_data`，不可當作符合。
- 證照比對只讀取 `confirmation_status == "confirmed"` 的 `CredentialRecord`；競賽比對只讀取目前登入學生且 `status == "confirmed"` 的 `Portfolio`。
- 證照級別正規化使用明確且有順序的對照表；未知證照名稱或級別一律標示未能判斷，不可猜測。

- [x] 定義並驗證支援的 `value_json` 格式及比較運算子。
- [x] 實作同組條件 AND、不同組條件 OR 的判斷，回傳逐條條件說明，而非只有布林值。
- [x] 依設計規格的優先順序回傳 `eligible`、`not_eligible`、`insufficient_data` 或 `needs_review`，並附上適用條件及來源網址、位置。
- [x] 遇到未知證照級別、競賽名次／類別或不支援的資料欄位時，保留未判定狀態，不從自由文字推測是否符合。

### 任務 3：從官方來源擷取候選資格規則

**檔案：**
- 修改：`app/services/admission_agent_service.py`
- 修改：`tests/test_admission_agent.py`

**介面：**
- 擴充擷取結構，加入 `eligibility_rules` 陣列。每筆候選資料包含 `rule_group`、`condition_type`、`operator`、`value_json`、`description` 和 `source_location`。
- `extract_programs(...)` 將擷取結果存成 `mapping_status="pending"`，並連結到正確的校系版本及來源網址。
- 保持現有備審評分項目擷取行為不變。

- [ ] 更新擷取提示及資料格式，只擷取來源中明確寫出的資格條件，並記錄頁碼或章節位置。
- [ ] 將格式正確的候選規則存為待確認；格式錯誤者不得用於比對，並保留原文供管理者檢視。
- [ ] 遇到缺頁、文字模糊或資格內容不明確時，不猜測結構化條件，改建立待人工確認的候選說明。

### 任務 4：新增管理者資格規則核對流程

**檔案：**
- 修改：`app/routes/admin.py`
- 修改：`app/templates/admin_programs.html`（或目前路由使用的招生核對頁面範本）
- 修改：`tests/test_admission_services.py`

**介面：**
- 管理者操作範圍限於既有候選 `AdmissionProgram` 及其 `AdmissionEligibilityRule`。
- 每條規則可以修改並設為 `confirmed`，也可以保留待確認；發布仍沿用既有校系版本狀態流程。
- 核對頁同時顯示原文、標準化條件、來源連結、來源位置及確認狀態。

- [ ] 新增只有管理者可使用的規則核對操作，儲存前依條件格式驗證修改內容。
- [ ] 在現有招生核對流程中顯示待確認規則及其官方來源資訊。
- [ ] 必要資格仍有待確認規則時，不可將校系顯示為資格已確認；未結構化的規則仍要標示「需人工確認」。

### 任務 5：將資格查詢加入學生小助手

**檔案：**
- 修改：`app/services/assistant_tools.py`
- 修改：`app/services/assistant_service.py`
- 修改：`tests/test_assistant.py`

**介面：**
- 新增學生工具 `find_eligible_admission_programs(user, admission_year=None) -> dict`；使用登入的 `user` 判定學生身分，不接受模型傳入的身分參數。
- 工具只查詢指定年度（或系統明確選定的最新可用年度）已發布的校系；每筆回傳 `evaluate_program` 結果、校系名稱及官方來源。
- 工具只註冊於 `STUDENT_TOOLS`；第一版不提供導師查詢。
- 小助手系統指示須說明資格結果標籤，並區別系統比對結果與招生單位正式審查。

- [ ] 實作並註冊僅限學生使用的資格查詢工具；查詢範圍限於目前登入學生已確認的資料。
- [ ] 更新小助手指示：學生詢問二技／技優個人資格時使用此工具，逐項解釋結果，不得自行新增招生條件。
- [ ] 盡可能沿用小助手現有 `sources` 回傳格式提供來源連結與頁碼／章節位置；工具結果也需保留完整來源資訊，供最後回答使用。

### 任務 6：完成遷移、權限及整體流程檢查

**檔案：**
- 修改：`tests/test_migration_setup.py`
- 修改：`tests/test_admission_eligibility_service.py`
- 修改：`tests/test_assistant.py`
- 修改：`docs/02_需求與設計/01_目前有效/AI_資料字典_現行ORM草稿_2026-10-13.md`

- [ ] 確認符合資格的學生能看到對應的來源規則說明，不符合者能看到未通過的條件及原因。
- [ ] 確認替代條件群組、待確認規則、OCR 尚未確認的證照、尚未確認的競賽經歷、個人資料缺漏、不支援的競賽資料，以及年度篩選，都會回傳不誇大的正確狀態。
- [ ] 確認小助手工具只使用登入學生的身分，不可查詢其他學生的資料。
- [ ] 確認遷移可以在一次性 SQLite 資料庫升級及降級；本計畫不會對 MySQL 執行遷移。
- [ ] 更新現行 ORM 資料字典，記載資格規則資料表及其核對、來源欄位。

# 畢業門檻三方連動（缺口案件）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把即時計算的畢業門檻擴充成「判斷結果＋缺口案件」，讓學生、導師、科辦透過同一個案件編號處理同一筆缺口，並有站內通知。

**Architecture:** `graduation_check_service` 只負責「判斷」（無狀態）；新增 `graduation_case_service` 負責「同步」判斷結果到案件表（可重複執行、不重複開案）；`case_actions` 負責角色動作與權限；通知只指向案件與事件。既有導師、科辦、學生頁只加區塊，不重做。

**Tech Stack:** Flask、SQLAlchemy、Alembic、Jinja2、pytest（SQLite 記憶體資料庫）。

**Spec:** `docs/superpowers/specs/2026-11-05-graduation-gap-cases-design.md`（使用者已核准，含第 5.2 節）

## Global Constraints

- 工作目錄 `D:\democase\ai-wt-story`，分支 `feat/google-docs-autobiography`。工作樹有別人未提交的修改（`app/demo.py`、`login.html`、`theme-campus.css`、`scripts/*`、`tests/test_auth.py` 等）：**只 `git add` 本任務自己的檔案，不整批提交、不推送、不合併。**
- 測試指令：`D:\democase\ai\.venv\Scripts\python.exe -m pytest -q <檔案> --basetemp=logs/test-runs/<新名稱>`；每次用全新 basetemp 名稱。
- 系統或 AI 不得宣告學生「符合畢業資格」或「無法畢業」。所有相關畫面固定附註：「僅供提醒，正式畢業資格以學校學生畢業門檻審核委員會的審核結果為準。」
- 「已確認改善」畫面要寫明：只代表這一筆缺口的資料與改善結果經過核對，不代表學生符合全部畢業資格。
- 開啟或重新整理頁面**不得**建立案件、改變狀態、寫事件或發通知。
- 專一～專四上不自動開案件；開案條件見 spec 5.2。
- 已核對屆別只有 111、113（`CREDIT_RULES`）；其他屆別為 `rule_unverified`。
- 每學期學分上限：專四、專五 28 學分（修業科目表教務規定）。
- 證照補救方式只引用「資訊管理科學生畢業門檻實施要點，113.03.27 修訂，第五點」，並寫明適用 109 學年度（含）以後入學的日間部五年制學生；學分補救只顯示「請洽科辦確認補修方式」。
- 案件編號顯示格式 `G-` 加 6 位補零流水號（`G-000123`）。
- 介面、訊息、註解用繁體中文；沿用現有 `work-shell`、`work-panel`、`tag--ok/--warn/--danger` 樣式。
- 每完成一個任務，在 `docs/03_開發紀錄/development-log.md` 最上面補一小段（最新在上）。

## Review Focus

1. 成績紀錄的 `school_year` 有時存民國學年度（例如 111），有時存年級（1～5，見 `LearningCourseRecord.year_for_placement`）：資料是否足夠的判斷兩種都要認得，不能把有資料的學期判成缺資料。→ Task 1 測試 `test_ended_term_matches_grade_number_school_year`。
2. 學生沒有 `StudentProfile` 或 `admission_year` 是空值：不得報錯，各項目為 `rule_unverified`，不開案件。→ Task 1 測試 `test_missing_profile_is_rule_unverified`、Task 3 測試 `test_sync_without_profile_creates_nothing`。
3. 同一學生短時間內被同步兩次（例如連續確認兩份文件）：只能有一筆未結案的同項目案件；第二次同步不產生任何事件或通知。→ Task 3 測試 `test_sync_twice_is_idempotent`。
4. 一個班有兩位導師：兩位都收到通知，同一人對同一事件不會收到兩則。→ Task 3 測試 `test_all_advisors_notified_once`。
5. 結案後同一問題再出現：開新案件、`previous_case_id` 指回舊案，舊案事件不變。→ Task 3 測試 `test_reopen_creates_linked_case`。

---

### Task 1: 判斷結果（階段、資料是否足夠、5.2 規則）

**Files:**
- Modify: `app/services/graduation_check_service.py`（保留既有 `classify_credential`、`certificate_status`、`credit_status`、`evaluate`，新增下列函式）
- Test: `tests/test_graduation_assessment.py`

**Interfaces:**
- Consumes: 既有 `CREDIT_RULES`、`REQUIRED_CATEGORIES`、`ELECTIVE_CATEGORIES`、`certificate_status(student)`、`load_curriculum()`、`normalize_course_name()`；`SystemSetting`；`TransferCreditRecord`；`SourceDocument`。
- Produces:
  - `MAX_CREDITS_PER_TERM_SENIOR = 28`、`TOTAL_TERMS = 10`、`TODAY_SETTING_KEY = "graduation_check_today"`
  - `ITEMS = ("certificates", "required_credits", "elective_credits", "total_credits")`
  - `RESULTS = ("met", "gap", "insufficient_data", "transfer_pending", "rule_unverified", "progress")`
  - `academic_term(today: date) -> tuple[int, str]`：回傳（民國學年度, "上"|"下"）。8/1 起為新學年上學期，2/1 起為下學期。
  - `check_today() -> date`：`SystemSetting` 有 `graduation_check_today`（ISO 日期字串）就用它，否則今天。
  - `student_stage(admission_year: int | None, today: date) -> dict`：`{"grade": int|None, "semester": "上"|"下", "formal": bool, "ended_terms": list[tuple[int, str]], "remaining_terms": int}`。`formal` 為專四下或之後；`ended_terms` 是入學後、目前學期之前的所有學期；`remaining_terms = TOTAL_TERMS - len(ended_terms)`（含目前學期），最小 0。
  - `assess(student, today: date | None = None, curriculum=None) -> dict`：`{"stage": <student_stage>, "items": {item: {"result": str, "amount": int|None, "unit": "張"|"學分", "detail": str, "basis": str, "failed_required": list[str], "missing_terms": list[tuple[int, str]]}}}`。

**判斷規則（spec 4.2、5.2；實作照此順序）**

- 證照：有 `SourceDocument(owner_id=學生, document_type="credential")` 且 `status != "confirmed"` → `insufficient_data`；否則採計張數 ≥ 3 → `met`；不足時 `formal` → `gap`（amount = 3 − 採計張數），非 `formal` → `progress`。
- 學分三項：屆別不在 `CREDIT_RULES` 或課綱沒有該屆 → `rule_unverified`；`ended_terms` 中任一學期沒有已確認課程紀錄 → `insufficient_data`（列出 `missing_terms`）；有 `TransferCreditRecord` 且 `status != "completed"` → `transfer_pending`；已修 ≥ 規定 → `met`；否則非 `formal` → `progress`；`formal` 時：
  - 必修：有必修類別課程已確認不及格（`acquisition_status == "not_passed"`），且沒有同正規化課名已確認及格的紀錄 → `gap`（`failed_required` 列課名）；或 還差學分 > `remaining_terms × 28` → `gap`；否則 `progress`。
  - 選修、總學分：還差學分 > `remaining_terms × 28` → `gap`；否則 `progress`。
  - `gap` 的 amount = 還差學分。
- 「該學期有資料」：存在已確認課程紀錄，`semester` 相同，且 `school_year` 等於該學期的民國學年度**或**等於該學期對應的年級（學年度 − 入學學年度 + 1）。
- `basis`：證照為 `"資訊管理科學生畢業門檻實施要點（113.03.27 修訂）第五點"`；學分為 `CREDIT_RULES[year]["source"]`。

- [ ] **Step 1: 寫失敗測試**（`tests/test_graduation_assessment.py`；建立學生的寫法沿用 `tests/test_graduation_check.py` 的 `make_student`、`add_course`、`add_credential`，另加 `add_course(..., school_year=, semester=)` 參數）

```python
def test_academic_term_boundaries():
    assert svc.academic_term(date(2026, 8, 1)) == (115, "上")
    assert svc.academic_term(date(2027, 1, 31)) == (115, "上")
    assert svc.academic_term(date(2027, 2, 1)) == (115, "下")

def test_stage_formal_from_grade4_second_term():
    assert svc.student_stage(111, date(2025, 3, 1))["formal"] is True    # 114 下＝專四下
    assert svc.student_stage(111, date(2024, 10, 1))["formal"] is False  # 114 上＝專四上
    stage = svc.student_stage(111, date(2025, 10, 1))                     # 115 上＝專五上
    assert stage["grade"] == 5 and stage["remaining_terms"] == 2

def test_grade1_short_of_220_is_progress_not_gap(app): ...           # 驗收情境 1：四項都不是 gap
def test_grade4_first_term_without_certificates_is_progress(app): ...  # 驗收情境 2：certificates == "progress"
def test_grade4_second_term_one_certificate_is_gap(app): ...           # 驗收情境 3：result "gap", amount 2
def test_no_transcript_is_insufficient_data(app): ...                  # 驗收情境 5：學分三項 "insufficient_data"
def test_transfer_pending_marks_credits(app): ...                      # 驗收情境 6：學分三項 "transfer_pending"
def test_failed_required_without_retake_is_gap(app): ...               # failed_required == ["國文"]
def test_failed_required_then_passed_is_not_gap(app): ...
def test_credit_gap_beyond_remaining_capacity_is_gap(app): ...         # 專五下 remaining 1，差 30 → gap
def test_credit_gap_within_capacity_is_progress(app): ...              # 專五上 remaining 2，差 50 → progress
def test_unconfirmed_credential_document_is_insufficient(app): ...
def test_ended_term_matches_grade_number_school_year(app): ...         # Review Focus 1
def test_missing_profile_is_rule_unverified(app): ...                  # Review Focus 2
def test_check_today_uses_setting_override(app): ...                   # SystemSetting 設 "2027-03-01"
```

每個 `...` 測試只呼叫 `svc.assess(student, today=<日期>)` 並斷言對應項目的 `result`（與註解中的 amount 或清單）。

- [ ] **Step 2: 執行測試確認失敗**
Run: `D:\democase\ai\.venv\Scripts\python.exe -m pytest -q tests/test_graduation_assessment.py --basetemp=logs/test-runs/gc-t1-a`
Expected: FAIL（`academic_term` 不存在）

- [ ] **Step 3: 依上方介面與規則實作。** `load_curriculum()` 只在 `assess` 呼叫一次並往下傳；既有 `evaluate` 保持可用（學生頁還在用）。

- [ ] **Step 4: 執行測試確認通過**，連同 `tests/test_graduation_check.py`、`tests/test_graduation_check_page.py`。Expected: 全部 PASS

- [ ] **Step 5: 提交**
```bash
git add app/services/graduation_check_service.py tests/test_graduation_assessment.py
git commit -m "feat: graduation assessment with stage rules and data sufficiency"
```

---

### Task 2: 資料表（案件、事件、通知）與遷移

**Files:**
- Create: `app/models/graduation_case.py`
- Modify: `app/models/__init__.py`（匯出三個模型）
- Create: `migrations/versions/b20261105b01_add_graduation_cases.py`（`down_revision = "b20261105a01"`；沿用該檔「表已存在就跳過」的寫法）
- Test: `tests/test_graduation_case_models.py`

**Interfaces:**
- Produces:
  - `GraduationCase`（`graduation_cases`）：`id`、`student_id`（FK users）、`case_type`（`"gap"|"data_needed"|"inquiry"`）、`item`（gap：`ITEMS` 之一；data_needed：`"certificates"|"credits"`；inquiry：`"general"`）、`status`（`"pending"|"in_progress"|"awaiting_verification"|"closed"`，預設 pending）、`close_reason`（`"improved"|"no_gap"|None`）、`initial_amount`、`current_amount`（int，可空）、`unit`（可空）、`basis`（String 255）、`detail`（Text）、`open_key`（String 80，unique，可空）、`previous_case_id`（FK 自己，可空）、`created_at`、`updated_at`、`closed_at`、`closed_by_id`。屬性 `number -> str`（`f"G-{id:06d}"`）、`is_open -> bool`。類別方法 `open_key_for(student_id: int, item: str, case_type: str) -> str` 回傳 `f"{student_id}:{item}:{case_type}"`。
  - `GraduationCaseEvent`（`graduation_case_events`）：`id`、`case_id`（FK）、`actor_id`（FK users，可空＝系統）、`event_type`（`"created"|"student_note"|"teacher_note"|"started"|"submitted"|"recalculated"|"auto_verify"|"verified"|"rejected"|"closed_no_gap"|"data_changed"`）、`from_status`、`to_status`、`amount_before`、`amount_after`、`note`（Text）、`created_at`。
  - `Notification`（`notifications`）：`id`、`recipient_id`（FK users）、`case_id`（FK）、`event_id`（FK）、`message`（String 255）、`created_at`、`read_at`（可空）；`UniqueConstraint("recipient_id", "event_id")`。

- [ ] **Step 1: 寫失敗測試**
```python
def test_case_number_format(app):           # 建一筆後 case.number == f"G-{case.id:06d}"
def test_open_key_unique_while_open(app):   # 同 open_key 第二筆 flush 時 IntegrityError
def test_closed_cases_allow_null_open_key(app):  # 兩筆 open_key=None 可同時存在
def test_notification_unique_per_recipient_event(app):  # 同 recipient+event 第二筆 IntegrityError
```
- [ ] **Step 2: 執行確認失敗**（`--basetemp=logs/test-runs/gc-t2-a`）
- [ ] **Step 3: 實作模型、匯出、遷移。**
- [ ] **Step 4: 執行確認通過**；另跑 `tests/test_migrations*.py`（若存在）確認遷移鏈只有一個 head。
- [ ] **Step 5: 提交**（只加上面四個檔案）

---

### Task 3: 同步服務（判斷結果 → 案件、事件、通知）

**Files:**
- Create: `app/services/graduation_case_service.py`
- Test: `tests/test_graduation_case_sync.py`

**Interfaces:**
- Consumes: Task 1 `assess`、`check_today`；Task 2 三個模型；`teacher_scope`（`ClassAdvisor` 查班導）；`audit_service`（狀態變更寫 `AuditLog`，用法照既有呼叫）。
- Produces:
  - `advisors_for(student) -> list[User]`：學生班級（`StudentProfile.class_name`）的所有導師。
  - `staff_users() -> list[User]`：所有啟用中的 `role == "staff"`。
  - `record_event(case, event_type: str, actor=None, *, to_status: str | None = None, amount_after: int | None = None, note: str = "", notify: list[User] = (), message: str = "") -> GraduationCaseEvent`：寫事件；`to_status` 有值時改狀態並寫 `AuditLog`（action `"graduation_case.status"`）；對 `notify` 每人建一則通知（同人去重）。
  - `sync_student(student, today: date | None = None) -> list[GraduationCaseEvent]`：spec 第七節「正式同步」第 1～6 點；回傳本次新增的事件。
  - `sync_all(today: date | None = None) -> int`：同步所有啟用中的學生，回傳新增事件數。

**同步對照（spec 第七、八節）**

| 判斷結果（formal 時） | 已有未結案同項目同類型案件？ | 動作 | 通知 |
| --- | --- | --- | --- |
| gap | 無 | 建 gap 案件（pending），事件 created | 學生、導師 |
| gap，amount 變小 | 有 | 事件 recalculated，更新 current_amount，狀態不變 | 無 |
| gap，amount 相同 | 有 | 什麼都不做 | 無 |
| met / progress | 有 gap 案件且未在待驗證 | 事件 auto_verify，→ awaiting_verification | 科辦 |
| insufficient_data / transfer_pending / rule_unverified | 有 gap 案件 | 事件 data_changed（同一判斷結果只寫一次），狀態不變 | 無 |
| insufficient_data | 無 data_needed 案件 | 建 data_needed 案件（item：證照為 certificates，學分三項合併為 credits） | 學生 |
| 資料已足夠 | 有 data_needed 案件 | 事件 auto_verify，→ awaiting_verification | 科辦 |

非 formal 的學生：不建任何 gap 或 data_needed 案件；已存在的未結案案件照上表處理（例如 met 仍會送待驗證）。
新案件時若存在同 `student_id`、`item`、`case_type` 的已結案案件，`previous_case_id` 指向最新那一筆。

- [ ] **Step 1: 寫失敗測試**（班級、導師用 `ClassAdvisor(teacher_id=..., class_name=..., school_year=115)`；日期一律用 `today=` 參數傳入）
```python
def test_grade4_second_term_gap_creates_case_and_notifies(app):   # 驗收 3：1 筆 pending、學生與導師各 1 則通知
def test_sync_twice_is_idempotent(app):                           # 驗收 4／Review 3：第二次回傳 []，案件與通知數不變
def test_partial_improvement_updates_same_case(app):              # 驗收 7：current_amount 8→4、狀態不變、無新通知
def test_gap_resolved_moves_to_awaiting_verification(app):        # 科辦收到通知
def test_no_transcript_creates_data_needed_not_gap(app):          # 驗收 5
def test_transfer_pending_creates_no_credit_gap(app):             # 驗收 6
def test_grade1_creates_nothing(app):                             # 驗收 1
def test_all_advisors_notified_once(app):                         # Review 4
def test_reopen_creates_linked_case(app):                         # Review 5：舊案 closed、新案 previous_case_id
def test_sync_without_profile_creates_nothing(app):               # Review 2
```
- [ ] **Step 2: 執行確認失敗**（`--basetemp=logs/test-runs/gc-t3-a`）
- [ ] **Step 3: 實作。** 建立案件時捕捉 `IntegrityError`（open_key 衝突）→ rollback 該筆並改走「已有案件」分支。
- [ ] **Step 4: 執行確認通過。**
- [ ] **Step 5: 提交**

---

### Task 4: 角色動作與權限

**Files:**
- Create: `app/services/graduation_case_actions.py`
- Test: `tests/test_graduation_case_actions.py`

**Interfaces:**
- Consumes: Task 3 `record_event`、`advisors_for`、`staff_users`；`teacher_scope.students_for_teacher`。
- Produces:
  - `class CaseActionError(Exception)`（`.status_code`：403 權限不足、400 狀態不允許或缺原因）
  - `ACTIONS = ("note", "start", "submit", "verify", "reject", "close_no_gap")`
  - `can_view(case, user) -> bool`：學生本人；導師本班；科辦全部；其他 False。
  - `available_actions(case, user) -> list[str]`
  - `perform(case, user, action: str, note: str = "") -> GraduationCaseEvent`
  - `create_inquiry(student, note: str) -> GraduationCase`：`case_type="inquiry"`、`item="general"`、`open_key=None`；通知導師；**不**列入風險名單。

**動作表（spec 6.4）**

| action | 誰 | 允許的起始狀態 | 結果狀態 | 事件 | 通知 | 原因必填 |
| --- | --- | --- | --- | --- | --- | --- |
| note | 學生 | 非 closed | pending→in_progress，其他不變 | student_note | 導師 | 是 |
| note | 導師 | 非 closed | pending→in_progress，其他不變 | teacher_note | 學生 | 是 |
| start | 三者 | pending | in_progress | started | 無 | 否 |
| submit | 三者 | in_progress | awaiting_verification | submitted | 科辦 | 否 |
| verify | 科辦 | awaiting_verification | closed（improved） | verified | 學生、導師 | 否 |
| reject | 科辦 | awaiting_verification | in_progress | rejected | 學生、導師 | 是 |
| close_no_gap | 科辦 | 非 closed | closed（no_gap） | closed_no_gap | 學生、導師 | 是 |

結案時 `open_key = None`、寫 `closed_at`、`closed_by_id`。

- [ ] **Step 1: 寫失敗測試**
```python
def test_student_note_moves_pending_to_in_progress_and_notifies_teacher(app)
def test_teacher_cannot_act_on_other_class(app)            # CaseActionError, status_code 403；驗收 11
def test_student_cannot_verify(app)                         # 403
def test_reject_requires_reason_and_returns_in_progress(app)  # 驗收 8：空原因 400；有原因→in_progress，學生與導師各 1 則
def test_verify_closes_improved_and_clears_open_key(app)
def test_close_no_gap_records_distinct_reason(app)          # 驗收 9：close_reason == "no_gap"
def test_inquiry_from_grade2_not_in_risk(app)               # 驗收 12：case_type "inquiry"、open_key None
def test_available_actions_by_role(app)                     # 例：awaiting_verification 時科辦有 verify、reject；學生沒有
```
- [ ] **Step 2: 執行確認失敗**（`--basetemp=logs/test-runs/gc-t4-a`）
- [ ] **Step 3: 實作。**
- [ ] **Step 4: 執行確認通過。**
- [ ] **Step 5: 提交**

---

### Task 5: 案件頁、通知頁、學生頁、同步觸發點

**Files:**
- Create: `app/routes/graduation.py`（blueprint `graduation_bp`，在 `app/__init__.py` 註冊）
- Create: `app/templates/graduation_case.html`、`app/templates/notifications.html`
- Modify: `app/routes/student.py`（`graduation_check` 改用 `assess` 與該生案件；文件確認成功 `db.session.commit()` 後呼叫 `sync_student`，約第 750 行）
- Modify: `app/templates/student_graduation_check.html`（判斷結果、依據、補救方式、案件編號與狀態、更正／諮詢表單）
- Modify: `app/routes/transfer_credit.py`（學生儲存與導師確認成功後 `sync_student`）
- Modify: `app/__init__.py`（註冊 blueprint；`context_processor` 提供 `unread_notification_count`）
- Modify: `app/templates/partials/nav.html`（三種角色導覽顯示未讀數，連到通知頁）
- Modify（spec 第十節「管理員可設定模擬日期」）：若 `app/routes/admin.py` 已有編輯 `SystemSetting` 的頁面，把 `graduation_check_today` 加進去；若沒有，第一版只由示範資料與測試設定，並在開發日誌註明（Claude 的決定）
- Test: `tests/test_graduation_case_pages.py`

**Interfaces:**
- Consumes: Task 1 `assess`、`check_today`；Task 3 `sync_student`、`sync_all`；Task 4 全部。
- Produces（路由）：
  - `GET /graduation/cases/<int:case_id>` → `graduation.case_detail`（學生、導師、科辦；`can_view` 為否回 403）
  - `POST /graduation/cases/<int:case_id>/actions`（表單 `action`、`note`）→ `graduation.case_action`；`CaseActionError` 用其 `status_code` 回應並顯示訊息
  - `POST /student/graduation-check/inquiry`（表單 `note`）→ `graduation.create_inquiry`
  - `GET /notifications` → `graduation.notifications`；打開案件頁時，把該使用者指向此案件的未讀通知設為已讀
  - `POST /staff/graduation/recheck`（可選表單 `student_id`）→ `graduation.recheck`（只限科辦）
- 補救方式文字常數放 `graduation_check_service.REMEDY_TEXT`（證照：實施要點第五點配套措施 1～6 項原文摘要＋條款版本；學分：`"請洽科辦確認補修方式。"`）。

- [ ] **Step 1: 寫失敗測試**
```python
def test_case_page_same_number_for_three_roles(app)        # 學生、導師、科辦開同一網址都 200，頁面含同一 G-編號
def test_case_page_forbidden_for_other_student(app)        # 403
def test_opening_pages_creates_nothing(app)                # 驗收 10：GET 學生頁、導師首頁、科辦首頁、案件頁各兩次，案件、事件、通知數不變
def test_confirming_document_triggers_sync(app)            # POST 確認後該生有新案件（today 用 SystemSetting 設在專四下）
def test_case_page_shows_disclaimers(app)                  # 含「僅供提醒」；已結案 improved 時含「不代表學生符合全部畢業資格」
def test_unread_count_drops_after_opening_case(app)
def test_staff_recheck_only_for_staff(app)                 # 導師 POST 403
```
- [ ] **Step 2: 執行確認失敗**（`--basetemp=logs/test-runs/gc-t5-a`）
- [ ] **Step 3: 實作。**
- [ ] **Step 4: 執行確認通過**，並跑 `tests/test_student_navigation.py tests/test_graduation_check_page.py`。
- [ ] **Step 5: 提交**

---

### Task 6: 導師首頁 A 版、導師學生頁、科辦待核對

**Files:**
- Modify: `app/services/graduation_case_service.py`（新增 `class_overview`）
- Modify: `app/routes/main.py`（`teacher_dashboard`、`staff_dashboard` 傳入新資料）
- Modify: `app/templates/dashboard.html`（導師區塊、科辦第三類）
- Modify: `app/routes/teacher.py`、`app/templates/teacher_student.html`（該生判斷結果、案件與處理紀錄、面談表單送到 Task 5 的 action 路由）
- Test: `tests/test_graduation_dashboards.py`

**Interfaces:**
- Consumes: Task 1 `assess`；Task 2 模型；Task 3。
- Produces: `class_overview(students: list[User], today: date | None = None) -> dict`：
  `{"total": int, "met": int, "gap": int, "data": int, "other": int, "priority": list[dict]}`
  - `met`：四項都 `met`；`gap`：有未結案 gap 案件；`data`：無 gap 案件但有未結案 data_needed 案件或任一項 `insufficient_data`；`other`：其餘（修課中、抵免待核對、待人工確認）。四張數字卡顯示 total／met／gap／data，`other` 以小字顯示在比例條下方（Claude 的決定：spec 只定四張卡）。
  - `priority` 每列：`{"student": User, "case": GraduationCase, "label": str, "hint": str}`；只含未結案 gap 與 data_needed 案件（不含 inquiry）。排序：gap 先於 data_needed；gap 內 `item` 依 certificates、required_credits、total_credits、elective_credits；再依該生年級高者先（越接近專五下越急）；再依 current_amount 大者先。
  - `hint`：證照→「依實施要點第五點補救」；學分→「請洽科辦確認補修」；data_needed→「請學生上傳並確認資料」。
- 科辦：`staff_dashboard` 加 `graduation_awaiting`（狀態 awaiting_verification 的案件清單）與「重新檢核全科」按鈕（POST 到 `graduation.recheck`）。
- 下一次檢核時間文字：專四下以前顯示「專四下學期期末考前兩週」；專四下顯示同上；專五上顯示「專五上學期期末考前兩週」；之後顯示「已過兩次檢核，請與科辦確認」。

- [ ] **Step 1: 寫失敗測試**
```python
def test_class_overview_counts(app)            # 4 人：1 met、1 gap、1 data、1 progress → total 4、met 1、gap 1、data 1、other 1
def test_priority_excludes_inquiry(app)
def test_priority_order(app)                   # 證照 gap 在必修 gap 前；gap 都在 data_needed 前
def test_teacher_dashboard_shows_cards_and_names(app)   # 頁面含「已達門檻」「確定有缺口」「資料待確認」與 gap 學生姓名
def test_teacher_sees_only_own_class(app)               # 別班學生姓名不出現
def test_staff_dashboard_lists_awaiting_cases(app)      # 含 G-編號
```
- [ ] **Step 2: 執行確認失敗**（`--basetemp=logs/test-runs/gc-t6-a`）
- [ ] **Step 3: 實作。**
- [ ] **Step 4: 執行確認通過**，另跑 `tests/test_review_workflow.py tests/test_teacher*.py`（存在者）確認既有導師、科辦功能沒壞。
- [ ] **Step 5: 提交**

---

### Task 7: 展示資料、瀏覽器驗收、完整測試、文件

**Files:**
- Modify: `app/demo.py`（**先 `git diff app/demo.py` 看別人未提交的修改，只新增一個獨立函式並在既有建置流程尾端呼叫，不改動別人的段落**）
- Modify: `docs/03_開發紀錄/development-log.md`、`docs/05_交接與專案管理/handoff.md`（最上面加一節）

- [ ] **Step 1: 新增示範資料** `seed_graduation_demo(today: date)`：一個 111 學年度入學的班級（例如「資管科五甲」）、一位已綁班的 `teacher_demo`；至少 4 位假學生，姓名或備註標「僅為測試資料」，課名用 `curriculum_groups.csv` 111 屆的真實課名，涵蓋：已達門檻、證照只有 1 張（gap）、必修不及格（gap）、缺一學期成績（data_needed）。設定 `SystemSetting("graduation_check_today")` 為專五上的日期（例如 `2025-10-15`），並呼叫 `sync_all`。
- [ ] **Step 2: 瀏覽器驗收**（`preview_start` 名稱 `story-merged-5013`）：`teacher_demo` 首頁看到四張卡與名單 → 點學生進案件頁寫面談紀錄 → `student_demo`（或對應假學生）看到通知與案件 → `staff_demo` 在待核對看到案件並退回、再通過。每一步截圖。
- [ ] **Step 3: 完整測試**
Run: `D:\democase\ai\.venv\Scripts\python.exe -m pytest -q --basetemp=logs/test-runs/gc-full-01`
Expected: 全部通過（基準：2026-11-05 為 1148 passed、2 skipped，數字應增加）
- [ ] **Step 4: 開發日誌與交接**：寫做了什麼、測試數字、瀏覽器驗收結果、未做事項（電子郵件、各學期預警、抵免學分、兩套修業規則合併、檢核日期倒數）。
- [ ] **Step 5: 提交**（只加本任務檔案；不推送）

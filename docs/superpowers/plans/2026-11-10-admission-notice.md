# 二技公告（UC-25）實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 管理員核准招生日程後發布二技公告；學生、導師、科辦收到並有未讀標記；導師提醒自己四、五年級的學生；科辦首頁顯示寄送備審截止前未核准的電子獎狀。

**Architecture:** 新增通用 `Announcement`／`AnnouncementRead` 模型與 `announcement_service`（發布、下架、已讀、截止日、導師學生）；新 blueprint `announcement_bp` 放閱讀端與管理端頁面；未讀提示沿用 `Notification`（11-08 已支援非案件通知與 `link`）。截止日一律由 `admission_schedule.load_schedule()` 讀，沒有任何輸入日期的畫面。

**Tech Stack:** Flask、SQLAlchemy、Alembic、Jinja2、pytest（SQLite 記憶體資料庫）。

**Spec:** `docs/superpowers/specs/2026-11-09-admission-notice-design.md`

## Global Constraints

- 全部畫面、訊息、註解用繁體中文；測試資料全部合成。
- 截止日不能由人輸入；抓不到「寄送備審」項目時顯示「簡章未載明」。
- 公告不能刪除，只能下架；發布、下架、導師提醒都寫 `AuditLog`。
- 學生、導師、科辦看不到 `draft`、`withdrawn` 的公告。
- 導師只看到 `teacher_scope.students_for_teacher()` 中 `current_grade` 為 4 或 5 的學生。
- 不改 `app/templates/partials/nav.html`（其他對話在改）；未讀數靠既有「通知」。
- Migration：`revision = "b20261110a01"`，`down_revision = "b20261108f01"`；SQLite 建表前先 `inspector.has_table` 跳過已存在的表（與既有 migration 同風格）。
- 測試指令：`D:\democase\ai\.venv\Scripts\python.exe -m pytest -q --basetemp=logs/test-runs/<新資料夾> <路徑>`。

## Review Focus

1. 同一則公告重複發布（按兩次「發布」）→ 不會重複寄通知；已發布的不能再發布。→ Task 2 `test_publish_twice_does_not_duplicate_notifications`
2. 導師沒有任何帶班（無 `ClassAdvisor`）→ 內容頁顯示「目前沒有您帶的四、五年級學生」，提醒按鈕不出現，POST 也回 400 不寄通知。→ Task 4 `test_teacher_without_class_cannot_remind`
3. 學生直接輸入草稿或已下架公告的網址 → 404。→ Task 3 `test_student_cannot_open_draft_or_withdrawn`
4. 公告沒有對應管道、學年度（手動新增）→ 內容頁不顯示重要日期區塊，不出錯；科辦卡片不以它算截止日。→ Task 2 `test_deadline_ignores_manual_announcement`
5. 日程裡的「寄送備審」只有開始時間沒有結束時間 → 用開始時間當截止。→ Task 2 `test_deadline_uses_start_when_no_end`

---

## File Structure

| 檔案 | 責任 |
| --- | --- |
| Create `app/models/announcement.py` | `Announcement`、`AnnouncementRead` |
| Modify `app/models/__init__.py` | 匯出兩個模型 |
| Create `migrations/versions/b20261110a01_add_announcements.py` | 建兩張表 |
| Create `app/services/announcement_service.py` | 草稿、發布、下架、可見清單、已讀、截止日、導師學生、提醒 |
| Create `app/routes/announcement.py` | `announcement_bp`：閱讀端、管理端、導師提醒 |
| Modify `app/__init__.py` | 註冊 blueprint |
| Create `app/templates/announcements.html`、`announcement_detail.html`、`admin_announcements.html`、`admin_announcement_form.html` | 畫面 |
| Modify `app/routes/admin.py::agent_schedule_decide` | 核准後導到擬公告 |
| Modify `app/templates/admin_agent.html` | 加「二技公告管理」連結 |
| Modify `app/routes/main.py::staff_dashboard`、`app/templates/dashboard.html` staff 區塊 | 截止數字卡＋最新公告連結 |
| Modify `app/templates/student_home.html`、`dashboard.html` teacher 區塊 | 最新公告連結（一行） |
| Create `tests/test_announcements.py` | 全部測試 |

---

### Task 1: 模型與 migration

**Files:** Create `app/models/announcement.py`、`migrations/versions/b20261110a01_add_announcements.py`；Modify `app/models/__init__.py`；Test `tests/test_announcements.py`

**Interfaces — Produces:**
- `Announcement`（`__tablename__ = "announcements"`）：`id`、`kind: str(20)` 預設 `"admission"`、`title: str(200)`、`body: Text`、`audience: str(60)` 預設 `"student,teacher,staff"`、`channel: str(30)|None`、`admission_year: int|None`、`status: str(20)` 預設 `"draft"`（index）、`created_by`、`published_by`、`published_at`、`withdrawn_by`、`withdrawn_at`、`created_at`；屬性 `audience_roles -> set[str]`。
- `AnnouncementRead`（`announcement_reads`）：`id`、`announcement_id`、`user_id`、`read_at`；`UniqueConstraint(announcement_id, user_id, name="uq_announcement_read")`。

- [ ] Step 1：寫 `test_migration_creates_announcement_tables`：對空 SQLite 檔跑 `flask db upgrade`（照 `tests/test_form_library.py` 的 migration 測試寫法），`inspect` 後 `"announcements"` 與 `"announcement_reads"` 都在，且 `announcement_reads` 有 `uq_announcement_read`。另寫 `test_audience_roles_parses_csv`：`Announcement(audience="student,staff").audience_roles == {"student", "staff"}`。
- [ ] Step 2：執行，預期 FAIL（ImportError）。
- [ ] Step 3：建模型、匯出、寫 migration。
- [ ] Step 4：執行兩個測試，預期 PASS。
- [ ] Step 5：commit `二技公告：新增公告與已讀資料表`。

### Task 2: announcement_service

**Files:** Create `app/services/announcement_service.py`；Test `tests/test_announcements.py`

**Interfaces — Consumes:** Task 1 模型；`admission_schedule.load_schedule()`（回傳 `{(channel, year): [ {name, start, end, ...} ]}`，實作前先讀確認鍵名）；`admission_schedule.CHANNEL_LABELS`；`teacher_scope.students_for_teacher`；`journey_service.current_grade`；`Notification(recipient_id, message, link)`；`AuditLog`。

**Produces（全部 module 層函式）：**
- `draft_from_schedule(channel: str, year: int, actor) -> Announcement`：同管道同學年已有 `draft` 就更新它的 title/body 並回傳，否則新建。title = `f"{year} 學年度{CHANNEL_LABELS[channel]}招生日程公告"`；body 逐行 `"・{name}：{日期}"`（日期格式 `M/D` 或 `M/D–M/D`）。
- `create_manual(title: str, body: str, audience: set[str], actor) -> Announcement`（`channel`、`admission_year` 為 None）。
- `publish(announcement, actor, now=None) -> int`：只允許 `draft`，否則 `ValueError("只有草稿可以發布")`；設 published 欄位；替 `audience_roles` 內每位 `is_active` 使用者建 `Notification(message=f"二技公告：{title}", link=url_for("announcement.detail", announcement_id=id))`；寫 `AuditLog(action="announcement.publish")`；回傳通知數。
- `withdraw(announcement, actor, now=None) -> None`：只允許 `published`；寫 `AuditLog(action="announcement.withdraw")`。
- `visible_for(user) -> list[Announcement]`：`published` 且 `user.role in audience_roles`，依 `published_at` 新到舊。
- `unread_ids(user, announcements) -> set[int]`
- `mark_read(announcement, user, now=None) -> None`：寫 `AnnouncementRead`（已有就略過），並把 `recipient_id == user.id` 且 `link` 等於該公告網址、未讀的 `Notification` 標已讀。
- `key_dates(announcement) -> list[dict]`：無 channel/year 回 `[]`；否則 `load_schedule()[(channel, year)]` 各項 `{name, start, end, is_send_review}`，`is_send_review = "寄送備審" in name`。
- `send_review_deadline(today=None) -> dict | None`：取最新 `published_at`、有 channel/year 的公告；沒有則 None。找 `is_send_review` 項目，截止 = `end or start`；回 `{"announcement": a, "deadline": datetime|None, "label": "M/D" 或 "簡章未載明"}`；截止日 `< today` 回 None。
- `teacher_targets(teacher, today=None) -> list[dict]`：`students_for_teacher` 中 `current_grade(profile.admission_year, today) in (4, 5)`，每筆 `{student, grade, target_count}`（`StudentTarget` 筆數）。
- `remind_students(announcement, teacher, today=None) -> int`：沒有學生 → `ValueError("目前沒有您帶的四、五年級學生")`；每位學生建 `Notification(message=f"{teacher.display_name}老師提醒你看二技公告：{title}", link=公告網址)`；寫 `AuditLog(action="announcement.remind", detail_json={"student_ids": [...]})`；回傳人數。

**測試（共用 `_app(tmp_path)`：照 `tests/test_award_certificates.py::cert_app` 建 admin、學生 `s5`（admission_year=111）、`s4`（112）、`s3`（113）、別班 `x5`（111）、導師 `t1`（帶 s5/s4/s3 的班）、`t0`（無帶班）、科辦 `staff`；`today=date(2026, 11, 10)`；日程用 `AdmissionScheduleEvent(status="published", channel="skill_review", admission_year=116, ...)` 合成，含「向甄審校院繳費並寄送備審資料」2027-04-20～2027-04-24）：**
- `test_draft_from_schedule_prefills_dates`：title 含 `"116 學年度二技技優甄審"`，body 含 `"寄送備審"` 與 `"4/20–4/24"`；再呼叫一次仍只有 1 筆 draft。
- `test_publish_notifies_audience_and_logs`：回傳值 == 啟用中的 student+teacher+staff 人數；admin 沒收到；`AuditLog` 有 `announcement.publish`。
- `test_publish_twice_does_not_duplicate_notifications`：第二次 `pytest.raises(ValueError)`，通知數不變。
- `test_visible_and_unread_flow`：學生 `visible_for` 含它、`unread_ids` 含它；`mark_read` 後不含，且該 `Notification.read_at` 不為 None。
- `test_withdraw_hides_and_logs`：下架後 `visible_for(學生) == []`，`AuditLog` 有 `announcement.withdraw`。
- `test_send_review_deadline_label`：`label == "4/24"`；`today=date(2027, 4, 25)` 時回 None。
- `test_deadline_says_not_stated_when_missing`：日程沒有寄送備審項目 → `label == "簡章未載明"`，`deadline is None`。
- `test_deadline_uses_start_when_no_end`：寄送備審只有 start 2027-04-20 → `label == "4/20"`。
- `test_deadline_ignores_manual_announcement`：只有手動公告已發布 → `send_review_deadline()` 為 None，`key_dates` 為 `[]`。
- `test_teacher_targets_only_grade_4_and_5`：t1 → 學生集合 `{s5, s4}`；不含 s3、x5。
- `test_remind_students_notifies_and_logs`：回 2；兩位學生各 1 則含 `"陳導師老師提醒你"`；`AuditLog` 有 `announcement.remind`。

- [ ] Step 1：寫上面 11 個測試。
- [ ] Step 2：執行，預期 FAIL。
- [ ] Step 3：實作 service。`url_for` 需要 request context，測試內用 `app.test_request_context()`；或 Task 3 註冊 blueprint 前先以字串 `f"/announcements/{id}"` 產生網址——**採後者**（`announcement_url(a) -> str`），route 也用同一路徑，避免 service 依賴 request。
- [ ] Step 4：執行，預期 PASS。
- [ ] Step 5：commit `二技公告：發布、下架、已讀、截止日與導師提醒服務`。

### Task 3: 閱讀端頁面（學生、導師、科辦）

**Files:** Create `app/routes/announcement.py`、`app/templates/announcements.html`、`app/templates/announcement_detail.html`；Modify `app/__init__.py`

**Interfaces — Produces:** `announcement_bp`；`GET /announcements`（endpoint `announcement.index`）、`GET /announcements/<int:announcement_id>`（`announcement.detail`），皆 `role_required("student", "teacher", "staff")`。內容頁呼叫 `mark_read`，顯示 `key_dates`（寄送備審那列加 `data-send-review`），無日期時整區不出現。清單未讀列加 `data-unread` 與文字「未讀」。

- [ ] Step 1：測試 `test_index_shows_unread_badge`（學生 GET 清單含標題與「未讀」；開內容頁後清單不再含 `data-unread`）、`test_detail_highlights_send_review`（內容頁含 `data-send-review` 與「4/20–4/24」）、`test_student_cannot_open_draft_or_withdrawn`（draft、withdrawn 都 404）、`test_admin_cannot_open_reader_pages`（admin GET `/announcements` 非 200）。
- [ ] Step 2：執行，預期 FAIL。
- [ ] Step 3：實作 route 與模板（沿用 `base.html` 與 `work-panel`／`work-list` 樣式，參考 `notifications.html`）。
- [ ] Step 4：執行，預期 PASS。
- [ ] Step 5：commit `二技公告：學生、導師、科辦的公告清單與內容頁`。

### Task 4: 導師提醒

**Files:** Modify `app/routes/announcement.py`、`app/templates/announcement_detail.html`

**Interfaces — Produces:** `POST /announcements/<id>/remind`（`announcement.remind`，`role_required("teacher")`）→ 呼叫 `remind_students`，成功後導回內容頁並顯示「已提醒 N 位學生」；`ValueError` → 400。內容頁（導師）顯示 `teacher_targets` 表格（姓名、年級、目標校系數）與按鈕；沒有學生顯示「目前沒有您帶的四、五年級學生」且不出現按鈕。

- [ ] Step 1：測試 `test_teacher_sees_own_grade_4_5_students`（t1 內容頁含 s5、s4 姓名，不含 s3、x5）、`test_teacher_remind_creates_notifications`（POST 後 302，學生通知頁含提醒文字）、`test_teacher_without_class_cannot_remind`（t0 內容頁含「目前沒有您帶的四、五年級學生」、不含「提醒這些學生」；POST 回 400）、`test_student_cannot_remind`（學生 POST 非 2xx/3xx 成功，且無新通知）。
- [ ] Step 2：FAIL。Step 3：實作。Step 4：PASS。
- [ ] Step 5：commit `二技公告：導師一鍵提醒自己的四、五年級學生`。

### Task 5: 管理端（擬公告、發布、下架、手動新增）

**Files:** Modify `app/routes/announcement.py`、`app/routes/admin.py::agent_schedule_decide`、`app/templates/admin_agent.html`；Create `app/templates/admin_announcements.html`、`app/templates/admin_announcement_form.html`

**Interfaces — Produces（皆 `role_required("admin")`）：**
- `GET /admin/announcements`（`announcement.admin_list`）：草稿、已發布、已下架三區；已發布有「下架」按鈕；**沒有刪除**。
- `GET/POST /admin/announcements/new`（`announcement.admin_new`）：手動新增（title、body、audience 勾選），存成草稿。
- `GET/POST /admin/announcements/<id>/edit`（`announcement.admin_edit`）：只能改 draft；表單有 `action=save` 與 `action=publish` 兩鈕；**表單沒有任何日期欄位**。
- `POST /admin/announcements/<id>/withdraw`（`announcement.admin_withdraw`）。
- `agent_schedule_decide` 在 `approve` 成功後呼叫 `draft_from_schedule` 並 `redirect(url_for("announcement.admin_edit", announcement_id=...))`；`reject` 行為不變。

- [ ] Step 1：測試 `test_approving_schedule_opens_prefilled_draft`（建 candidate 日程，admin POST `/admin/agent/schedule/skill_review/116/approve` → 302 到 edit 頁，GET 含「寄送備審」）、`test_admin_edits_and_publishes`（POST 改 title＋`action=publish` → status published、學生清單看到新標題）、`test_edit_form_has_no_date_inputs`（edit 頁不含 `type="date"`、`type="datetime-local"`）、`test_admin_withdraw_and_no_delete`（下架後 status withdrawn；admin_list 不含「刪除」）、`test_non_admin_cannot_manage`（學生、科辦 GET `/admin/announcements` 非 200）。另更新既有核准日程測試若斷言了導向 `agent_home`（先 `grep -rn "schedule/skill_review" tests/` 找出並改成新導向）。
- [ ] Step 2：FAIL。Step 3：實作。Step 4：PASS。
- [ ] Step 5：commit `二技公告：管理員擬稿、發布、下架與手動新增`。

### Task 6: 首頁入口與科辦截止卡

**Files:** Modify `app/routes/main.py::staff_dashboard`（與 teacher／student 首頁對應函式）、`app/templates/dashboard.html`、`app/templates/student_home.html`

**Interfaces — Consumes:** `send_review_deadline(today)`、`visible_for(user)`、`unread_ids`。**Produces:** `staff_dashboard` 多傳 `admission_deadline`（`send_review_deadline()` 結果）；有值時 `work-metrics` 多一張 `<a class="work-metric work-metric--link" data-admission-deadline href="{{ url_for('certificate.staff_list') }}">`，`<span>二技截止前未核准的電子獎狀</span><strong>{{ staff_pending_certificates }}</strong><small>寄送備審 {{ label }} 截止</small>`（label 為「簡章未載明」時 small 寫「截止日：簡章未載明」）。三種角色首頁各一行 `data-latest-announcement`：最新可見公告標題連結＋未讀時加「未讀」；沒有公告就不出現。

- [ ] Step 1：測試 `test_staff_home_shows_deadline_card`（1 筆 pending 證書＋已發布公告 → 首頁含「二技截止前未核准的電子獎狀」與「4/24」）、`test_staff_home_card_hidden_after_deadline`（monkeypatch `announcement_service` 的 today 或傳入參數→ 截止後不含 `data-admission-deadline`）、`test_staff_home_not_stated`（無寄送備審 → 含「簡章未載明」）、`test_homes_show_latest_announcement`（學生、導師、科辦首頁都含 `data-latest-announcement` 與標題）。
- [ ] Step 2：FAIL。Step 3：實作（不動 `partials/nav.html`）。Step 4：PASS。
- [ ] Step 5：commit `二技公告：首頁最新公告與科辦寄送備審截止卡`。

### Task 7: 完整測試、瀏覽器驗證、開發日誌

- [ ] Step 1：背景跑完整測試 `D:\democase\ai\.venv\Scripts\python.exe -m pytest -q --basetemp=logs/test-runs/admission-notice-full`，預期全部通過（失敗先查是否為本分支造成）。
- [ ] Step 2：用合成資料啟動預覽站（埠號 5077，非 5013/5041），走：管理員核准日程 → 擬稿 → 發布 → 學生、導師、科辦清單見未讀與通知數 → 導師提醒 → 科辦首頁見截止卡。截圖留證。
- [ ] Step 3：在 `docs/03_開發紀錄/development-log.md` 最上面寫一節（含 migration `b20261110a01` ← `b20261108f01`，提醒合併時可能多 head）。
- [ ] Step 4：commit `二技公告：開發日誌`。不推送。

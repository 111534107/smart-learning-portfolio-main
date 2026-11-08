# 表單下載區（UC-28／F-53）實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans（本專案 AGENTS.md：未經使用者明確要求不啟動子代理，所以用 Native 方式在本對話實作）. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 科辦在 `/staff/forms` 管理分類、上架／改版／下架表單；學生與老師在 `/forms` 下載開放給自己且上架中的最新版。

**Architecture:** 新模型檔 `app/models/form_library.py`（三張表）＋服務層 `app/services/form_library_service.py`（權限、上傳檢查、建立版本、示範資料）＋藍圖 `app/routes/forms.py`（學生老師頁與科辦頁）。檔案沿用 `storage_service`。

**Tech Stack:** Flask、SQLAlchemy、Alembic、Jinja2、pytest。

**Spec:** `docs/superpowers/specs/2026-11-08-forms-download-design.md`

## Global Constraints

- 不做收件；不刪檔、不覆寫版本；下載檔一律 `as_attachment=True`。
- 副檔名 `pdf, doc, docx, xls, xlsx, odt, ods`；單檔上限 `FORM_MAX_BYTES = 10 * 1024 * 1024`。
- 不存在 → 404；存在但無權限、已下架、分類停用 → 403。
- Alembic revision `b20261108f01`，down_revision `b20261105c01`。
- `partials/nav.html` 只加三處：staff「表單下載區」、teacher「表單下載」、學生刊頭右側「表單下載」小連結。
- 介面文字繁體中文；示範檔只用程式產生的合成 PDF。

## Review Focus

1. 學生用網址下載只開放老師的表單 → 403（Task 2 測試）。
2. 檔案副檔名是 `.pdf` 但內容不是 PDF → 拒收（Task 1 測試）。
3. 改版後 `/forms` 下載拿到新版、舊版檔案仍在且科辦可下載（Task 2 測試）。
4. 開放對象一個都沒勾 → 拒收，不建立表單（Task 2 測試）。
5. 分類停用時，原本可下載的表單網址也變 403（Task 2 測試）。

---

### Task 1: 模型、migration、服務層

**Files:**
- Create: `app/models/form_library.py`、`migrations/versions/b20261108f01_add_form_library.py`、`app/services/form_library_service.py`、`tests/test_form_library.py`
- Modify: `app/models/__init__.py`（匯出 `FormCategory, FormItem, FormItemVersion`）、`app/services/audit_service.py`（ACTION_LABELS 加 7 筆）

**Interfaces（Produces）:**
- `FormCategory(name, sort_order, is_active)`、`FormItem(category_id, title, description, open_to_students, open_to_teachers, is_published, created_by_id)`，`item.versions`（依 version_no 排序）、`item.latest_version`（property）。`FormItemVersion(item_id, version_no, file_path, original_filename, file_size, file_sha256, note, uploaded_by_id)`，`UniqueConstraint(item_id, version_no)`。
- `class UploadRejected(ValueError)`（訊息是給使用者看的中文）。
- `check_upload(filename: str, data: bytes) -> str`：回傳清理後檔名，不合格丟 `UploadRejected`。
- `add_version(item, filename, data, uploader, note="") -> FormItemVersion`：檢查、存檔（`storage_service.save(..., folder="forms")`）、版本號＝最大＋1，flush，不 commit。
- `can_download(user, item) -> bool`；`visible_items(user, q="") -> list[(FormCategory, [FormItem])]`。
- `seed_demo_forms(staff_user) -> None`；`demo_pdf(text: str) -> bytes`。

- [ ] Step 1：寫失敗測試 `test_check_upload_rejects_bad_extension_signature_empty_and_size`（`.exe`、`.pdf` 內容 `hello`、空檔、超過 `FORM_MAX_BYTES` 都丟 `UploadRejected`；合法 PDF 回傳檔名）、`test_add_version_increments_and_keeps_old_file`、`test_can_download_rules`（學生／老師 × 開放旗標 × 下架 × 分類停用 × staff 一律可）、`test_migration_creates_and_drops_form_tables`、`test_seed_demo_forms_is_synthetic`。
- [ ] Step 2：跑 `pytest tests/test_form_library.py -q` 確認失敗。
- [ ] Step 3：實作模型、migration（有表就跳過，與既有 migration 寫法一致）、服務層、ACTION_LABELS。
- [ ] Step 4：測試通過。
- [ ] Step 5：提交。

### Task 2: 路由與頁面

**Files:**
- Create: `app/routes/forms.py`（`forms_bp`）、`app/templates/forms_list.html`、`app/templates/staff_forms.html`、`app/templates/staff_form_detail.html`
- Modify: `app/__init__.py`（註冊藍圖）、`app/templates/partials/nav.html`
- Test: `tests/test_form_library_routes.py`

**路由:**
- `GET /forms`（student, teacher）；`GET /forms/<item_id>/download`（student, teacher, staff）→ 最新版。
- `GET /staff/forms`、`POST /staff/forms`（上架新表單）、`POST /staff/forms/categories`（新增）、`POST /staff/forms/categories/<id>`（改名、排序、啟用切換）。
- `GET /staff/forms/<item_id>`、`POST /staff/forms/<item_id>`（編輯資料）、`POST /staff/forms/<item_id>/versions`（改版）、`POST /staff/forms/<item_id>/publish`（`action=unpublish|republish`）、`GET /staff/forms/versions/<version_id>/download`。

- [ ] Step 1：寫失敗測試：`test_teacher_only_form_hidden_and_403_for_student`、`test_new_version_download_returns_new_content_old_kept`、`test_unpublish_hides_and_blocks_then_republish`、`test_inactive_category_blocks_download`、`test_student_and_teacher_cannot_use_staff_pages`、`test_create_requires_audience_and_valid_file`、`test_actions_write_audit_logs`、`test_nav_entries`（staff 首頁有「表單下載區」、教師首頁有「表單下載」、學生首頁有 `/forms` 連結）。
- [ ] Step 2：確認失敗。
- [ ] Step 3：實作路由與三個模板（沿用 `work-panel`、`data-table`、`<details>`）。
- [ ] Step 4：通過。
- [ ] Step 5：提交。

### Task 3: 示範資料接上、完整測試、瀏覽器走查、日誌

**Files:** Modify `app/demo.py`、`scripts/run_demo.py`（各加一行呼叫 `seed_demo_forms`）、`tests/test_local_demo.py`（展示站有表單）、`docs/03_開發紀錄/development-log.md`。

- [ ] Step 1：加測試 `test_local_demo_has_demo_forms`，接上示範資料。
- [ ] Step 2：背景跑完整測試 `D:\democase\ai\.venv\Scripts\python.exe -m pytest -q --basetemp=logs/test-runs/forms-full-20261108`，預期全過。
- [ ] Step 3：用自己的埠（5077）啟動本機展示站，瀏覽器走：科辦上架 → 改版 → 學生下載到新版 → 下架後學生看不到。
- [ ] Step 4：開發日誌最上面寫一節（含 revision／down_revision、學生入口暫放位置）。
- [ ] Step 5：只提交自己的檔案，不推送。

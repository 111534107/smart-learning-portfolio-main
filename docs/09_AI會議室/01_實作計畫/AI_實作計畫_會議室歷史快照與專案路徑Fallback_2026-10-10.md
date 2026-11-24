# 會議室歷史快照與專案路徑 fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓檔案面板在有歷史快照時使用快照，快照不存在時依會議 `meta.json` 的 `repo` 回退到目前專案目錄，並清楚標示來源。

**Architecture:** 新增僅供檔案面板使用的 `preview_root()`，優先回傳 `workspaces/<meeting-id>`，不存在時驗證 `meta.json` 的 `repo` 目錄並回傳專案根目錄。AI 執行仍由 `start_turns()` 明確傳入歷史快照路徑，不使用 fallback。API 回傳來源與警告，前端在檔案面板顯示「歷史快照／目前專案」狀態。

**Tech Stack:** Python 3、`http.server`、Pathlib、原生 JavaScript／HTML、pytest。

**Spec:** `D:\democase\ai\docs\09_AI會議室\AI_設計規格_公開會議記憶庫與團隊同步_2026-10-10.md`

## Global Constraints

- 歷史快照優先；只有快照不存在時才可使用 `meta.json` 的 `repo`。
- fallback 只供檔案面板預覽與讀取證據；AI live turn 仍只能讀隔離快照。
- 所有 fallback 路徑必須是已存在目錄，檔案路徑必須經 `child_path()` containment check。
- 找不到快照與專案目錄時，API 回傳可理解的缺失狀態，不回傳伺服器例外細節。
- 相關變更追加到 `ai/docs/03_開發紀錄/development-log.md` 與工作佇列代理回報。

### Task 1: Backend source selection and regression tests

**Files:**
- Modify: `D:\democase\ai-meeting-room\server.py`
- Test: `D:\democase\ai-meeting-room\tests\test_server_document_preview.py`

**Interfaces:**
- Produces `preview_root(meeting_id) -> tuple[Path, str | None]` where source is `snapshot`, `project`, or `None`.
- `workspace_tree()` returns `source` and `notice`; `workspace_file()` and raw download use the same preview root.

- [x] **Step 1: Write failing tests** for snapshot precedence, project fallback, missing source, and live-turn isolation.
- [x] **Step 2: Run the focused tests** and confirm they fail because `preview_root` and source metadata do not exist.
- [x] **Step 3: Implement `preview_root()`** and route only preview APIs through it; retain `agents.run(..., WORKSPACES / meeting_id, ...)`.
- [x] **Step 4: Run focused tests** and confirm they pass.

### Task 2: File-panel source notice

**Files:**
- Modify: `D:\democase\ai-meeting-room\static\index.html`
- Test: `D:\democase\ai-meeting-room\tests\test_layout_and_preview.py`

- [x] **Step 1: Add a failing static test** requiring source/notice state and a visible fallback warning.
- [x] **Step 2: Run the test and confirm the expected failure.**
- [x] **Step 3: Add `#fpNotice`, store tree metadata, and render distinct snapshot/project/missing notices.**
- [x] **Step 4: Run the static test and the full test suite.**

### Task 3: Public-memory documentation and log

**Files:**
- Modify: `D:\democase\ai-meeting-room\README.md`
- Modify: `D:\democase\ai\docs\09_AI會議室\AI_設計規格_公開會議記憶庫與團隊同步_2026-10-10.md`
- Modify: `D:\democase\ai\docs\03_開發紀錄\development-log.md`
- Modify: `D:\democase\ai\docs\AI_代理協作_工作佇列.md`

- [x] **Step 1: Document** that public `meetings/` can be combined with a same-layout `D:\democase` checkout, while `workspaces/` is optional for historical preview.
- [x] **Step 2: Record** the source-selection behavior, safety boundary, tests, and known limitation for teammates.
- [x] **Step 3: Review diffs** to preserve existing agent history and avoid claiming GitHub push.

### Verification

- [x] Run `python -m pytest tests -q -p no:cacheprovider --basetemp=D:\democase\.tmp\meeting-room-tests`.
- [x] Run `python -m py_compile document_extract.py server.py agents.py`.
- [x] Run `git diff --check` and inspect `git status --short`.

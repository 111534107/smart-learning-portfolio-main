# 流程圖修正 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修正專案文件的系統流程圖，使其呈現 P0 檔案分析根流程與各角色的檢核責任，並統一為可直接用於報告的視覺格式。

**Architecture:** 以 Mermaid 原始碼作為唯一可維護來源。`diagrams.md` 提供完整的圖表說明，`docs/images/*.mmd` 提供報告匯出的獨立圖檔；兩者使用相同角色名稱、流程邊界與風格變數。

**Tech Stack:** Markdown、Mermaid、Git。

**Spec:** `docs/superpowers/specs/2026-09-24-flow-diagram-correction-design.md`

## Global Constraints

- 僅使用 `student`、`teacher`、`staff`、`admin` 登入角色。
- P0 固定為上傳、擷取、學生確認、規則套用、人工檢核、學習結果與 Word 產出。
- AI 結果為草稿或候選提示，不得自行形成正式判定。
- 保留既有非本次變更的工作樹內容；Git 僅暫存本次圖表與日誌檔案。

## Review Focus

- Mermaid 是否能解析，特別是含中文標點與多行節點的圖。
- P0 圖是否完整呈現 Word 產出，而非止於送審或任務地圖。
- 教師回饋與科辦正式結論是否被畫成不同責任。
- 是否意外加入 `reviewer` 角色或讓 AI 直接定案。
- P1、P2 與 Future 是否被誤畫為 P0 主路徑。

---

### Task 1: 建立統一圖表視覺與角色規範

**Files:**
- Modify: `docs/04_圖表與介面/03_檢查與圖表規範/diagram-style-guide.md`

- [ ] 補充白底、細灰框、繁中字型、低飽和色彩與閱讀方向規則。
- [ ] 更新圖表清單，將 D-02 定義為 P0 檔案分析主流程，新增人工檢核與補件圖。
- [ ] 檢查角色命名，確認沒有獨立 `reviewer` 登入角色。

### Task 2: 改寫主流程、人工檢核與資料流程圖

**Files:**
- Modify: `docs/04_圖表與介面/03_檢查與圖表規範/diagrams.md`
- Modify: `docs/images/D-01-use-case-v2.mmd`
- Modify: `docs/images/D-02-login-role-routing.mmd`
- Modify: `docs/images/D-10-midterm-core-flow.mmd`

- [ ] 將 P0 主流程改為「上傳 → 擷取 → 學生校正 → 規則套用 → 人工檢核 → 產出」。
- [ ] 新增教師／科辦人工檢核與補件迴圈，區分回饋與正式結論。
- [ ] 移除 GitHub 作為 P0 架構依賴，將 AI 標示為可替換分析服務。
- [ ] 將角色圖和獨立 `.mmd` 檔同步為相同責任邊界與視覺規格。

### Task 3: 降階延伸流程並同步規格文字

**Files:**
- Modify: `docs/images/D-03-group-project-review-flow.mmd`
- Modify: 含舊 P0 主流程的正式規格與設計文件

- [ ] 將小組專題流程標示為 P1 補充，連回學生已確認學習歷程。
- [ ] 將備審檢核、招生資料與五年地圖分別標示為 Future 或 P2。
- [ ] 將舊版主流程文字替換為已確認 P0 流程，保留歷史脈絡但不把舊流程當現行規格。

### Task 4: 驗證、記錄與發布

**Files:**
- Modify: `docs/03_開發紀錄/development-log.md`

- [ ] 使用 Mermaid CLI 或等效解析器驗證所有變更圖檔。
- [ ] 檢查本次 diff，只保留流程圖、規範、相關規格文字與開發日誌。
- [ ] 提交本次圖表修正並推送 `main` 到 `origin` GitHub。

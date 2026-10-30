# Checklist：2026-10-28 指導討論後續

> 對應任務清單：[代辦任務清單_2026-10-28_指導討論.md](代辦任務清單_2026-10-28_指導討論.md)。每完成一項，把 `[ ]` 改成 `[x]`，並在括號寫證據（測試名稱、檔案路徑或日誌日期）。未確認的項目不要打勾。

## 開工前（待確認）

- [ ] Q1 登入後引導：自動進入或學生選擇（回聽 00:00–01:20）
- [ ] Q2 「主任」與「科主」是否同一角色（14:19–15:10）
- [ ] Q3 統計表是使用者統計或管理者統計（13:48–13:53）
- [ ] Q4 排行是否隨資料自動更新（05:21–05:23）
- [x] Q5 拼圖完成狀態的具體畫面（09:09–10:16）（使用者沒有定見，2026-10-28 核准 Claude 建議：有資料的格亮起、亮起的格也能再上傳；走過年級每格都亮時顯示「拼圖完成！」並開放「生成自傳」）
- [ ] Q6 一千人使用的成本估算範圍（01:37–02:05）
- [ ] Q7 「你不把這幾個月做出來」整句意思（13:30–13:34）

## 工作流 A：學生引導與完成狀態

- [ ] A1 盤點現有引導頁並寫出缺口
- [ ] A2 登入後說明上傳順序、OCR 核對與可做的分析（需 Q1）
- [x] A3 拼圖完成狀態：上傳後亮起、可重複上傳（需 Q5）（首頁大桌板 `student_home.html`、`journey_home.board`；拼圖完成才能生成自傳，網頁與 AI 小幫手共用 `board_block_reason`；`test_board_*`、`test_lit_slots_are_links_for_another_upload`、`test_autobiography_blocked_until_board_complete`、`test_draft_tool_refuses_when_board_is_incomplete`；2026-10-28 瀏覽器 390px／1280px 實測無水平捲動）。示範帳號 student_demo 拼圖 0／30，目前示範時無法生成自傳，待使用者決定

## 工作流 B：OCR 核對

- [x] B1 確認 OCR 核對頁的修正與確認功能，並改成左圖右表、待確認列數、低信心欄位標橘（`learning_profile_review.html`；`test_review_marks_low_confidence_rows`、`test_review_unknown_confidence_is_not_orange`；2026-10-28 瀏覽器 390px／1280px 實測）
- [x] B2 未確認資料不進 AI 分析（`test_unconfirmed_document_excluded_from_ai_input`；修正 `agent_file_tool.get_my_document` 原本會把未確認的 OCR 草稿傳給 AI）

## 工作流 C：校系建議總覽

- [x] C1 盤點現有比對頁呈現方式（`rank_programs` 已有排序與 `gap["items"]`，沿用）
- [x] C2 單頁排行或圖表，點入看細節：橫條／長條切換、篩選（科系、學制、是否可報）、點入看已符合與缺少（`tests/test_matching_page.py`；2026-10-28 瀏覽器 390px 實測）。地區篩選待 B-2（沒有地區資料）
- [ ] C3 新增資料後排序更新（需 Q4；目前每次開頁即時計算）
- [x] C4 百分比標示「準備度／建議值」，無錄取保證字樣（排行頁、細項頁、Agent 結果頁已改；`matching_service.py` 第 46、157 行與 `agent_advisor.py` 第 31、32、140 行已於 2026-10-29 改為準備度）

## 工作流 G：篩選選項後台

- [x] G1 篩選選項資料表與遷移（`MatchFilterOption`、`migrations/versions/e5b9d1c3a826_add_match_filter_options.py`；`tests/test_match_filter_options.py`）
- [x] G2 管理頁：新增、修改、停用（`/admin/match-filters`；`tests/test_match_filter_admin.py`）

## 工作流 D：AI 比分檢查

- [x] D1 用既有測試資料人工檢查比分合理性，留紀錄（`docs/superpowers/plans/2026-10-28-score-check-notes.md`：純文件項目不列入分母，只有成績也可能顯示 100%）
- [ ] D2 若不合理：先寫失敗測試，再修，記錄測試數字（待使用者決定是否改算法）

## 工作流 E：權限與統計（需 Q2、Q3）

- [ ] E1 權限表經老師確認
- [ ] E2 主任後台彙總統計（使用人數、班級使用、志願分布）
- [ ] E3 導師只能看本班上傳資料（測試）

## 工作流 F：文件、命名與待確認

- [ ] F1 「招生資料 Agent」名稱與責任書面確認
- [ ] F2 文件寫明科助可選擇是否協助
- [ ] F3 用量與成本估算（需 Q6）
- [ ] F4 回聽錄音，Q1–Q7 每題有結論或列為待老師確認

## 收尾

- [x] 每個完成的工作流都在 `docs/03_開發紀錄/development-log.md` 最上面有一節（2026-10-28「指導討論三畫面」）
- [x] 相關測試全部執行，結果如實寫入日誌（927 passed, 2 skipped, 0 failed）
- [ ] 未完成項目寫在日誌「下一步」，不要留白

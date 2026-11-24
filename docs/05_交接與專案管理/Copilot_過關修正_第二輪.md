# Copilot 過關修正第二輪

## 修正內容

1. 平板與手機頁首主導覽連結高度至少 44px，修改 `student-v2/shell.css`。
2. 手機與平板「我的資料」分頁標籤高度至少 44px，修改 `student-v2/shell.css`。
3. 目標校系排行項目的 summary／連結整列最小高度 44px，修改 `design-system.css`。
4. 首頁與寫自傳頁字級切換按鈕設為 44×44px，修改 `design-system.css`。
5. 實習履歷的性別／其他單選標籤、縣市與區鄉下拉、文字輸入欄、核取框及操作按鈕在手機、平板具 44px 點擊高度，修改 `student-v2/home-desk.css`。
6. 實習履歷 `.rz-side` 在 1100px 以下移至履歷後方的文件流，預設沿用既有按鈕收合，把手改為 static；打字時側欄隱藏，修改 `student-v2/home-desk.css`。
7. 批次生成頁根節點、主內容與紙張軌道限制寬度並使用 `overflow-x: clip`，避免桌寵泡泡或變形元素造成文件橫向捲動，修改 `design-system.css`。
8. 寫自傳頁深色外觀的「上一段」、「主張」、字數與位置文字及段落工具列改用 `--card`、`--surface`、`--ink`、`--line`，修改 `design-system.css`。
9. 寫自傳段落標題改為可換行、不裁切，修改 `design-system.css`。
10. 寫自傳每段儲存列保持在 textarea 前的文件流，打字時仍顯示「儲存」；履歷自有「儲存草稿」按鈕保持可見，修改 `design-system.css` 與 `student-v2/home-desk.css`。兩頁模板已有符合文字與 DOM 順序的按鈕，未改動模板。
11. 學生首頁路線數字對比調整，淺色下第三、四站使用黑字，深色下使用 `--on`；「你在這裡」使用 `--on` 搭配 `--accent`，修改 `student-v2/home-desk.css`。
12. 尺寸覆寫限於 1100px 以下，桌面版只調整明確要求的段落標題／深色對比／批次頁橫向溢出；尊重現有 reduced-motion 規則，未更動已通過頁面的樣式，修改檔案如上。

## 修改檔案

- `app/static/css/design-system.css`
- `app/static/css/student-v2/shell.css`
- `app/static/css/student-v2/home-desk.css`
- `docs/05_交接與專案管理/Copilot_過關修正_第二輪.md`

未改動模板、Python、欄位名稱、`data-*`、`data-tour` 或套件；未執行終端機指令或測試，依任務限制僅檢視並修改檔案。工作樹中找不到任務指定的 `AGENTS.md` 與 `過關標準_畫面與動線_2026-11-20.md`，因此本輪依任務文字、第一輪紀錄、ux3 檢查報告及檢查腳本規則處理。

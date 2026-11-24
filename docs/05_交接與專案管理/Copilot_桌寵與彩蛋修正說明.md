# Copilot 桌寵與彩蛋修正說明

## 修正項目

- 桌寵批次生成頁的每張校系紙張預設為 `data-status="pending"`，載入時只顯示「等待小助手開始」中性提示，不再預先顯示失敗面板或失敗操作按鈕。
- 後端狀態輪詢只在收到 `status="failed"` 時顯示失敗面板；重試後會恢復 `pending`，完成與施法中仍由既有狀態控制。
- 桌寵角色區在角色上方預留至少頁首高度加 16px 的空間，並於手機寬度維持可用與可視。
- 彩蛋頒獎卡片改為頁首下方置中，且不再放在畫面底部；卡片可點擊關閉，3～4 秒後自動消失。
- 使用 `MutationObserver` 觀察 `.tour-invite` 的加入、按鈕移除及 DOM 移除；導覽邀請存在時頒獎卡片等待，邀請關閉或最長等待 8 秒後才顯示。每次只允許一張頒獎卡片。
- 修正區塊使用既有顏色與字級變數，並保留淺色、深色、375px 手機、`prefers-reduced-motion` 與 `.reduced-motion` 行為。

## 修改檔案

- `app/templates/student_autobiography_batch.html`
- `app/static/js/pet-batch.js`
- `app/static/css/design-system.css`
- `app/static/js/easter-eggs.js`
- `app/static/css/easter-eggs.css`
- `docs/05_交接與專案管理/Copilot_桌寵與彩蛋修正說明.md`

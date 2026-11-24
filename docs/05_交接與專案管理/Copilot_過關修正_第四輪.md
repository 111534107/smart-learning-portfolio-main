# Copilot 過關修正：第四輪

## 驗證範圍

依任務要求僅以 CSS 規則推算，沒有執行任何畫面檢查、測試或終端機指令。指定的失敗清單 `D:\democase\ai\logs\layout-check\ux8\report.md` 讀取遭拒，因此無法核對報告中的實際選擇器或逐尺寸畫面。以下各項均標記「未驗證」。

## 修正項目

1. **目標校系排行列，手機與平板、淺色與深色｜未驗證**  
   檔案：`app/static/css/design-system.css`。末段新增 `@media (max-width: 1099.98px)` 的 `.target-ranking__row`、`.map-school > summary`、`.map-program > summary`、`.target-program__summary` 規則，明確設定 `display: grid`、`height: auto !important`、`min-height: 44px !important`、`box-sizing: border-box` 和換行。預期連結或摘要整列不再受固定高度裁短，至少有 44px 高。

2. **我的資料表單欄位，手機與平板｜未驗證**  
   檔案：`app/static/css/design-system.css`。同一媒體查詢為學生端表單的一般 `input`、`select`、`textarea` 設 `box-sizing: border-box`、`height: auto !important`、`min-height: 44px !important`；排除 checkbox、radio、file、hidden、range。預期欄位至少 44px，且邊框盒不壓縮最小高度。

3. **畢業門檻卡片，平板｜未驗證**  
   檔案：`app/static/css/design-system.css`。末段 `.gd-block > summary` 規則明確解除固定高度，設定 `min-height: 44px !important` 並允許換行。預期可點摘要列連同內容至少 44px 高。

4. **寫自傳字級按鈕，手機與平板｜未驗證**  
   檔案：`app/static/css/design-system.css`。加強 `body[data-page="student-autobiography"] .font-switch button` 規則，設定 44px 寬、最小高 44px、`height: auto !important` 與置中。預期「A」字級按鈕觸控區至少 44×44px。

5. **寫自傳鍵盤開啟時的段落編輯與儲存，手機｜未驗證**  
   檔案：`app/static/css/student-v2/shell.css`。在 `max-width: 899px` 的打字狀態將頁首改為 `position: static`、將底部留白縮至安全區，並將段落 textarea 最大高度限制為 `min(8rem, 28dvh)`、內部可捲動。既有打字狀態規則隱藏底部導覽、並將段落工具列和 textarea 放回文件流。預期頁首不再覆蓋編輯區，短視窗中 textarea 和儲存列較容易同時保持可見。

6. **寫自傳長文字不裁切，電腦版淺色與深色｜未驗證**  
   檔案：`app/static/css/design-system.css`。末段對 `.canva-paragraph-header__title`、`.canva-preview-item__title`、`.canva-preview-item__text` 及紙面段落文字設定 `white-space: normal`、`overflow: visible`、`overflow-wrap: anywhere`、`text-overflow: clip`。CSS 原有 `.canva-paragraph-header__title` 曾以 `white-space: nowrap`、`overflow: hidden`、`text-overflow: ellipsis` 裁切；新增規則提高特異性並解除這些限制。預期長句可換行完整顯示。

7. **寫自傳深色模式段落標題、字數與上一段按鈕，所有尺寸｜未驗證**  
   檔案：`app/static/css/design-system.css`。末段深色規則指定 `.canva-paragraph-header`、`.canva-paragraph-nav`、段落標題／步驟、字數計數、導覽指示及按鈕使用 `--card` 背景和 `--ink` 文字。規則不選取 `.draft__paragraph`，預期工具列對比改善且白底黑字標楷體紙面保持原樣。

8. **學生首頁深色路線站點數字，所有尺寸｜未驗證**  
   檔案：`app/static/css/student-v2/home-desk.css`。末段新增深色主題高特異性規則，預設站點數字及圓點使用 `--ink`；僅 past／now 站點（底色為淺色年級色）改用深色 `#171411`。預期文字顏色依底色選擇，不再以同一顏色覆寫所有站點。

9. **實習履歷 1px 檔案輸入框，手機與平板、淺色與深色｜未驗證**  
   檔案：`app/static/css/student-v2/shell.css`。末段加強 `.rz-page input[type="file"]` 的 visually-hidden 規則，包含 `position: absolute`、1px 尺寸、`overflow: hidden`、`clip`／`clip-path`，並以 `!important` 避免較早的 `position: static` 規則使其顯示。預期輸入框不佔版面且仍可聚焦，不使用 `display: none`。

10. **實習履歷自傳輔助按鈕對比，平板淺色｜未驗證**  
    檔案：`app/static/css/design-system.css`。末段 `.rz-bio-assist__button` 改用 `--card` 背景、`--line` 邊框及 `--ink` 文字。預期在淺色卡片底上提高文字對比。

11. **導師工作清單文字與送審列，手機淺色與深色｜未驗證**  
    檔案：`app/static/css/design-system.css`。末段 `@media (max-width: 1099.98px)` 為 `.work-list > li` 和列內文字／標籤設至少 44px、取消固定高度並允許換行及 `overflow-wrap: anywhere`。預期校系名稱和送審文字不再被切斷，整列至少 44px。

12. **導師工作清單送審列，平板淺色與深色｜未驗證**  
    檔案：`app/static/css/design-system.css`。同第 11 項，列內 `.queue-badge` 等可點標籤亦設 `min-height: 44px`。預期平板上的「1 份送審」列／標籤高度至少 44px。

13. **寫自傳淺色字級按鈕，手機｜未驗證**  
    檔案：`app/static/css/design-system.css`。使用第 4 項的相同 `.font-switch button` 規則；預期淺色模式的字級按鈕觸控區至少 44×44px。

## 第四輪收斂追加（末段規則）

以下追加規則只修改指定的三個 CSS 檔，未執行檢查；各項仍標記「未驗證」。

1. **目標校系／畢業門檻／我的資料／字級與導師工作台**  
   檔案：`app/static/css/design-system.css`。末段 `[data-ui="student-v2"] :is(...)` 使用高特異性規則取消固定／最大高度，設定 `min-height: 44px !important`、邊框盒與換行；導師工作清單列及列內文字最低 44px。預期可點範圍與文字完整顯示；未驗證。

2. **實習履歷小助手對比與可點文字**  
   檔案：`app/static/css/design-system.css`。平板媒體查詢中將 `.rz-bio-assist`、`.rz-bio-assist__button` 設為 `var(--card)`／`var(--ink)`，並將內部狀態文字設為 `var(--ink)`。預期「請小助手依我勾選的資料生成自傳」達 4.5:1；未驗證。

3. **實習履歷檔案輸入框**  
   檔案：`app/static/css/student-v2/shell.css`、`app/static/css/student-v2/home-desk.css`。末段再覆寫 `input[type="file"]`，保持 `position: absolute`、1×1px、`overflow: hidden`、`clip`／`clip-path`、不使用 `display: none`。預期隱藏控制項不佔版面；未驗證。

4. **寫自傳鍵盤開啟、深色文字與長文字**  
   檔案：`app/static/css/student-v2/shell.css`。末段在 `max-width: 899px` 將打字狀態頁首與相關區塊改為 `position: static`，textarea 限制可視捲動高度；深色標題／字數／導覽使用 `--card` 與 `--ink`；長標題與預覽文字使用正常換行、可見 overflow 與 anywhere 換行。預期鍵盤開啟時仍可見編輯區與儲存列，長文字完整顯示；未驗證。

5. **學生首頁深色路線站點**  
   檔案：`app/static/css/student-v2/home-desk.css`。末段依站點底色覆寫數字與圓點的 `color`／`fill`：一般深底用 `var(--ink)`，淺底 past／now 或指定站點用 `#171411`。預期不以單一前景色覆蓋所有站點；未驗證。

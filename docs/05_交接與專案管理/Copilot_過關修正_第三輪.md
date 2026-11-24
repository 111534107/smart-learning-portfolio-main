# Copilot 過關修正第三輪

## 修改檔案

- `app/static/css/design-system.css`
- `app/static/css/student-v2/home-desk.css`
- `app/static/css/student-v2/shell.css`
- 本報告

## 修改項目與預期結果

1. **頁首與工具列**
   - 修改檔案：`design-system.css`、`shell.css`
   - 規則：第三輪覆寫在檔案末段，以 `min-height: 44px`、`height: auto`、`min-width: 44px` 及特定 `.masthead__tools` 選擇器處理頁首、帳號選單、主導覽、麵包屑與搜尋連結。
   - 預期結果：手機／平板主要頁首連結與工具按鈕實際高度至少 44px，不再被較早的固定高度限制。
   - 狀態：未驗證（無法執行畫面檢查）。

2. **學生首頁與各頁按鈕**
   - 修改檔案：`design-system.css`、`home-desk.css`、`shell.css`
   - 規則：第三輪覆寫 `.button`、`.button--small`、`.desk-actions`、`.desk-action-locked`、`.maker-row`、`.guide-card__actions`、`.rz-*` 等規則；設定 `min-height: 44px` 並取消小尺寸按鈕固定高度。
   - 預期結果：履歷、上傳、修改、儲存、校系探索、畢業門檻小卡等按鈕的實際高度至少 44px。
   - 狀態：未驗證（無法執行畫面檢查）。

3. **目標校系排行列**
   - 修改檔案：`design-system.css`、`shell.css`
   - 規則：第三輪覆寫 `.target-ranking__row`、`.target-program__summary`、`.map-school > summary`、`.map-program > summary`，設定 `min-height: 44px`、`height: auto`、`white-space: normal`、`overflow: visible`、`overflow-wrap: anywhere`。
   - 預期結果：40 個排行列與校系連結整列可點；長校名與校系名稱可換行。
   - 狀態：未驗證（無法執行畫面檢查）。

4. **導師工作台**
   - 修改檔案：`design-system.css`、`shell.css`
   - 規則：第三輪覆寫 `.class-filter select`、`.teacher-roster-filters select`、`map-school`／`map-program` summary 與名稱文字，實際下拉及列高度至少 44px；長文字允許換行。
   - 預期結果：「班級篩選」、「全部負責班級」、「資管科五甲」、「查看」與摘要按鈕至少 44px；校名及「1 份送審」不被裁切。
   - 狀態：未驗證（無法執行畫面檢查）。

5. **寫自傳手機打字模式**
   - 修改檔案：`design-system.css`、`shell.css`
   - 規則：第三輪覆寫 `.font-switch button` 至 44×44；在手機打字模式將 `.sv2-tabbar`、`.assistant__toggle`、`.tour-invite` 與底部 typing 元件收起；`.draft__paragraph`、textarea 保持 `position: static`。
   - 預期結果：「A」字級按鈕至少 44×44；406px 可視高度內 textarea 與儲存鈕可留在文件流中，底部導覽與小助手收起。
   - 狀態：未驗證（無法執行畫面檢查）。

6. **寫自傳電腦版標題換行**
   - 修改檔案：`design-system.css`
   - 規則：第三輪覆寫 `.draft__paragraph`、`.canva-paragraph-header__title`，設定 `white-space: normal`、`overflow: visible`、`overflow-wrap: anywhere`、`text-overflow: clip`。
   - 預期結果：「未來規劃：補強資料分析，成為懂需求的開發者」可完整換行、不裁切。
   - 狀態：未驗證（無法執行畫面檢查）。

7. **寫自傳深色外觀對比與紙張例外**
   - 修改檔案：`design-system.css`
   - 規則：第三輪覆寫深色 `.draft-paragraph-toolbar`、字數、段落標題與段落外文字使用 `var(--ink)`；`.draft__paragraph` 本體及標題、段落文字保留白底黑字例外，底色使用主題線條變數。
   - 預期結果：深色模式段落列表與控制文字有主題前景；紙張區塊仍為白底黑字。
   - 人工確認：紙張區塊、段落標題與字數的實際對比仍需畫面人工確認，屬未驗證項目。

8. **學生首頁深色路線站點數字**
   - 修改檔案：`home-desk.css`
   - 規則：第三輪覆寫深色站點 3、5、6 的 `.stop-node__count` 與 `.route-list__dot`，前景／填色使用 `#171411`。
   - 預期結果：「3」「5」「6」與淺色站點圓底有足夠對比。
   - 狀態：未驗證（無法執行畫面檢查）。

9. **實習履歷手機**
   - 修改檔案：`shell.css`、`home-desk.css`、`design-system.css`
   - 規則：第三輪覆寫可見檔案輸入框為 1px visually-hidden 樣式；`.info-tip__btn` 改為實際 44×44；打字模式 textarea 保持 static，隱藏側欄並保留 `.rz-mobile-save`。
   - 預期結果：不再有可見 1px input；`?` 說明按鈕至少 44×44；鍵盤開著時儲存草稿與文字欄可見。
   - 狀態：未驗證（無法執行畫面檢查）。

10. **我的資料手機**
   - 修改檔案：`shell.css`、`design-system.css`
   - 規則：第三輪覆寫 `label[for]` 至少 44px 高；目標相容表單輸入框保持 44px。
   - 預期結果：檢查器以 label 包覆層計算時可達 44px 高。
   - 狀態：未驗證（無法執行畫面檢查）。

## 整體驗證狀態

- 未執行終端機指令、未執行畫面檢查、未執行測試。
- 上一輪 `D:\democase\ai\logs\layout-check\ux7\report.md` 因工作區工具權限拒絕讀取，未能逐項對照原失敗清單；上述項目依任務清單與 CSS 靜態推算完成。

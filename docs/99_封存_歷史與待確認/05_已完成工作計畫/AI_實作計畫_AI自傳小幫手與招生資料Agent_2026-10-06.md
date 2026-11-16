# 實作計畫：AI 自傳小幫手＋招生資料 Agent（第二、三階段）

> 日期：2026-10-06
> 使用者決定：兩個一起做；AI 用 Google Gemini；自傳採「先問幾題再寫」。
> 分支：`feat/main-line-2`

## 一、共用：AI 連線（`app/services/gemini_client.py`）

- 只用 Python 內建的 `urllib` 呼叫 Gemini REST API，**不安裝新套件**，組員較好讀。
- 設定沿用 `.env`：`AI_ENABLED`、`AI_PROVIDER=gemini`、`AI_API_KEY`，新增 `GEMINI_MODEL`（預設 `gemini-2.5-flash`）。金鑰只放 `.env`，不 commit。
- 一律要求 Gemini 回傳固定格式 JSON（`responseSchema`），程式再檢查一次格式。
- 沒有金鑰時：
  - 自傳改用「示範草稿」，並清楚標示「尚未接上 AI」。
  - Agent 擷取直接告知「尚未設定金鑰」。招生資料不能用假的，以免誤導學生。

## 二、AI 自傳小幫手

流程：選目標校系 → 回答 4 題 → AI 依「回答＋六類資料＋該校系加權」寫 4 段草稿 → 學生逐段修改並儲存 → 備審 Word 的「自傳」章節自動放入。

| 題目 | 用途 |
| --- | --- |
| 為什麼想繼續讀資管／這個系？ | 動機段 |
| 五年中最有成就感的一件事，你做了什麼？ | 具體經驗段 |
| 遇過最大的困難，你怎麼解決？ | 成長段 |
| 二技想學什麼、之後想做什麼？ | 未來規劃段 |

防止 AI 亂寫：

- 系統把學生資料整理成編號事實（F1、F2…），AI 只能引用這些事實與學生的回答，不得編造獎項、分數或經歷。
- 每段都要列出引用的事實編號，畫面上以「依據」標籤顯示。系統會濾掉不存在的編號。
- 草稿存在既有的 `learning_profile_outputs` 資料表（`output_type="autobiography_ai"`），**不需要 migration**。

路由：`GET /student/autobiography`、`POST /student/autobiography/generate`、`POST /student/autobiography/<id>/save`。入口放在缺件比對頁的「自傳」章節，導師的學生頁可以看到草稿。

## 三、招生資料 Agent（亮點第二、三階段）

- **第二階段（偵測更新）**：管理者登記官方來源（網址或上傳簡章 PDF）。Agent 下載後計算內容雜湊（sha256），和上次比對；內容有變就建立「變更」通知管理者。
  - 每次執行都記錄在 `agent_tasks`。
  - 可以在管理頁按「立即檢查」，也可以用排程執行 `flask agent-check`（Windows 工作排程器，每月一次）。
- **第三階段（擷取加權）**：管理者在變更上按「擷取加權」。Agent 把簡章交給 Gemini，擷取資管相關校系的項目與加權，建立 `status=candidate`、`data_origin=agent` 的校系版本；同時建議項目對應的資料類別，對應狀態一律設為「待確認」。
  - 管理者在「校系資料」頁看到和前一年正式版的差異，核准後學生才看得到。
- 使用既有的 `public_sources`、`public_source_snapshots`、`public_source_changes`、`agent_tasks` 資料表，**不需要 migration**。檔案存在 `instance/agent-sources/<雜湊>.<副檔名>`。
- 安全：只接受 `http`／`https` 網址；只有管理者能操作；連線逾時 30 秒；User-Agent 標明專題用途。不抓學校的學生系統。

## 四、測試

- 所有 AI 與網路呼叫都可以注入替身函式，測試不連網路、不需要金鑰。
- 自傳：
  - 沒有目標校系時引導先選校系。
  - 產生草稿時濾掉不存在的事實編號。
  - 只能看和改自己的草稿。
  - Word 會放入草稿。
- Agent：
  - 第一次抓取會建立變更；內容相同不建立，內容改變會建立。
  - 只接受 http／https 網址。
  - 擷取會建立候選版本，學生看不到。
  - 沒有金鑰時給中文說明。
  - 非管理者回 403。

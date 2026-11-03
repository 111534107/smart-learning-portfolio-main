# 學校 Google 一鍵登入：設定步驟

> 來源：組員 111534107 的 `smart-learning-portfolio-main` 提交 `3187cb5`（2026-11-02），2026-11-03 由 Claude 整合進本專案。

## 做什麼

- 學生用學校帳號 `學號@stu.ukn.edu.tw` 登入**已經存在**的學生帳號；不會自動建立任何帳號。
- 只限學生、只限 `stu.ukn.edu.tw` 網域、信箱要經 Google 驗證、帳號要是啟用中。
- 第一次登入後記下 Google 帳號的固定編號（`users.google_sub`），之後用這個編號認人；管理員改綁信箱時會清掉，要重新登入綁定。
- 登入時用 Google 官方套件 `google-auth` 驗證身分憑證；權限只要 `openid email profile`，不碰雲端硬碟。
- 登入後顯示名稱會換成 Google 上的姓名（會寫進資料庫）。

## 設定

1. Google Cloud Console → 「API 和服務」→「憑證」→ 本專案現有的 OAuth 用戶端（和 Google 文件共用）→「已授權的重新導向 URI」新增：
   `http://localhost:5013/auth/google/callback`
   主機名稱要用 `localhost`，和 Google 文件的回呼網址一致，不要混用 `127.0.0.1`。
2. `.env` 加上：`GOOGLE_LOGIN_REDIRECT_URI=http://localhost:5013/auth/google/callback`（用戶端 ID 與密鑰沿用既有的 `GOOGLE_OAUTH_CLIENT_ID`、`GOOGLE_OAUTH_CLIENT_SECRET`）。
3. 重新啟動系統，登入頁才會出現「使用學校 Google 帳號登入」。
4. 管理員到「帳號管理」，在學生那一列填學號（系統自動補 `@stu.ukn.edu.tw`）並儲存；學號必須和該學生的學號相同。

## 本機驗收（展示站）

```text
D:\democase\ai\.venv\Scripts\python.exe scripts\run_local_demo.py --student-no 你的學號
```

`--student-no` 只把記憶體裡合成學生 `student_demo` 的學號換掉，讓管理員可以綁定本人的學校信箱；服務停止後就消失。
流程：`admin_demo` 登入 → 帳號管理綁定 → 登出 → 學生按學校 Google 登入（本人操作）。
學校的 Google Workspace 若封鎖外部應用程式，Google 會顯示已封鎖，需請學校資訊單位允許。

## 安裝了什麼

| 項目 | 位置 | 來源 |
| --- | --- | --- |
| `google-auth[requests]==2.62.0`（連帶安裝 `cryptography`、`cffi`、`pycparser`、`pyasn1`、`pyasn1-modules`） | `D:\democase\ai\.venv` | PyPI 官方 |
| 資料表欄位 `users.google_sub` | 資料庫（遷移 `b20261102e01`） | 本專案 |

## 如何移除

1. `.env` 刪掉 `GOOGLE_LOGIN_REDIRECT_URI`，登入頁的按鈕就會消失（功能關閉）。
2. Google Cloud Console 的「已授權的重新導向 URI」刪掉 `/auth/google/callback` 那一行。
3. 移除套件：`D:\democase\ai\.venv\Scripts\python.exe -m pip uninstall google-auth pyasn1-modules pyasn1`（`cryptography`、`cffi`、`pycparser` 若其他套件沒有用到也可一併移除，移除前先用 `pip show cryptography` 看 Required-by）。
4. 學生到 <https://myaccount.google.com/permissions> 移除本系統的存取權。

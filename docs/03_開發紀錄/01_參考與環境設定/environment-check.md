# 開發環境檢查報告

日期：2026-09-29（本次環境補充）

## 結論

目前專案已具備基本 Flask 開發條件，可以進入下一步功能開發。

本次補充：已建立個人完整備份專案 `D:\democase\ai-personal-backup-2026-09-29`，並完成 `docs` 文件庫的現行／封存分類。團隊協作線與個人完整線尚未直接建立 Git worktree，需在目前未提交變更完成基準快照後再建立。

已確認：

- Python 可用。
- 專案 `.venv` 已存在。
- `.venv` 內 Flask、python-dotenv、SQLAlchemy、PyMySQL 已安裝。
- Flask app 可正常載入。
- 首頁 `/` 回應 200。
- 管理者頁 `/admin` 回應 200。
- pytest 已修正並通過。
- Git 已安裝。
- Node.js 已安裝。
- npm 已安裝，但 PowerShell 直接執行會被執行原則擋住。
- Mermaid CLI 已安裝，可由完整路徑執行 `C:\Users\lisa2\AppData\Roaming\npm\mmdc.cmd`。

尚需處理：

- MySQL CLI 尚未加入 PATH，或尚未安裝 MySQL Client。
- 目前資料庫連線尚未實測，因為專案還沒有正式初始化資料表。
- 專案目前位於 Git `main` 分支，但工作區有未提交變更；建立協作分支前必須先做基準快照。

## 實際檢查結果

### Python

```text
Python 3.13.15
```

### pip

```text
pip 26.2.1
```

### 專案虛擬環境

```text
.venv 存在
.venv Python 版本：Python 3.13.15
```

### Flask 載入

```text
Flask app 載入成功
已註冊路由：
- /
- /admin
- /static/<path:filename>
```

### 測試結果

```text
1 passed
```

### Git

```text
git version 2.55.0.windows.3
```

### Node.js

```text
v24.19.0
```

### npm

PowerShell 直接執行：

```text
npm.ps1 未經數位簽署，遭 PowerShell 執行原則阻擋
```

可用替代方式：

```powershell
cmd /c npm --version
```

檢查結果：

```text
11.13.0
```

### Mermaid CLI

```text
mmdc 12.0.0
位置：C:\Users\lisa2\AppData\Roaming\npm\mmdc.cmd
注意：目前 PowerShell PATH 未包含 Node.js 與 npm 全域執行檔路徑。
```

### MySQL

```text
mysql 指令找不到
```

可能原因：

- 尚未安裝 MySQL。
- 已安裝 MySQL，但 `mysql.exe` 沒有加入 PATH。
- 只安裝資料庫服務，沒有安裝 MySQL Client。

## 已修正項目

新增 `pytest.ini`：

```ini
[pytest]
pythonpath = .
cache_dir = logs/.pytest_cache
testpaths = tests
```

目的：

- 讓 pytest 找得到 `app` 模組。
- 將 pytest 快取放到 `logs/.pytest_cache`，避免根目錄權限問題。

## 建議下一步

### 1. 每次開發前啟動虛擬環境

```powershell
cd D:\democase\ai
.\.venv\Scripts\Activate.ps1
```

看到命令列前面出現 `(.venv)` 才代表成功。

### 2. 啟動 Flask

```powershell
python run.py
```

打開：

```text
http://127.0.0.1:5000
http://127.0.0.1:5000/admin
```

### 3. 跑測試

```powershell
pytest -q
```

或不用啟動虛擬環境也可以：

```powershell
.\.venv\Scripts\pytest.exe -q
```

### 4. npm 的使用方式

目前 PowerShell 會擋 `npm.ps1`，所以先用：

```powershell
cmd /c npm --version
```

如果未來要用 npm 安裝前端套件，可以用：

```powershell
cmd /c npm install
```

### 5. Git 分支／備份

建議執行：

```powershell
先確認 `git status`，不可用 reset 或 checkout 清除既有變更。整合前使用 `D:\democase\ai-personal-backup-2026-09-29` 或新的快照目錄保存完整專案，再建立團隊 worktree。
```

### 6. MySQL 處理

請先確認你電腦是否已安裝 MySQL Workbench 或 MySQL Server。

如果有安裝但 `mysql` 指令找不到，需要把 MySQL 的 `bin` 資料夾加入 PATH，例如：

```text
C:\Program Files\MySQL\MySQL Server 8.0\bin
```

如果還沒安裝，可以先用 MySQL Installer 安裝：

- MySQL Server
- MySQL Workbench
- MySQL Shell 或 Command Line Client

## 對程式小白的開發建議

每次開發照這個固定流程：

1. 開 Antigravity IDE。
2. 開資料夾 `D:\democase\ai`。
3. 啟動 `.venv`。
4. 跑 `pytest -q` 確認目前是好的。
5. 改一小段功能。
6. 再跑 `pytest -q`。
7. 把今天做的事寫進 `docs/development-log.md`。
8. 如果成功，再 commit。

這樣報告時你比較不會慌，因為每一步都有紀錄，也能證明系統是逐步開發出來的。

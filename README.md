# 資管科智慧學習歷程系統

這是使用 Flask + MySQL 開發的學習歷程管理系統，搭配 Antigravity IDE 與 BMAD AI Agent 協助規劃、切分故事與開發。

## 開發環境

建議工具：

- Python 3.11+
- MySQL 或 MariaDB
- Antigravity IDE
- BMAD
- Git

## 一鍵啟動（組員請用這個）

先安裝 Python、XAMPP、Git，clone 後點兩下 `create_desktop_shortcut.bat` 建立桌面捷徑，之後點桌面的「資管科學習歷程」就會啟動 MySQL、建好資料庫並開啟 `http://127.0.0.1:5013`。

詳細步驟與常見問題：[docs/05_交接與專案管理/組員開啟說明.md](docs/05_交接與專案管理/組員開啟說明.md)；完整手冊：[docs/05_交接與專案管理/系統啟動手冊.md](docs/05_交接與專案管理/系統啟動手冊.md)

## 手動設定

```powershell
cd D:\democase\ai
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python run.py
```

## BMAD 建議流程

```text
CP  Create PRD
CA  Create Architecture
CE  Create Epics and Stories
IR  Check Implementation Readiness
SP  Sprint Planning
CS  Create Story
DS  Dev Story
CR  Code Review
```

## 文件位置

- `docs/01_正式規格/資管科智慧學習歷程系統-系統規格設計書-開發閱讀版.md`（主要系統規格書）
- `docs/README.md`（文件總索引）
- `docs/04_圖表與介面/03_檢查與圖表規範/diagrams.md`（Mermaid 圖表庫）
- `docs/04_圖表與介面/03_檢查與圖表規範/diagram-style-guide.md`（圖表繪製指南）
- `docs/03_開發紀錄/01_參考與環境設定/mysql-setup.md`（MySQL 設定說明）
- `docs/03_開發紀錄/development-log.md`（開發日誌）

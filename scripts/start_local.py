"""一鍵啟動用：準備 .env 與 MySQL 資料庫，再啟動 Flask 並開瀏覽器。

由專案根目錄的 start_system.bat 呼叫（那時 MySQL 已啟動、venv 已裝好），也可以自己執行：
    .venv\\Scripts\\python.exe scripts\\start_local.py
步驟：
1. .env 裡還是範例值的 SECRET_KEY、DB_PASSWORD 換成隨機值（只寫進自己的 .env，不會提交）。
2. 用 MySQL root 建立資料庫與專案帳號（XAMPP 預設 root 沒有密碼；有設密碼就在 .env 加 MYSQL_ROOT_PASSWORD）。
3. 空資料庫：依目前的 Model 建表、把遷移版本標到最新、建立 admin；已有資料表：執行資料庫遷移。
4. 在 APP_PORT（預設 5013）啟動系統，伺服器接受連線後自動開瀏覽器。
"""

import os
import secrets
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# 一般用專案自己的 .env；想沿用別處已設定好的 .env（例如另一個資料夾），設 SLP_ENV_FILE 指過去，不必複製金鑰
ENV_FILE = Path(os.getenv("SLP_ENV_FILE") or PROJECT_ROOT / ".env")
PLACEHOLDERS = {
    "SECRET_KEY": "change-this-in-production",
    "DB_PASSWORD": "change-this-password",
}


def fail(message):
    print(f"\n[錯誤] {message}")
    sys.exit(1)


def fill_placeholder_secrets():
    """把 .env 中仍是範例值的金鑰換成隨機值，其他行原樣保留。"""
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    changed = []
    for index, line in enumerate(lines):
        key, sep, value = line.partition("=")
        if sep and PLACEHOLDERS.get(key.strip()) == value.strip():
            lines[index] = f"{key.strip()}={secrets.token_urlsafe(24)}"
            changed.append(key.strip())
    if changed:
        ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"已在 .env 產生隨機值：{', '.join(changed)}")


def ensure_database(config):
    """用 root 建資料庫與專案帳號；專案帳號已能登入就不動。"""
    import pymysql

    port = int(config.DB_PORT)
    try:
        pymysql.connect(host=config.DB_HOST, port=port, user=config.DB_USER,
                        password=config.DB_PASSWORD, database=config.DB_NAME,
                        connect_timeout=5).close()
        return
    except pymysql.err.OperationalError:
        pass

    try:
        root = pymysql.connect(host=config.DB_HOST, port=port, user="root",
                               password=os.getenv("MYSQL_ROOT_PASSWORD", ""), connect_timeout=5)
    except pymysql.err.OperationalError as error:
        fail(f"無法用 root 連上 MySQL（{config.DB_HOST}:{port}）：{error}\n"
             "若 root 有設密碼，請在 .env 加一行 MYSQL_ROOT_PASSWORD=你的密碼 後重新執行。")

    with root.cursor() as cursor:
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{config.DB_NAME}` "
                       "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cursor.execute("SELECT COUNT(*) FROM mysql.user WHERE user = %s", (config.DB_USER,))
        user_exists = cursor.fetchone()[0] > 0
        if user_exists and config.DB_USER != "root":
            # 帳號已存在但密碼不符時不擅自改密碼，避免弄壞同一台電腦上其他設定
            root.close()
            fail(f"MySQL 已有帳號 {config.DB_USER}，但 .env 的 DB_PASSWORD 登入失敗。\n"
                 "請把該帳號的正確密碼填進 .env 的 DB_PASSWORD，或在 .env 改用另一個 DB_USER 名稱。")
        for host in ("localhost", "127.0.0.1"):
            cursor.execute("CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s",
                           (config.DB_USER, host, config.DB_PASSWORD))
            cursor.execute(f"GRANT ALL PRIVILEGES ON `{config.DB_NAME}`.* TO %s@%s",
                           (config.DB_USER, host))
        cursor.execute("FLUSH PRIVILEGES")
    root.commit()
    root.close()
    print(f"已建立資料庫 {config.DB_NAME} 與帳號 {config.DB_USER}")


def prepare_schema(app):
    from flask_migrate import stamp, upgrade
    from sqlalchemy import inspect

    from app.extensions import db
    from scripts.init_db import create_admin_user

    migrations = str(PROJECT_ROOT / "migrations")
    with app.app_context():
        tables = set(inspect(db.engine).get_table_names())
        if not tables:
            # 第一個遷移是建在既有資料表上，空資料庫要先依 Model 建表再把版本標到最新
            db.create_all()
            stamp(directory=migrations)
            print("已建立資料表，遷移版本標為最新")
        elif "alembic_version" in tables:
            upgrade(directory=migrations)
            print("資料庫遷移已更新到最新")
        else:
            print("[注意] 資料庫已有資料表但沒有遷移紀錄，略過遷移；若畫面出錯請改用新的 DB_NAME。")
        print(create_admin_user())


def port_in_use(port):
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def open_browser_when_ready(url, port):
    for _ in range(60):
        if port_in_use(port):
            webbrowser.open(url)
            return
        time.sleep(0.5)


def main():
    os.chdir(PROJECT_ROOT)
    sys.path.insert(0, str(PROJECT_ROOT))
    if not ENV_FILE.exists():
        fail("找不到 .env，請先執行 start_system.bat（會從 .env.example 複製）。")
    # 借用別處的 .env 時只讀不寫：那份設定的密碼可能正被 MySQL 使用，改掉就登不進去（10-27 實際發生過）
    if not os.getenv("SLP_ENV_FILE"):
        fill_placeholder_secrets()

    from dotenv import load_dotenv

    load_dotenv(ENV_FILE, override=False)
    # 正式版不能停在假辨識：.env 沒設或設成 fake 時，這次啟動改用本機 RapidOCR（只改這個行程，不寫回 .env）
    from real_ocr import real_ocr_provider

    os.environ["DOCUMENT_ANALYSIS_PROVIDER"] = real_ocr_provider(os.getenv("DOCUMENT_ANALYSIS_PROVIDER", ""))
    print(f"OCR 模式：{os.environ['DOCUMENT_ANALYSIS_PROVIDER']}")
    from app.config import Config

    port = int(os.getenv("APP_PORT", "5013"))
    url = f"http://127.0.0.1:{port}"
    if port_in_use(port):
        fail(f"{port} 埠已被其他程式使用（可能系統已經開著）。\n"
             f"可直接打開 {url}，或關掉占用的程式；也可以在 .env 加 APP_PORT=其他埠號。")

    ensure_database(Config)

    from app import create_app

    app = create_app()
    prepare_schema(app)

    print(f"\n系統網址：{url}")
    print("關閉這個視窗即停止系統（MySQL 會繼續在背景執行）。\n")
    if os.getenv("NO_BROWSER") != "1":
        threading.Thread(target=open_browser_when_ready, args=(url, port), daemon=True).start()
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()

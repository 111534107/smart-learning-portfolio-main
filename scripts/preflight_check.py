"""正式主機上線前的唯讀檢查（2026-11-12）。

只讀不寫：
1. `.env` 必要項目有沒有設定——只說「有／沒有／像範例值」，絕不印出值。
2. 資料庫目前的遷移版本是不是最新 head（只執行 SELECT）。

用法（在專案根目錄）：
    python scripts/preflight_check.py              # 讀 ./.env
    python scripts/preflight_check.py --env D:/path/.env
    python scripts/preflight_check.py --skip-db    # 只檢查 .env

結束代碼：0＝全部通過；1＝有必要項目缺少或資料庫不是最新；2＝無法檢查（例如連不上資料庫）。
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 必要：沒有就不能上線
REQUIRED = {
    "SECRET_KEY": "Flask 工作階段簽章；正式環境沒設會直接拒絕啟動",
    "FLASK_ENV": "正式主機設 production",
    "DB_HOST": "MySQL 主機",
    "DB_PORT": "MySQL 連接埠",
    "DB_NAME": "資料庫名稱",
    "DB_USER": "資料庫帳號",
    "DB_PASSWORD": "資料庫密碼",
    "TWO_FACTOR_KEY": "加密 Authenticator 金鑰；沒設會由 SECRET_KEY 推導，換 SECRET_KEY 後全部人要重設雙重驗證",
}

# 建議：依啟用的功能而定，沒設只提醒
RECOMMENDED = {
    "ADMIN_DEFAULT_PASSWORD": "第一個管理員的初始密碼（建好後應立即改掉）",
    "UPLOAD_FOLDER": "上傳檔案存放位置",
    "AI_ENABLED": "是否啟用 AI",
    "AI_PROVIDER": "AI 預設供應商（實際順序可在管理員 AI 設定頁調）",
    "AI_API_KEY": "Gemini 金鑰（AI_PROVIDER=gemini 時）",
    "OPENAI_API_KEY": "OpenAI 金鑰（AI 設定頁有選 OpenAI 時）",
    "ANTHROPIC_API_KEY": "Claude 金鑰（AI 設定頁有選 Claude 時）",
    "OLLAMA_URL": "本機 Ollama 位址（AI 設定頁有選 Ollama 時）",
    "GOOGLE_OAUTH_CLIENT_ID": "Google 文件／登入用 OAuth 用戶端",
    "GOOGLE_OAUTH_CLIENT_SECRET": "Google OAuth 用戶端密鑰",
    "GOOGLE_OAUTH_REDIRECT_URI": "Google 文件授權回呼網址（要改成正式網域）",
    "GOOGLE_LOGIN_REDIRECT_URI": "學校 Google 一鍵登入回呼網址（要改成正式網域）",
    "GOOGLE_STORAGE_REDIRECT_URI": "Google 雲端硬碟存放回呼網址（STORAGE_BACKEND=google 時）",
    "STORAGE_BACKEND": "檔案存放：local 或 google",
    "TWO_FACTOR_ISSUER": "Authenticator 顯示的名稱",
    "SMTP_HOST": "寄信主機（電子郵件通知；變數名稱以 feat/email-notify 定案為準）",
    "SMTP_PORT": "寄信連接埠（同上）",
    "SMTP_USER": "寄信帳號（同上）",
    "SMTP_PASSWORD": "寄信密碼（同上）",
    "MAIL_FROM": "寄件人（同上）",
}

PLACEHOLDER_HINTS = ("change-me", "changeme", "your-", "your_", "xxx", "example", "dev-secret-key", "<", "請填")


def read_env(path):
    values = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
    return values


def describe(value):
    if value is None:
        return "沒有"
    if value == "":
        return "空白"
    if any(hint in value.lower() for hint in PLACEHOLDER_HINTS):
        return "像範例值"
    return "有"


def check_env(env):
    print("== .env 必要項目")
    failed = False
    for key, note in REQUIRED.items():
        state = describe(env.get(key))
        ok = state == "有"
        if key == "FLASK_ENV" and ok and env.get(key) != "production":
            state, ok = "有，但不是 production", False
        failed |= not ok
        print(f"  [{'OK' if ok else '缺'}] {key}: {state}　— {note}")
    print("== .env 建議項目（依啟用的功能決定要不要填）")
    for key, note in RECOMMENDED.items():
        state = describe(env.get(key))
        print(f"  [{'OK' if state == '有' else '--'}] {key}: {state}　— {note}")
    return failed


def migration_heads():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return set(ScriptDirectory.from_config(cfg).get_heads())


def current_db_versions(env):
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import URL

    url = URL.create(
        "mysql+pymysql",
        username=env.get("DB_USER", "root"),
        password=env.get("DB_PASSWORD", ""),
        host=env.get("DB_HOST", "127.0.0.1"),
        port=int(env.get("DB_PORT", "3306") or 3306),
        database=env.get("DB_NAME", "smart_learning_portfolio"),
    )
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return {row[0] for row in conn.execute(text("SELECT version_num FROM alembic_version"))}
    finally:
        engine.dispose()


def check_db(env):
    print("== 資料庫遷移版本")
    heads = migration_heads()
    print(f"  程式裡的最新 head：{', '.join(sorted(heads))}")
    if len(heads) > 1:
        print("  [缺] 遷移有多個 head，合併分支時 down_revision 沒接好，先修再上線")
        return True
    try:
        current = current_db_versions(env)
    except Exception as exc:  # 連不上就回報，不重試、不建表
        print(f"  [??] 無法讀取資料庫版本：{type(exc).__name__}（檢查 DB_* 設定與 MySQL 是否啟動）")
        return None
    print(f"  資料庫目前版本：{', '.join(sorted(current)) or '（空，從未遷移）'}")
    if current == heads:
        print("  [OK] 已是最新")
        return False
    print("  [缺] 不是最新，請先備份資料庫再執行：flask db upgrade")
    return True


def main():
    parser = argparse.ArgumentParser(description="上線前唯讀檢查")
    parser.add_argument("--env", default=os.environ.get("SLP_ENV_FILE") or str(ROOT / ".env"))
    parser.add_argument("--skip-db", action="store_true")
    args = parser.parse_args()

    env_path = Path(args.env)
    if not env_path.exists():
        print(f"找不到 .env：{env_path}")
        return 2
    env = read_env(env_path)
    print(f"檢查檔案：{env_path}（只顯示有沒有設定，不顯示值）")
    env_failed = check_env(env)
    db_failed = False if args.skip_db else check_db(env)
    if db_failed is None:
        return 2
    print("== 結果：" + ("有項目要處理" if env_failed or db_failed else "全部通過"))
    return 1 if env_failed or db_failed else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

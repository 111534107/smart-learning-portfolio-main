"""給外網看的展示站（透過 Cloudflare 臨時通道）。

和 run_demo.py 一樣是 SQLite 假資料，差別：
- 先把 .env 裡的 AI 金鑰、Google 金鑰清成空的（load_dotenv 不會覆蓋已存在的環境變數），
  外面的人登入後也不會用到我們的 AI 額度或 Google 帳號。
- 只聽本機 127.0.0.1，外面的人只能從通道進來。
用法：python scripts/run_public_demo.py  （埠號預設 5097，可用 DEMO_PORT 改）
"""
import os
import runpy
from pathlib import Path

BLANK = [
    "AI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_API_KEY",
    "GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_PICKER_API_KEY", "GOOGLE_CLOUD_PROJECT_NUMBER",
    "GOOGLE_OAUTH_REDIRECT_URI", "GOOGLE_STORAGE_REDIRECT_URI", "GOOGLE_LOGIN_REDIRECT_URI",
]
for key in BLANK:
    os.environ[key] = ""
os.environ.setdefault("DEMO_PORT", "5097")
os.environ["TWO_FACTOR_REQUIRED"] = "false"

runpy.run_path(str(Path(__file__).with_name("run_demo.py")), run_name="__main__")

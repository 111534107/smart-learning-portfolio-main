"""學生主線動線：做完一件事回到出發的頁面，並告訴學生哪裡更新了。

例：在「臺中科大資管系」的備審頁按「去新增」上傳成績單，確認後回到這個校系頁，
顯示「已儲存 3 門課程。準備度 20% → 45%」，不用自己再找路回去。
"""
import re
from urllib.parse import urlsplit

from flask import flash

from app.extensions import db

_TARGET_PAGE = re.compile(r"^/student/targets/(\d+)(?:[/?#]|$)")


def safe_next(value):
    """只接受站內路徑（/ 開頭），避免被拿來跳轉到外部網站；不合格回傳 None。"""
    value = (value or "").strip()
    if not value.startswith("/") or value.startswith("//") or "\\" in value:
        return None
    parts = urlsplit(value)
    return None if parts.scheme or parts.netloc else value


def target_program(next_path):
    """出發頁若是某個目標校系的備審頁，回傳該校系；否則回傳 None。"""
    from app.models import AdmissionProgram

    match = _TARGET_PAGE.match(next_path or "")
    return db.session.get(AdmissionProgram, int(match[1])) if match else None


def readiness(user, program):
    from app.services.gap_service import analyze_gap

    return analyze_gap(user, program)["readiness"] if program else None


def flash_done(message, user, program, before):
    """顯示完成訊息；回到校系頁時附上準備度前後變化。"""
    after = readiness(user, program)
    if program is not None and after is not None:
        message += f"準備度 {before or 0}% → {after}%"
    flash(message)

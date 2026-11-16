"""教務處畢業檢核日期與倒數（管理員設定；只提醒）。

教務處每學年兩次請學生填畢業資格自評表：第一次在專四下、第二次在專五上（期末考前兩週）。
管理員填本學年的兩個日期；學生頁、導師頁顯示還有幾天。沒填日期時只顯示文字說明。
「模擬今天」沿用 graduation_check_today，給展示站模擬專四下等情境。
"""

from datetime import date

from app.extensions import db
from app.models import SystemSetting
from app.services import audit_service
from app.services import graduation_check_service as check

FIRST_KEY = "graduation_check_first_date"
SECOND_KEY = "graduation_check_second_date"
KEYS = {"first": FIRST_KEY, "second": SECOND_KEY, "today": check.TODAY_SETTING_KEY}
LABELS = {"first": "第一次檢核（專四下）", "second": "第二次檢核（專五上）"}


def _parse(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def dates():
    rows = {row.key: row.value for row in SystemSetting.query.filter(SystemSetting.key.in_(KEYS.values())).all()}
    return {name: _parse(rows.get(key)) for name, key in KEYS.items()}


def save(actor, form):
    """存三個日期；空白代表清除。格式錯誤丟 ValueError（中文訊息）。"""
    new = {}
    for name, key in KEYS.items():
        raw = (form.get(name) or "").strip()
        if raw and _parse(raw) is None:
            raise ValueError("日期格式要像 2027-06-07。")
        new[name] = raw
    previous = {name: (value.isoformat() if value else "") for name, value in dates().items()}
    for name, key in KEYS.items():
        row = SystemSetting.query.filter_by(key=key).first()
        if new[name]:
            if row:
                row.value, row.updated_by_id = new[name], actor.id
            else:
                db.session.add(SystemSetting(key=key, value=new[name], updated_by_id=actor.id))
        elif row:
            db.session.delete(row)
    audit_service.record(actor, "graduation.check_dates", "system_setting", None,
                         {"from": previous, "to": new})
    db.session.commit()


def countdown(stage, today=None):
    """這位學生下一次檢核的倒數：專四（上、下）看第一次，專五上看第二次；其他回傳 None。"""
    grade, semester = stage.get("grade"), stage.get("semester")
    if grade == 4:
        name = "first"
    elif grade == 5 and semester == "上":
        name = "second"
    else:
        return None
    today = check.check_today() if today is None else today
    when = dates()[name]
    if when is None:
        return {"label": LABELS[name], "date": None, "days": None, "text": f"{LABELS[name]}：日期還沒公布。"}
    days = (when - today).days
    if days > 0:
        text = f"{LABELS[name]}：{when.isoformat()}，還有 {days} 天。"
    elif days == 0:
        text = f"{LABELS[name]}：就是今天（{when.isoformat()}）。"
    else:
        text = f"{LABELS[name]}：{when.isoformat()} 已經過了，請向教務處確認結果。"
    return {"label": LABELS[name], "date": when, "days": days, "text": text}

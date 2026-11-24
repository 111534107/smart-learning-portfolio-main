"""科辦角色判斷集中在這一個檔（2026-11-18 指導老師：科主任與科助是各自獨立的使用者）。

目前登入角色仍是 `User.role == "staff"`，用 `job_title` 區分；之後若要拆成兩種登入角色，
只改這個檔與帳號建立，不必再到各路由找職稱字串。
- 科主任：職稱「主任」或「副主任」。
- 科助：職稱「科助」。
- 其他行政人員：職稱自填，權限同科助以下（不能核准、不能指派班級）。
"""

CHIEF_TITLES = ("主任", "副主任")
ASSISTANT_TITLES = ("科助",)


def is_staff(user):
    return bool(user) and user.role == "staff"


def is_chief(user):
    """科主任（含副主任）。"""
    return is_staff(user) and (user.job_title or "") in CHIEF_TITLES


def is_assistant(user):
    return is_staff(user) and (user.job_title or "") in ASSISTANT_TITLES


def staff_label(user):
    """畫面上的稱呼：科主任（副主任標明）、科助、其他職稱照原樣。"""
    title = (user.job_title or "") if user else ""
    if title == "主任":
        return "科主任"
    if title == "副主任":
        return "科主任（副主任）"
    return title or "科辦"

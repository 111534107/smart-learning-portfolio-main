"""送外部 AI 前的去識別化（V2 第 6、8 頁：只傳去識別化的最小必要資料）。

兩層：
1. 已知的個資值（姓名、學號、帳號、電子郵件）直接換成代號。
2. 看起來像個資的格式：身分證／居留證號、手機、電子郵件、8～10 位數的編號（學號、證書號碼）。
一般的分數、學分、學年度（1～4 位數）不會被換掉。
"""
import re

_PATTERNS = (
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[電子郵件]"),
    (re.compile(r"(?<![A-Za-z0-9])[A-Z][1289]\d{8}(?!\d)"), "[證號]"),  # 身分證、新式居留證
    (re.compile(r"(?<![A-Za-z0-9])[A-Z]{2}\d{8}(?!\d)"), "[證號]"),  # 舊式居留證
    (re.compile(r"(?<!\d)09\d{2}-?\d{3}-?\d{3}(?!\d)"), "[電話]"),
    (re.compile(r"(?<!\d)\d{8,10}(?!\d)"), "[號碼]"),
)
_LABELS = {"display_name": "[姓名]", "student_no": "[學號]", "username": "[帳號]", "email": "[電子郵件]"}


def known_values(**values):
    """回傳 [(值, 代號)]，長的先換；一個字的姓名不換，避免把一般文字換掉。"""
    pairs = [(str(value).strip(), _LABELS[key]) for key, value in values.items()
             if key in _LABELS and value and len(str(value).strip()) >= 2]
    return sorted(pairs, key=lambda pair: len(pair[0]), reverse=True)


def known_values_for(user):
    profile = getattr(user, "student_profile", None)
    return known_values(display_name=user.display_name, username=user.username, email=user.email,
                        student_no=profile.student_no if profile else None)


def redact(value, known=()):
    """字串、清單、字典都會逐層處理；數字和 None 原樣保留。"""
    if isinstance(value, str):
        for original, label in known:
            value = value.replace(original, label)
        for pattern, label in _PATTERNS:
            value = pattern.sub(label, value)
        return value
    if isinstance(value, dict):
        return {key: redact(item, known) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item, known) for item in value]
    return value

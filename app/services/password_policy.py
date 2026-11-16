"""密碼規則與「改密碼後其他裝置登出」（11-05 評審意見 1b，2026-11-10）。

規則（check 回傳不合格的原因清單，空清單代表可以用）：
- 至少 10 個字元，最多 128 個字元。
- 同時有英文字母和數字。
- 不能包含帳號（學生帳號通常就是學號）。
- 不能是常見密碼，也不能和目前的密碼相同。

其他裝置登出：登入時在 session 存一個「密碼指紋」（用 SECRET_KEY 對密碼雜湊做 HMAC，不把雜湊本身放進 cookie）。
改密碼後雜湊變了，其他裝置帶的舊指紋對不上，下一次開頁面就被登出（app/routes/main.get_current_user）。
不用新增資料表欄位，也不用資料庫遷移。
"""
import hashlib
import hmac

from flask import current_app

MIN_LENGTH = 10
MAX_LENGTH = 128
SESSION_KEY = "password_fingerprint"

# 常見密碼（小寫比對）。只列真的常被用的，避免誤擋。
COMMON = {
    "password", "password1", "password123", "1234567890", "0123456789", "12345678910", "qwertyuiop",
    "qwerty1234", "1qaz2wsx3edc", "abcd123456", "abc1234567", "a123456789", "aa12345678", "iloveyou12",
    "admin12345", "student123", "ukn1234567", "kangning123", "1q2w3e4r5t", "zxcvbnm123", "asdf123456",
}


def rules_text():
    return [f"至少 {MIN_LENGTH} 個字元", "同時有英文字母和數字", "不能包含帳號或學號", "不能用常見密碼"]


def check(password, user=None):
    problems = []
    password = password or ""
    if len(password) < MIN_LENGTH:
        problems.append(f"密碼至少要 {MIN_LENGTH} 個字元。")
    if len(password) > MAX_LENGTH:
        problems.append(f"密碼最多 {MAX_LENGTH} 個字元。")
    if not any(ch.isascii() and ch.isalpha() for ch in password) or not any(ch.isdigit() for ch in password):
        problems.append("密碼要同時有英文字母和數字。")
    lowered = password.lower()
    if lowered in COMMON:
        problems.append("這是常見密碼，很容易被猜到，請換一個。")
    if user is not None:
        names = {(user.username or "").lower()}
        profile = getattr(user, "student_profile", None)
        if profile and profile.student_no:
            names.add(profile.student_no.lower())
        if any(name and len(name) >= 4 and name in lowered for name in names):
            problems.append("密碼不能包含帳號或學號。")
        if user.password_hash and user.check_password(password):
            problems.append("新密碼不能和目前的密碼相同。")
    return problems


def fingerprint(user):
    key = (current_app.config.get("SECRET_KEY") or "").encode()
    return hmac.new(key, (user.password_hash or "").encode(), hashlib.sha256).hexdigest()[:32]

"""資管科小助手在「實習履歷」頁的專屬功能：學生直接對小助手說家庭生活，小助手整理後填進履歷（2026-11-18）。

- 只在學生開著實習履歷頁、而且說的內容提到家人時才攔截；其他問題照原本的小助手流程。
- 內容只用學生說的，由 `internship_resume_draft.family_paragraph` 整理（走 ai_gateway、先遮蔽個資；AI 沒開就放原文）。
- 回傳多一個 `fill`，前端（components.js 的小助手）收到後交給履歷頁的 `resume-editor.js` 填進「家庭生活」格子；
  要按「儲存草稿」才存檔，小助手本身不存學生說的內容。
"""

import re

PAGE_HINT = "實習履歷"
_FAMILY = re.compile(r"家庭|家裡|家人|爸媽|父母|爸爸|媽媽|我家")
_QUESTION = re.compile(r"怎麼|如何|怎樣|什麼|嗎|\?|？")
MIN_CONTENT = 20  # 少於這個字數多半只是「幫我寫家庭生活」這種要求，還沒有內容可整理

GUIDE = ("直接用說的就好：說說你家有幾個人、家裡的人做什麼、你從小在家裡學到什麼或幫過什麼忙。"
         "例如：「我家四個人，爸媽做小生意，我從小幫忙顧店，學會負責任。」"
         "說完我會整理成一段，放進履歷的「家庭生活」，你再自己修改。")


def family_fill(user, message, page):
    """沒有要攔截回傳 None；否則回傳小助手的回應字典（和 /assistant/ask 的格式相同，可能多一個 fill）。"""
    if getattr(user, "role", "") != "student" or PAGE_HINT not in (page or ""):
        return None
    message = (message or "").strip()
    if not _FAMILY.search(message):
        return None
    base = {"steps": [], "sources": [], "links": [], "plan": None}
    if len(message) < MIN_CONTENT or (len(message) < 40 and _QUESTION.search(message)):
        return {**base, "answer": GUIDE}
    from app.services import internship_resume_draft as drafts
    try:
        text, note = drafts.family_paragraph(user, message)
    except ValueError:
        return {**base, "answer": GUIDE}
    return {**base, "steps": ["整理家庭生活"], "fill": {"target": "family", "text": text},
            "answer": f"{note}\n已經放進履歷的「家庭生活」，關掉這個視窗就看得到；按「儲存草稿」才會存檔。"}

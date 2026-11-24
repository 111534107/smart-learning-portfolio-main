"""實習履歷自傳（學校格式四段）一鍵生成：家庭生活、求學經過及社團活動、個人專長及簡要經歷、未來生涯規劃。

- 只用學生勾選的已確認資料，以及學生自己寫／說的文字；不編造家庭、感受、獎項、數字。
- 家庭生活與未來規劃是學校格式固定要寫的，內容只有學生知道：學生沒寫就留空，並提示怎麼寫，不替他編。
- 送外部 AI 前會遮蔽姓名、學號、電話等個資（ai_gateway 處理）；AI 沒開或失敗就改用規則整理。
- 結果只是預填，學生可以逐段修改，按儲存才算數。
"""

from app.services import internship_resume as resume

SECTION_KEYS = [key for key, _ in resume.SECTIONS]
SECTION_TITLES = dict(resume.SECTIONS)
MAX_CHARS = 220  # 每段上限，避免寫成長文
SCHEMA = {"type": "object",
          "properties": {key: {"type": "string"} for key in SECTION_KEYS},
          "required": SECTION_KEYS}
HINTS = {
    "family": "家庭生活只有你自己知道，請用一兩句寫：家裡有誰、你從小學到什麼或幫過什麼忙；小助手不會替你編。",
    "future": "未來生涯規劃請先寫一兩句你想去哪裡實習、想學什麼；小助手會幫你整理語句。",
}


def _items_for(choices, key):
    lines = [item["line"] for item in choices["experiences"] if item["section"] == key]
    if key == "skill":
        lines = [f"證照：{item['name']}" for item in choices["credentials"]] + lines
    return lines


def collect(choices):
    """每段要整理的原料：{key: {"typed": 學生寫的字, "items": [已確認資料一行一筆]}}。"""
    return {key: {"typed": (choices["texts"].get(key) or "").strip(),
                  "items": _items_for(choices, key)} for key in SECTION_KEYS}


def _fallback(material):
    """AI 沒開時：把學生寫的字和勾選的資料排成一段，不加任何沒有的內容。"""
    result = {}
    for key, data in material.items():
        parts = []
        if data["typed"]:
            parts.append(data["typed"])
        if data["items"]:
            parts.append("相關經歷：" + "；".join(data["items"]) + "。")
        result[key] = "".join(parts)[:MAX_CHARS * 2]
    return result


def _prompt(material):
    blocks = []
    for key in SECTION_KEYS:
        data = material[key]
        typed = data["typed"] or "（學生沒有寫）"
        items = "\n".join(f"- {line}" for line in data["items"]) or "（沒有勾選資料）"
        blocks.append(f"【{SECTION_TITLES[key]}】（欄位 {key}）\n學生自己寫的：{typed}\n學生勾選的已確認資料：\n{items}")
    return ("你是資管科的自傳小助手，幫學生把「實習申請履歷」的自傳四段整理成通順、具體、像五專學生自己會說的話。\n"
            "規則：\n1. 第一人稱、真誠自然，不浮誇、不用空泛形容詞。\n"
            "2. 只能使用下面的內容，不可以編造任何家庭情況、獎項、名次、分數、證照、公司、感受或數字。\n"
            f"3. 每段約 100 到 {MAX_CHARS} 字；不要加標題或編號。\n"
            "4. 家庭生活（family）與未來生涯規劃（future）：學生沒有寫，該欄位輸出空字串，不要自己想。\n"
            "5. 求學經過及社團活動（study）、個人專長及簡要經歷（skill）：依勾選資料整理，資料不夠就寫短一點。\n"
            "只輸出 JSON，欄位為 family、study、skill、future。\n\n" + "\n\n".join(blocks))


def generate(student, choices):
    """回傳 {"sections": {key: 文字}, "hints": {key: 提示}, "provider": 來源, "note": 給學生看的說明}。"""
    from app.services import ai_gateway
    material = collect(choices)
    names = [(student.display_name or "", "〔姓名〕")] if student.display_name else []
    provider, note = "rules", "AI 目前沒有開啟，先把你寫的和勾選的資料排好，請自己再修。"
    try:
        result, used = ai_gateway.generate_json(_prompt(material), SCHEMA, known=names)
        sections = {key: str(result.get(key, "")).strip()[:MAX_CHARS * 2] for key in SECTION_KEYS}
        provider, note = used, "小助手已整理，請逐段看過再改成你自己的話，改好按儲存。"
    except Exception:  # noqa: BLE001  AI 沒開、沒金鑰或失敗都退回規則整理
        sections = _fallback(material)
    # 家庭與未來學生沒寫就不放內容（AI 若自己編了也清掉）
    for key in ("family", "future"):
        if not material[key]["typed"]:
            sections[key] = ""
    hints = {key: text for key, text in HINTS.items() if not material[key]["typed"]}
    return {"sections": sections, "hints": hints, "provider": provider, "note": note}

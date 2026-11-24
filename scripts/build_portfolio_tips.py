"""從聯招會二技技優甄審簡章（已轉成文字）整理各校系的備審白話建議（2026-11-20）。

用法：
    python scripts/build_portfolio_tips.py <簡章文字檔> [輸出 JSON]

文字檔是用 pypdfium2 逐頁轉出的純文字，每頁開頭有「===== 第 N 頁 =====」。
只整理簡章寫明的內容：要交什麼、配分、同分比序、格式規定（字數、表格、簽名、排列順序）與備註；
每條都附簡章印刷頁碼。產出的 JSON 由 app/content/portfolio_tips.py 讀取。
"""
import json
import re
import sys
from pathlib import Path

SOURCE = "115 學年度科技校院二年制技優保送及甄審入學招生簡章（聯招會）"
SOURCE_URL = "https://enrollstudents.nfu.edu.tw/download/20251121001/25845"
CHECKED = "2026-11-20"

# 規定用語 → 白話（只換詞，不改意思）
PLAIN = [
    ("電腦繕打", "電腦打字"), ("繕打", "打字"), ("親簽", "親筆簽名"), ("送審資料", "備審資料"),
    ("缺項以零分計", "少交的項目以零分計算"), ("依序排列", "照順序排好"), ("檢附", "附上"),
    ("影本", "影印本"), ("須", "要"), ("俾利", "方便"), ("惟", "但"), ("逾期", "超過期限"),
]
FORMAT_WORDS = re.compile(r"字以內|字為限|字數|頁以內|頁為限|張以內|表[A-ZＡ-Ｚ一二三]|下載|格式|封面|目錄|親簽|簽名|繕打|手寫|A4|裝訂|依序|順序|註明|負責")
SKIP_NOTES = re.compile(r"不再歸還|自行留存|畢業門檻")


def plain(text):
    text = re.sub(r"\s+", "", text)
    for old, new in PLAIN:
        text = text.replace(old, new)
    return text.strip("。；;") + "。"


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.content.portfolio_tips import key_of, norm_school  # noqa: E402  (和網頁對應用同一套寫法)


def numbered(lines):
    """把換行斷掉的編號項目接回去：1.… 2.… *…"""
    items = []
    for line in lines:
        if re.match(r"^(\d+[.．、]|\*|※)", line) or not items:
            items.append(line)
        else:
            items[-1] += line
    return [re.sub(r"^(\d+[.．、]|\*|※)\s*", "", item).strip() for item in items if item.strip()]


def parse(text):
    pages = re.split(r"\n===== 第 (\d+) 頁 =====\n", text)
    blocks = []
    for k in range(1, len(pages), 2):
        body = pages[k + 1]
        match = re.search(r"招生簡章\s*(\d+)\s*$", body.strip()) or re.search(r"^\s*(\d+)\s*115\s*學年度", body.strip())
        printed = match.group(1) if match else None
        for part in body.split("校系(組)、學程資料")[1:]:
            lines = [line.strip() for line in part.splitlines() if line.strip()]
            idx = next((j for j, line in enumerate(lines) if re.search(r"指定項目\s*占總成", line)), None)
            if idx is None:
                continue
            dept = re.sub(r"\s*指定項目.*$", "", lines[idx]).strip("　 ")
            school = lines[idx - 1]
            head_end = next((j for j, line in enumerate(lines) if line.startswith("繳交資料")), len(lines))
            head = lines[idx + 1:head_end]
            category = re.search(r"招生類別\s*(\S+)", "\n".join(head))
            written = re.search(r"(?:書面|備審)資料審查\s*(\d+)%", "\n".join(head))
            order = []
            for line in head:
                found = re.search(r"\s(\d)\s+([^\s-][^\s]*)$", line)
                if found and found.group(2) not in ("--",):
                    order.append(found.group(2))
            rest = lines[head_end + 1:]
            note_at = next((j for j, line in enumerate(rest) if re.match(r"^備\s*註", line)), len(rest))
            score_at = next((j for j, line in enumerate(rest[:note_at]) if "評分" in line), note_at)
            submit = numbered(rest[:score_at])
            score_lines = rest[score_at + 1:note_at]
            # 有些校系把評分標準寫成一行：「…評分標準:歷年成績單30%、自傳及其他佐審資料70%。」
            inline = "".join(rest[score_at:note_at])
            inline_weights = re.findall(r"([^:：、，,。\d]{2,20}?)\s*(\d{1,3})\s*%", inline.split("評分標準", 1)[-1]) if "評分標準" in inline else []
            notes = numbered([line for line in rest[note_at + 1:] if "招生簡章" not in line])
            blocks.append({
                "school": school, "dept": dept, "category": category.group(1) if category else "",
                "page": printed, "written_percent": int(written.group(1)) if written else None,
                "order": order, "submit": submit, "score": numbered(score_lines), "notes": notes,
                "inline_weights": inline_weights,
            })
    return blocks


def tips_from(block):
    page = f"第{block['page']}頁" if block["page"] else ""
    tips = []
    if block["submit"]:
        names = []
        for item in block["submit"]:
            if item.startswith(("送審", "缺項", "備註", "未附")) or "%" in item or item.strip("。") in block["order"]:
                continue
            name = re.split(r"[，,。（(]", item.replace("「", "").replace("」", ""))[0]
            name = re.split(r"為|：|:", name)[0] if len(name) > 18 else name
            if name:
                names.append(name)
        if names:
            tips.append({"text": "要交：" + "、".join(names) + "。", "page": page})
    weights = []
    for item in block["score"]:
        found = re.match(r"^([^（(：:]+?)\s*[（(]\s*(\d+)\s*%\s*[）)]", item)
        if found:
            weights.append(f"{found.group(1)} {found.group(2)}%")
    if not weights:
        weights = [f"{name.strip()} {pct}%" for name, pct in block.get("inline_weights", [])]
    if not weights:
        # 評分標準散在繳交資料裡：「在校歷年成績單40%」「學習能力（30%）」；加起來約 100 才採用
        found = re.findall(r"([一-鿿A-Za-z、及與]{2,16})\s*[（(：:]?\s*(\d{1,3})\s*%", "".join(block["submit"] + block["score"]))
        if found and 95 <= sum(int(p) for _, p in found) <= 105:
            weights = [f"{name} {pct}%" for name, pct in found]
    if weights:
        tips.append({"text": "配分：" + "、".join(weights) + "。先準備占分最高的項目。", "page": page})
    for item in block["submit"] + block["notes"]:
        if FORMAT_WORDS.search(item) and not SKIP_NOTES.search(item):
            tips.append({"text": plain(item), "page": page})
    if block["order"]:
        tips.append({"text": "同分時依序比：" + "、".join(block["order"]) + "。", "page": page})
    seen, unique = set(), []
    for tip in tips:
        if tip["text"] not in seen:
            seen.add(tip["text"])
            unique.append(tip)
    return unique


def main():
    text = Path(sys.argv[1]).read_text(encoding="utf-8")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "app/content/portfolio_tips_115_skill.json"
    result = {}
    for block in parse(text):
        percent = block["written_percent"]
        summary = (f"這個管道只看書面資料（占 {percent}%），備審就是全部。" if percent == 100
                   else f"書面資料審查占總成績 {percent}%。" if percent else "請照簡章準備書面資料。")
        result[key_of(block["school"], block["dept"], block["category"])] = {
            "school": norm_school(block["school"]), "department": block["dept"], "channel": "技優甄審",
            "source": SOURCE, "source_url": SOURCE_URL, "checked": CHECKED,
            "summary": summary, "tips": tips_from(block),
        }
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(result)} 個校系 → {out}")


if __name__ == "__main__":
    main()

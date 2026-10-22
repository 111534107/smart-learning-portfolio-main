"""科上文件知識庫：搜尋 app/content/knowledge/*.md，給資管科小助手引用。

做法很簡單（不需要額外套件）：
1. 每份 Markdown 依「## 小標題」切成段落。
2. 把問題切成「兩個字一組」（例如「畢業門檻」→ 畢業、業門、門檻），看每段出現幾組。
3. 分數最高的幾段交給 AI，AI 只能依這些段落回答，並標出來源。

規定改了：直接修改對應的 .md 檔，或重新執行 scripts/build_knowledge.py。
"""

import re
from functools import lru_cache
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "content" / "knowledge"

# 學生常用的說法 → 文件裡的寫法（可以自己加）
SYNONYMS = {"重修": "重補修", "補修": "重補修", "畢業條件": "畢業門檻", "幾張證照": "專業證照", "四技": "二技",
            "統測": "二技", "備審": "備審資料", "報告書": "專題成果報告書", "轉系": "轉科"}


def _bigrams(text):
    text = re.sub(r"[\s\W_]+", "", text.lower())
    return {text[i:i + 2] for i in range(len(text) - 1)} | ({text} if len(text) == 1 else set())


@lru_cache(maxsize=1)
def _chunks(folder=KNOWLEDGE_DIR):
    chunks = []
    for path in sorted(Path(folder).glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        meta = dict(re.findall(r"^(title|url|source): ?(.*)$", raw.split("---", 2)[1], re.M)) if raw.startswith("---") else {}
        body = raw.split("---", 2)[2] if raw.startswith("---") else raw
        title = meta.get("title") or path.stem
        for section in re.split(r"\n(?=## )", body):
            heading = section.strip().splitlines()[0].lstrip("#").strip() if section.strip() else ""
            text = section.strip()
            if len(text) < 20:
                continue
            chunks.append({"doc": path.stem, "title": title, "heading": heading, "text": text[:2500],
                           "url": meta.get("url", ""), "grams": _bigrams(text),
                           "title_grams": _bigrams(title + heading)})
    return chunks


def search(query, limit=4):
    """回傳最相關的段落：[{title, heading, text, url}]。找不到就回傳空串列。"""
    for word, replacement in SYNONYMS.items():
        if word in query:
            query += replacement
    query_grams = _bigrams(query)
    if not query_grams:
        return []
    scored = []
    for chunk in _chunks():
        # 標題、小標題命中的分數加倍：問「轉科」時，轉科公告應該排在最前面
        score = len(query_grams & chunk["grams"]) + 2 * len(query_grams & chunk["title_grams"])
        if score:
            scored.append((score, chunk))
    scored.sort(key=lambda pair: -pair[0])
    best = scored[0][0] if scored else 0
    return [{k: chunk[k] for k in ("title", "heading", "text", "url")}
            for score, chunk in scored[:limit] if score >= max(2, best // 2)]


def documents():
    """知識庫有哪些文件（給小助手的開場說明用）。"""
    seen = {}
    for chunk in _chunks():
        seen.setdefault(chunk["doc"], chunk["title"])
    return list(seen.values())

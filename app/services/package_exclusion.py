"""學生選擇「不放進備審」的資料（導師 2026-11-12）。

- 成績、證照、經歷每一筆都有 excluded_from_package；學生標了之後，那一筆不進自傳事實、
  不進備審 Word、不算進準備度與佐證清單。
- 簡章規定必備的類別不能排除。「必備」的判斷只看簡章資料，不自己猜：
  1. 校系把成績列為評分項目 → 歷年成績單是必備文件，成績不能排除。
  2. 項目名稱或要求說明寫明「必繳／必備／必附」→ 該項目對應的類別不能排除。
- 標記存在資料本身（不分校系）；實際要不要放，依每個校系的必備類別決定，
  所以同一筆成績可能在甲校系被排除、在規定必備的乙校系仍然放入。
"""

import re

REQUIRED_WORDS = re.compile(r"必繳|必備|必附")
PROJECT_PATTERN = re.compile(r"專題|作品")

REQUIRED_REASON = "簡章規定必備"


def required_keys(program):
    """這個校系簡章規定必備、學生不能排除的資料類別。"""
    keys = set()
    for item in program.items:
        if not item.is_required:
            continue
        item_keys = item.category_keys
        if "grades" in item_keys:
            keys.add("grades")
        if REQUIRED_WORDS.search(f"{item.source_item_name or ''}{item.requirement or ''}"):
            keys.update(item_keys)
    return keys


def portfolio_keys(record):
    """一筆經歷算在哪些類別：自己的類別，標題含「專題／作品」再加專題作品。"""
    keys = {record.category}
    if PROJECT_PATTERN.search(record.title or ""):
        keys.add("project")
    return keys


def is_kept(record, keys, required):
    """這一筆要不要放進這個校系的備審。keys：這筆資料所屬類別；required：required_keys(program)。"""
    return not record.excluded_from_package or bool(set(keys) & set(required))


def keep_courses(courses, required):
    return [course for course in courses if is_kept(course, ("grades",), required)]


def keep_credentials(credentials, required):
    return [credential for credential in credentials if is_kept(credential, ("credential",), required)]


def keep_portfolios(records, required):
    return [record for record in records if is_kept(record, portfolio_keys(record), required)]


def locking_programs(programs, keys):
    """學生的目標校系中，哪些規定這類資料必備。"""
    return [program for program in programs if set(keys) & required_keys(program)]


def lock_state(programs, keys):
    """畫面用：locked＝每個目標校系都規定必備（不能排除）；programs＝規定必備的校系。"""
    locking = locking_programs(programs, keys)
    return {"locked": bool(programs) and len(locking) == len(programs), "programs": locking}

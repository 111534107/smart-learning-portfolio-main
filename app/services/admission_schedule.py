"""招生時程：依招生管道列出重要日程，標出已過、進行中、下一步。

資料放在 app/content/admission_schedule.csv，每一列附官方出處；時間是台灣時間。
- 二技技優甄審（6 位數志願代碼）：全國共用技專校院招生委員會聯合會的日程。
- 日間部申請入學：各校日期不同，這一版不列，請看學校招生網站。
- 插大（轉學考）：各校自辦或分區聯招，日期不同，不做共用日程，畫面寫「依各校簡章」並附學校網址。
- 這一年的日程還沒公告時，用最近一年當參考（reference=True），畫面要標明「去年」。
"""

import csv
from datetime import datetime
from pathlib import Path

from flask import has_app_context

from app.services.transfer_exam import TRANSFER_CATEGORY, is_transfer

SCHEDULE_FILE = Path(__file__).resolve().parents[1] / "content" / "admission_schedule.csv"

CHANNEL_LABELS = {"skill_review": "二技技優甄審", "transfer": TRANSFER_CATEGORY}

# 最近一次到官網確認「下一屆日程是否公告」的日期；公告後把新日程加進 CSV
CHECKED_ON = "2026-10-22"


def _parse(text):
    text = (text or "").strip()
    return datetime.strptime(text, "%Y-%m-%d %H:%M") if text else None


def _published_events():
    """管理員核准的日程（資料庫）。同一組（管道＋學年度）整組取代檔案裡的日程。"""
    from app.models import AdmissionScheduleEvent
    groups = {}
    for event in AdmissionScheduleEvent.query.filter_by(status="published").order_by(AdmissionScheduleEvent.id):
        groups.setdefault((event.channel, event.admission_year), []).append({
            "name": event.name, "start": event.start_at, "end": event.end_at, "note": event.note or "",
            "source": event.source_url or "",
        })
    return groups


def load_schedule(path=None):
    """回傳 {(管道, 學年度): [{name, start, end, note, source}]}，依開始時間排序。

    沒指定 path 時：先讀 app/content/admission_schedule.csv，再用管理員核准的日程（資料庫）整組取代。
    """
    use_database = path is None and has_app_context()
    path = path or SCHEDULE_FILE
    schedule = {}
    if not Path(path).is_file():
        return _sorted(_published_events()) if use_database else {}
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            schedule.setdefault((row["管道"].strip(), int(row["學年度"])), []).append({
                "name": row["項目"].strip(),
                "start": _parse(row["開始"]),
                "end": _parse(row["結束"]),
                "note": row["說明"].strip(),
                "source": row["出處"].strip(),
            })
    if use_database:
        schedule.update(_published_events())
    return _sorted(schedule)


def _sorted(schedule):
    for events in schedule.values():
        events.sort(key=lambda event: event["start"].date())  # 同一天依官方表格順序（sort 是穩定排序）
    return schedule


def schedule_groups():
    """管理員核對用：候選日程依（管道、學年度）分組，逐項和目前使用的日程比對。"""
    from app.models import AdmissionScheduleEvent
    current = load_schedule()
    candidates = {}
    for event in AdmissionScheduleEvent.query.filter_by(status="candidate").order_by(AdmissionScheduleEvent.start_at):
        candidates.setdefault((event.channel, event.admission_year), []).append(event)
    groups = []
    for (channel, year), events in sorted(candidates.items(), key=lambda item: -item[0][1]):
        existing = current.get((channel, year), [])
        used, rows = set(), []
        for event in events:
            index = _match(event, existing, used)
            old = existing[index] if index is not None else None
            if old is None:
                mark = "新增"
            elif old["start"] == event.start_at and old["end"] == event.end_at:
                mark = "相同"
            else:
                mark = "日期不同"
            rows.append({"event": event, "mark": mark, "current": old})
        groups.append({"channel": channel, "year": year, "label": CHANNEL_LABELS.get(channel, channel), "rows": rows,
                       "missing": [item["name"] for i, item in enumerate(existing) if i not in used],
                       "source": events[0].source_url or ""})
    return groups


def _compact(name):
    return "".join(ch for ch in name if ch.isalnum())


def _match(event, existing, used):
    """候選項目對應目前日程的哪一項：名稱相同 → 起訖時間相同 → 名稱互相包含。AI 常把說明併進名稱，所以不能只比名稱。"""
    tests = (
        lambda item: item["name"] == event.name,
        lambda item: item["start"] == event.start_at and item["end"] == event.end_at,
        lambda item: _compact(item["name"]) in _compact(event.name) or _compact(event.name) in _compact(item["name"]),
    )
    for test in tests:
        for index, item in enumerate(existing):
            if index not in used and test(item):
                used.add(index)
                return index
    return None


def program_channel(program):
    if program.program_code.isdigit():
        return "skill_review"
    return "transfer" if is_transfer(program) else None


def channel_label(program):
    """卡片上標示的招生管道名稱；其他管道用簡章上的招生類別。"""
    channel = program_channel(program)
    return CHANNEL_LABELS[channel] if channel else (program.admission_category or "申請入學")


def _state(event, now):
    # 只有一個時間點的項目（例如「報到截止 17:00」），當天都算進行中
    end = event["end"] or event["start"].replace(hour=23, minute=59)
    if now > end:
        return "past"
    return "current" if now >= event["start"] or now.date() == event["start"].date() else "upcoming"


def _build(channel, year, schedule, now, reference):
    now = now or datetime.now()
    events = [{**event, "state": _state(event, now)} for event in schedule[(channel, year)]]
    upcoming = [event for event in events if event["state"] != "past"]
    return {
        "channel": channel,
        "channel_label": CHANNEL_LABELS[channel],
        "year": year,
        "reference": reference,
        "events": events,
        "next": upcoming[0] if upcoming else None,
        "finished": not upcoming,
    }


def timeline(program, schedule=None, now=None):
    """回傳 {channel, channel_label, year, reference, events, next, finished}；沒有共用日程的管道回傳 None。"""
    channel = program_channel(program)
    if channel is None:
        return None
    schedule = load_schedule() if schedule is None else schedule
    years = sorted(year for key_channel, year in schedule if key_channel == channel and year <= program.admission_year)
    if not years:
        return None
    return _build(channel, years[-1], schedule, now, reference=years[-1] != program.admission_year)


def latest_timeline(channel="skill_review", schedule=None, now=None):
    """某個管道最新一年的日程（招生時程頁用）；沒有資料時回傳 None。"""
    schedule = load_schedule() if schedule is None else schedule
    years = sorted(year for key_channel, year in schedule if key_channel == channel)
    return _build(channel, years[-1], schedule, now, reference=False) if years else None

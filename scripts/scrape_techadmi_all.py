"""從技專校院招生策略委員會網站抓「全部」技專校院（含私立）的二技校系與名額（只讀公開網頁，不下載檔案）。

2026-11-13：原本的 scripts/scrape_techadmi_national.py 只抓國立、而且要等各管道公告名單；
116 學年度日間部申請入學名單要 115 年 12 月底才公告，所以改從「全國技專校院」各校、各系頁面
（schools_detail_search.php，列出這個系所有管道與名額）抓，取其中二技的管道（type=2）。

用法（在專案根目錄）：
    python scripts/scrape_techadmi_all.py [--out logs/techadmi]
輸出（--out 資料夾）：
    schools.json         每校：名稱、techadmi 編號、地址、官網（招策會「全國技專校院」頁）
    programs_2tech.csv   學校,科系,管道,招生類別,名額,來源網址
最多 2 條連線，每條每個請求後停 0.5 秒；網站回「禁止訪問」就停止。
"""
import argparse
import csv
import html
import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = "https://www.techadmi.edu.tw/"
# 管道名稱看網址裡的代碼（頁面上的標題順序不固定）；表上沒有的才用頁面標題
CHANNELS = {"comd01": "二技日間部申請入學", "comd02": "二技進修部申請入學", "comd05": "二技技優保送入學",
            "comd06": "二技技優甄審入學", "comd11": "身心障礙學生升學大專校院甄試(二技組)",
            "comi06": "二技進修部護理師在職專班", "comi08": "運動績優學生單獨招生(二技)",
            "comi13": "身心障礙學生單獨招生(二技)", "comi15": "產學攜手合作計畫專班(二技)",
            "comi18": "五專菁英班學生升讀二技甄審入學", "comi23": "新住民入學招生(二技)", "comz01": "空中進修學院二技"}


def get(url):
    err = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
            time.sleep(0.5)
            if "禁止訪問" in data[:3000] and "無法訪問此頁面" in data:
                # 2026-11-13 第二次重抓時被網站限制：遇到就整個停下來，不要一直重試
                raise SystemExit(f"招策會網站拒絕存取（{url}），請過一段時間再跑，或減少 --ids")
            return data
        except Exception as e:  # noqa: BLE001 - 網路錯誤重試三次
            err = e
            time.sleep(2)
    raise err


def lines_of(h):
    t = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>|<!--[\s\S]*?-->", "", h)
    t = re.sub(r'<a [^>]*href="([^"]+)"[^>]*>', r"\n[[\1]]\n", t)
    t = re.sub(r"<[^>]+>", "\n", t)
    t = html.unescape(re.sub(r"[ \t\xa0]+", " ", t))
    return [l.strip() for l in t.splitlines() if l.strip()]


def school_ids():
    ids = {}
    for region in (1, 2, 3, 4):
        for sid in re.findall(r"schools_detail\.php\?psrid=(\d+)", get(f"{BASE}schools_list.php?do={region}")):
            ids[sid] = region
    return ids


def school_info(sid):
    h = get(f"{BASE}schools_detail.php?psrid={sid}")
    lines = lines_of(h)
    # 校名下一行是地址（郵遞區號開頭；多校區的寫成「台北校區：100025臺北市…」，取第一個）。
    # 有的學校頁少了「學習資源」等連結，所以用地址定位；只看「返回」之前，避免抓到網站頁尾招策會自己的地址。
    end = lines.index("[[javaScript:history.go(-1);]]") if "[[javaScript:history.go(-1);]]" in lines else len(lines)
    address_re = re.compile(r"^(?:\S{1,8}：)?(\d{3,6}\s*\S{2}[縣市].*)$")
    a = next(i for i in range(end) if address_re.match(lines[i]))
    name, address = lines[a - 1], address_re.match(lines[a]).group(1)
    site = next((l[2:-2] for l in lines[a + 1:a + 6] if l.startswith("[[http") and "youtube" not in l), "")
    depts = re.findall(r'<option value="(\d+)"[^>]*>([^<]+)</option>', h)
    return {"name": name, "techadmi_id": sid, "address": address, "website": site,
            "source": f"{BASE}schools_detail.php?psrid={sid}"}, depts


def two_tech_programs(sid, seq):
    url = f"{BASE}schools_detail_search.php?psrid={sid}&seq={seq}"
    lines = lines_of(get(url))
    start = next((i for i, l in enumerate(lines) if l == "[[schools_detail.php?psrid=%s]]" % sid), 0)
    rows, channel = [], ""
    i = start
    while i < len(lines):
        l = lines[i]
        if l in ("[[javaScript:history.go(-1);]]",):
            break
        m = re.match(r"^\[\[schools_detail_search_detail\.php\?pid=(\d+)&type=(\d)&type2=(\w+)\]\]$", l)
        if m and i + 1 < len(lines) and not lines[i + 1].startswith("[["):
            label = lines[i + 1]
            quota = re.match(r"^(\d+)名$", lines[i + 3]) if i + 3 < len(lines) else None
            if m.group(2) == "2" and quota:
                dept, _, category = label.partition("/")
                rows.append([dept, CHANNELS.get(m.group(3), channel), category, int(quota.group(1)), BASE + l[2:-2]])
            i += 4 if quota else 2
            continue
        if l == "[[#]]":  # 「招生類別」標籤（例如 08管理類(四)），不是管道名稱
            i += 2
            continue
        if not l.startswith("[[") and not re.match(r"^\d+名$", l) and "/" not in l:
            channel = l
        i += 1
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="logs/techadmi")
    parser.add_argument("--ids", default="", help="只抓這些招策會學校編號（逗號分開），例如重抓有二技的學校")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    schools, programs = [], []
    def one_school(sid):
        info, depts = school_info(sid)
        found = []
        for seq, _dept in depts:
            for dept, channel, category, quota, url in two_tech_programs(sid, seq):
                found.append([info["name"], dept, channel, category, quota, url])
        info["departments"] = [name for _seq, name in depts]
        info["two_tech_programs"] = len(found)
        print(info["name"], len(depts), "系，二技", len(found), "筆", file=sys.stderr, flush=True)
        return info, found

    # 2 條連線同時抓（3 條時第二次重抓被網站限制）（每條每個請求後停 0.5 秒），學校順序照招策會名單
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = [i for i in args.ids.split(",") if i] or list(school_ids())
        for info, found in pool.map(one_school, ids):
            schools.append(info)
            programs.extend(found)
    (out / "schools.json").write_text(json.dumps(schools, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(out / "programs_2tech.csv", "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["學校", "科系", "管道", "招生類別", "名額", "來源網址"])
        writer.writerows(programs)
    print(f"{len(schools)} 校、二技 {len(programs)} 筆 → {out}", file=sys.stderr)


if __name__ == "__main__":
    main()

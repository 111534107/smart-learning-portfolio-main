"""從技專校院招生策略委員會網站抓「國立」二技校系與名額（只讀公開網頁，不下載檔案）。

用法（在專案根目錄）：
    python scripts/scrape_techadmi_national.py
輸出 techadmi_national.json（目前目錄）：{管道: {學校: [[系名, 名額, 招生類別], ...]}}
網站只有系名、名額、日程與簡章連結；備審加權要看各校簡章。
"""
import json, re, sys, time, urllib.request
BASE = "https://www.techadmi.edu.tw/"
CHANNELS = {"comd06": "技優甄審", "comd05": "技優保送", "comd01": "日間部申請入學", "comd02": "進修部申請入學",
            "comi18": "五專菁英班升讀二技", "comi15": "產學攜手專班"}

def get(url):
    for _ in range(3):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read().decode("utf-8", "ignore")
        except Exception as e:
            err = e; time.sleep(2)
    raise err

def text(h):
    t = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>|<!--[\s\S]*?-->", "", h)
    t = re.sub(r"<[^>]+>", "\n", t); t = re.sub(r"[ \t\xa0]+", " ", t)
    return [l.strip() for l in t.splitlines() if l.strip()]

out = {}
for code, name in CHANNELS.items():
    h = get(f"{BASE}edutype_list.php?type=2&type2={code}")
    schools = dict((s, n.strip()) for s, n in re.findall(rf'school=(\d+)&(?:amp;)?item=dd"[\s\S]*?<span class="h5[^"]*">([^<]+)</span>', h))
    out[name] = {}
    for sid, sname in schools.items():
        if not sname.startswith("國立"):
            continue
        lines = text(get(f"{BASE}edutype_list_detail.php?type=2&type2={code}&school={sid}&item=dd"))
        a = next(i for i, l in enumerate(lines) if l.startswith("招生校系"))
        b = next(i for i in range(a + 1, len(lines)) if lines[i] == "招生學校")
        seg = lines[a + 3:b]
        depts = []
        for i, l in enumerate(seg):
            m = re.match(r"^(\d+) 名$", l)
            if not m or i == 0:
                continue
            prev = seg[i - 1]
            if re.match(r"^\d{2}\D", prev) and i > 1:  # 技優：系名、招生類別、名額
                depts.append([seg[i - 2], int(m.group(1)), prev])
            elif not re.match(r"^\d", prev) and prev != sname:
                depts.append([prev, int(m.group(1)), ""])
        out[name][sname] = depts
        time.sleep(0.5)
    print(name, {k: len(v) for k, v in out[name].items()}, file=sys.stderr)
json.dump(out, open("techadmi_national.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

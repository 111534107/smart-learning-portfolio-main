"""補學校名錄（app/content/schools.csv）：把 scripts/scrape_techadmi_all.py 抓到的學校加進來。

2026-11-13：原本只有 10 所國立；這支補上其他學校的地區、縣市、座標、官網、招生網站。
- 縣市：招策會「全國技專校院」頁的地址；地區依 app/services/school_directory.py 的 REGION_OF_COUNTY（國發會劃分）。
- 座標：OpenStreetMap Nominatim，只送校名，每秒最多一次；查不到的留在報告裡，不寫進 CSV。
- 官網：招策會學校頁上的網址。
- 招生網站：從學校官網首頁找文字含「招生」的連結（同一個學校網域）；找不到就空白，不自己猜。
- 每個網址都用 app.services.form_library_service.check_link 實際連線；不通時再用 curl 以 GET 跟著轉址開一次
  （有些學校網站不收 HEAD、很慢或用舊式 SSL），兩種都不通的不寫。
已經在 CSV 的學校不動。

用法（在專案根目錄）：
    python scripts/build_school_directory.py --schools logs/techadmi/schools_info.json [--only 學校A,學校B]
報告寫到 logs/techadmi/directory_report.json。
"""
import argparse
import csv
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.form_library_service import check_link  # noqa: E402
from app.services.school_directory import CSV_COLUMNS, REGION_OF_COUNTY, SCHOOLS_FILE, normalize_county  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (school-map data check)"}
COUNTY = re.compile(r"^\d{3,6}\s*(\S{2}[縣市])")


def geocode(name, county, district=""):
    """回傳 (緯度, 經度)；查到的地點不在同一個縣市就當作查不到（避免同名店家、分部）。
    只送校名：先查全名，再查去掉「國立」，最後查「校名＋區名校區」（例如台北海洋科技大學士林校區）。"""
    queries = [name, name.removeprefix("國立")] + ([f"{name}{district[:-1]}校區"] if district else [])
    for query in dict.fromkeys(queries):
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
            {"q": query, "format": "json", "limit": 1, "countrycodes": "tw"})
        time.sleep(1.1)
        req = urllib.request.Request(url, headers={"User-Agent": "school-map-data-check/1.0"})
        found = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
        if found and county in normalize_county(found[0].get("display_name", "")):
            return round(float(found[0]["lat"]), 5), round(float(found[0]["lon"]), 5)
    return None


def verify(url):
    """先用系統的 check_link；不通時（有些學校網站不收 HEAD、回應慢、用舊式 SSL）再用 curl 跟著轉址以 GET 開一次。
    回傳 (狀態, 說明)；curl 確認的會註明。"""
    status = check_link(url)
    if status[0] == "ok":
        return status
    try:
        code = subprocess.run(["curl", "-s", "-L", "-o", os.devnull, "-w", "%{http_code}", "--max-time", "30",
                               "-A", "Mozilla/5.0", url], capture_output=True, text=True, timeout=40).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return status
    return ("ok", f"curl GET HTTP {code}（check_link：{status[1]}）") if code.startswith(("2", "3")) else status


def fetch_text(url):
    try:
        req = urllib.request.Request(url, headers=UA)
        return urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        try:
            return subprocess.run(["curl", "-s", "-L", "--max-time", "30", "-A", "Mozilla/5.0", url],
                                  capture_output=True, timeout=40).stdout.decode("utf-8", "ignore")
        except (OSError, subprocess.TimeoutExpired):
            return ""


def admission_site(website):
    """官網首頁上文字含「招生」的連結，同一個學校網域；優先招生專區、招生資訊。"""
    page = fetch_text(website)
    host = urllib.parse.urlparse(website).hostname or ""
    domain = ".".join(host.split(".")[-3:])  # chihlee.edu.tw
    candidates = []
    for href, text in re.findall(r'<a\s[^>]*href="([^"#]+)"[^>]*>([\s\S]*?)</a>', page):
        label = re.sub(r"<[^>]+>|\s+", "", html.unescape(text))
        if "招生" not in label or len(label) > 12:
            continue
        url = urllib.parse.urljoin(website, html.unescape(href).strip())
        if not url.startswith("http") or not (urllib.parse.urlparse(url).hostname or "").endswith(domain):
            continue
        if re.search(r"\.(pdf|docx?|xlsx?)$", url, re.I):
            continue
        score = 0 if re.search(r"招生(專區|資訊|網|服務)", label) else 1
        candidates.append((score, len(label), url))
    return sorted(candidates)[0][2] if candidates else ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schools", default="logs/techadmi/schools_info.json")
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    only = {s for s in args.only.split(",") if s}
    with open(SCHOOLS_FILE, encoding="utf-8-sig", newline="") as handle:
        existing = list(csv.DictReader(handle))
    known = {row["學校"] for row in existing}
    report, added = [], []
    for school in json.loads(Path(args.schools).read_text(encoding="utf-8")):
        name = school["name"]
        if name in known or (only and name not in only) or name.endswith("專科學校"):  # 專科學校沒有二技
            continue
        entry = {"學校": name, "地址": school["address"], "出處": school["source"]}
        m = COUNTY.match(school["address"].replace(" ", ""))
        county = normalize_county(m.group(1)) if m else ""
        region = REGION_OF_COUNTY.get(county, "")
        district = re.search(r"[縣市](\S{1,3}[區鄉鎮市])", school["address"])
        point = geocode(name, county, district.group(1) if district else "") if county else None
        website = school["website"].rstrip("/") + "/" if school["website"] else ""
        web_status = verify(website) if website else ("broken", "沒有官網")
        admission = admission_site(website) if web_status[0] == "ok" else ""
        adm_status = verify(admission) if admission else ("broken", "官網首頁找不到招生連結")
        entry.update({"縣市": county, "地區": region, "座標": point, "官網": website, "官網檢查": web_status,
                      "招生網站": admission, "招生網站檢查": adm_status})
        report.append(entry)
        print(name, county, region, point, web_status[1], admission, adm_status[1], file=sys.stderr, flush=True)
        if region and point and web_status[0] == "ok":
            added.append({"學校": name, "地區": region, "縣市": county, "緯度": point[0], "經度": point[1],
                          "官網": website, "招生網站": admission if adm_status[0] == "ok" else "",
                          "確認日期": date.today().isoformat()})
    with open(SCHOOLS_FILE, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(existing + added)
    out = Path(args.schools).with_name("directory_report.json")
    if out.exists():  # 分批跑時保留之前的報告
        old = {e["學校"]: e for e in json.loads(out.read_text(encoding="utf-8"))}
        old.update({e["學校"]: e for e in report})
        report = list(old.values())
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"新增 {len(added)} 校；報告 {out}", file=sys.stderr)


if __name__ == "__main__":
    main()

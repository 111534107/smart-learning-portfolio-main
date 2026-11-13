"""固定驗收腳本：模擬學生、科辦、導師、管理員實際操作，每一項印出「通過／失敗」。

用法（在專案根目錄）：
    python scripts/acceptance_check.py            自己開一個 5099 埠的驗收站（乾淨假資料），跑完自動關掉
    python scripts/acceptance_check.py --running  驗收站已經開著（例如 launch.json 的 verify-5099）就直接跑

注意：
- 會寫入資料（開立獎狀、加入目標校系），所以只能對本機驗收站跑，**不要對公開展示站 5097 跑**。
- 驗收站和公開站用不同的資料庫檔（instance/demo-5099.db），互不影響。
- 有任何一項失敗，結束代碼是 1。
"""
import html
import io
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import docx
import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PORT = 5099
BASE = f"http://127.0.0.1:{PORT}"
PW = "demo1234"
ROOT = Path(__file__).resolve().parent.parent
results = []


def start_server():
    """開驗收站：和公開展示站同樣的設定（AI、Google 金鑰清空，雙重驗證關閉），埠號 5099。"""
    code = ("import sys, runpy; sys.path.insert(0, '.'); from app.config import Config; "
            "Config.ADMIN_TWO_FACTOR_REQUIRED = False; Config.TWO_FACTOR_REQUIRED = False; "
            "runpy.run_path('scripts/run_public_demo.py', run_name='__main__')")
    log = open(ROOT / "logs" / "acceptance-server.log", "w", encoding="utf-8")
    process = subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                               env={**os.environ, "DEMO_PORT": str(PORT)})
    for _ in range(120):
        if process.poll() is not None:
            sys.exit("驗收站開不起來，請看 logs/acceptance-server.log（5099 埠可能已被占用，改用 --running）")
        try:
            if requests.get(BASE + "/login", timeout=2).ok:
                return process
        except requests.RequestException:
            time.sleep(1)
    process.terminate()
    sys.exit("驗收站等了 2 分鐘還沒回應，請看 logs/acceptance-server.log")


server = None
if "--running" not in sys.argv:
    (ROOT / "logs").mkdir(exist_ok=True)
    server = start_server()


def rec(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("通過 " if ok else "失敗 ") + name + (" | " + detail if detail else ""), flush=True)


def csrf(text):
    m = re.search(r'name="csrf_token" value="([^"]+)"', text)
    return m.group(1) if m else ""


def login(path, user):
    s = requests.Session()
    r = s.get(BASE + path)
    r = s.post(BASE + path, data={"csrf_token": csrf(r.text), "username": user, "password": PW})
    return s, r


def title(t):
    m = re.search(r"<title>([^<]*)", t)
    return m.group(1) if m else ""


def text_of(t):
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)))


def docx_text(content):
    d = docx.Document(io.BytesIO(content))
    parts = [p.text for p in d.paragraphs]
    for table in d.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


# ---------- 學生 113534902（有目標校系 208003） ----------
s, r = login("/login", "113534902")
rec("學生登入 113534902", r.ok and "/login" not in r.url, r.url)

r = s.get(BASE + "/student/targets")
ids = sorted(set(re.findall(r"/student/targets/(\d+)\"", r.text)))
rec("學生有目標校系", bool(ids), f"ids={ids}")
pid = ids[0] if ids else None

# 三段切換
for major in ("all", "home", "other"):
    rr = s.get(BASE + f"/student/targets?major={major}")
    rec(f"目標校系切換 major={major}", rr.ok and "Traceback" not in rr.text, f"{rr.status_code}")
tabs = re.findall(r'href="[^"]*major=(all|home|other)[^"]*"', r.text)
rec("目標校系頁有三段切換連結", {"all", "home", "other"} <= set(tabs) or 'name="major"' in r.text, f"found={sorted(set(tabs))}")
rr = s.get(BASE + "/student/targets?q=資訊管理&major=home")
rec("搜尋＋切換同時使用", rr.ok and "資訊管理" in text_of(rr.text), str(rr.status_code))

# 推薦排序頁
for major in ("all", "home", "other"):
    rr = s.get(BASE + f"/student/matching?major={major}")
    rec(f"推薦排序 major={major}", rr.ok and "Traceback" not in rr.text, f"{rr.status_code}")

# Word：排除前
if pid:
    before = s.get(BASE + f"/student/targets/{pid}/package.docx")
    ok = before.ok and before.content[:2] == b"PK"
    rec("備審 Word 下載（排除前）", ok, f"{before.status_code} {len(before.content)} bytes")
    before_text = docx_text(before.content) if ok else ""

    # 找一筆可以不放的資料
    page = s.get(BASE + f"/student/package-exclusions?program_id={pid}")
    rec("不放資料頁可開", page.ok, str(page.status_code))
    rows = re.findall(r"<tr>\s*<td data-label=\"資料\">(.*?)</td>(.*?)</tr>", page.text, flags=re.S)
    candidates, locked_n, locked_disabled = [], 0, 0
    for n, rest in rows:
        k = re.search(r'name="kind" value="([^"]+)"', rest)
        i = re.search(r'name="record_id" value="(\d+)"', rest)
        if not (k and i) or 'name="excluded" value="1"' not in rest:
            continue
        button = re.search(r'name="excluded" value="1">\s*(<button[^>]*>)', rest).group(1)
        if "不能排除" in rest or "disabled" in button:
            locked_n += 1
            locked_disabled += "disabled" in button
            continue
        candidates.append((text_of(n).strip(), k.group(1), i.group(1)))
    rec("必備資料的按鈕都是停用", locked_n == locked_disabled, f"必備 {locked_n} 筆，停用 {locked_disabled} 筆")
    rec("有可不放的資料", bool(candidates), f"{len(candidates)} 筆；共 {len(rows)} 筆；種類 {sorted(set(c[1] for c in candidates))}")
    picked = None
    for name, kind, rid in candidates:
        key = name.split(" ")[0][:12]
        if key and key in before_text:
            picked = (name, kind, rid, key)
            break
    rec("找到同時出現在 Word 的資料", picked is not None, str(picked))
    if picked:
        name, kind, rid, key = picked
        rr = s.post(BASE + "/student/package-exclusions", data={"csrf_token": csrf(page.text), "kind": kind, "record_id": rid, "excluded": "1", "program_id": pid})
        err = re.search(r'class="alert[^"]*"[^>]*>(.*?)</p>', rr.text, flags=re.S)
        rec("設定不放進備審", rr.ok and "不放進備審" in rr.text, f"{rr.status_code} {rr.url} {text_of(err.group(1)) if err else ''}")
        after = s.get(BASE + f"/student/targets/{pid}/package.docx")
        after_text = docx_text(after.content)
        rec("Word 排除後該筆資料消失", key not in after_text, f"key={key}")
        page2 = s.get(BASE + f"/student/package-exclusions?program_id={pid}")
        rr = s.post(BASE + "/student/package-exclusions", data={"csrf_token": csrf(page2.text), "kind": kind, "record_id": rid, "excluded": "0", "program_id": pid})
        back = s.get(BASE + f"/student/targets/{pid}/package.docx")
        rec("放回後 Word 又出現", key in docx_text(back.content), f"key={key}")

    # 自傳頁
    rr = s.get(BASE + f"/student/autobiography?program_id={pid}")
    t = text_of(rr.text)
    rec("自傳頁有引導（選了目標）", rr.ok and "先選一個目標校系" not in t, title(rr.text))
    rec("自傳頁資料可拖進文字框（B1）", "data-bio-pieces" in rr.text and 'draggable="true"' in rr.text
        and "js/bio-pieces.js" in rr.text, f"{rr.text.count('data-bio-piece=')} 個片段")
    print("  自傳頁摘要：", t[:600])

    gap = s.get(BASE + f"/student/targets/{pid}")
    rec("看還缺什麼頁", gap.ok and "Traceback" not in gap.text, title(gap.text))

# 學生其他頁
for p in ["/student/dashboard", "/student/learning-profile", "/student/learning-profile/upload", "/student/learning-profile/credentials",
          "/student/portfolio", "/student/portfolio/new", "/student/schedule", "/student/graduation-check", "/student/award-records",
          "/student/agent/issues", "/forms", "/notifications", "/help", "/account/two-factor"]:
    rr = s.get(BASE + p)
    rec(f"學生頁 {p}", rr.status_code == 200 and "Traceback" not in rr.text, title(rr.text))

# ---------- 學生 113534901：加入目標 ----------
s1, r = login("/login", "113534901")
page = s1.get(BASE + "/student/targets")
pids = re.findall(r'name="program_id" value="(\d+)"><button[^>]*>設為目標校系', page.text)
rec("113534901 可加入目標", bool(pids), f"{len(pids)} 個按鈕")
if pids:
    rr = s1.post(BASE + "/student/targets", data={"csrf_token": csrf(page.text), "program_id": pids[0]})
    rec("加入目標後導到缺什麼頁", rr.ok and f"/student/targets/{pids[0]}" in rr.url, rr.url)
    rr = s1.get(BASE + f"/student/autobiography?program_id={pids[0]}")
    rec("新目標的自傳頁可開", rr.ok and "先選一個目標校系" not in text_of(rr.text), title(rr.text))

# ---------- 科辦 ----------
st, r = login("/staff/login", "staff01")
rec("科辦登入", "/staff/dashboard" in r.url, r.url)
page = st.get(BASE + "/staff/certificates/batch")
rows_text = "113534901,資管科資訊週程式競賽,榮獲第一名,2026-10-20\n113534902,資管科資訊週,擔任工作人員,2026-10-21\n999999999,不存在的學生,測試,2026-10-22"
rr = st.post(BASE + "/staff/certificates/batch", data={"csrf_token": csrf(page.text), "rows": rows_text, "title": "活動證明", "action": "preview"})
t = text_of(rr.text)
rec("批量獎狀預覽", rr.ok and "確認建立 2 張" in t, re.search(r"確認建立[^）]*）?", t).group(0) if "確認建立" in t else t[:200])
rr2 = st.post(BASE + "/staff/certificates/batch", data={"csrf_token": csrf(rr.text), "rows": rows_text, "title": "活動證明", "action": "confirm"})
t2 = text_of(rr2.text)
ids_print = re.search(r"ids=([\d,]+)", rr2.text)
rec("批量獎狀建立", rr2.ok and ids_print is not None, (ids_print.group(1) if ids_print else t2[:300]))
if ids_print:
    pr = st.get(BASE + "/staff/certificates/print?ids=" + ids_print.group(1))
    pt = text_of(pr.text)
    rec("批量獎狀列印頁", pr.ok and "資管科資訊週程式競賽" in pt, f"{pr.status_code}")
    print("  獎狀內文摘要：", pt[:500])
# 學生看到自己的獎狀
rr = s1.get(BASE + "/notifications")
rec("學生收到獎狀通知", "獎狀" in text_of(rr.text), text_of(rr.text)[:200])

for p in ["/staff/dashboard", "/staff/certificates", "/staff/certificates/new", "/staff/forms", "/staff/forms/links"]:
    rr = st.get(BASE + p)
    rec(f"科辦頁 {p}", rr.status_code == 200 and "Traceback" not in rr.text, title(rr.text))

# ---------- 導師 ----------
te, r = login("/staff/login", "teacher01")
rec("導師登入", "/teacher/dashboard" in r.url, r.url)
rr = st.get(BASE + "/grade-overview")
rec("科辦看年級總覽", rr.status_code == 200 and "Traceback" not in rr.text, title(rr.text))
for p in ["/teacher/dashboard", "/teacher/reviews"]:
    rr = te.get(BASE + p)
    rec(f"導師頁 {p}", rr.status_code == 200 and "Traceback" not in rr.text, title(rr.text))
students = sorted(set(re.findall(r"/teacher/students/(\d+)", te.get(BASE + "/teacher/dashboard").text)))
for sid in students[:3]:
    rr = te.get(BASE + f"/teacher/students/{sid}")
    rec(f"導師看學生 {sid}", rr.status_code == 200 and "Traceback" not in rr.text, title(rr.text))

# ---------- 管理員 ----------
ad, r = login("/admin/login", "admin")
rec("管理員登入（不需雙重驗證）", "/admin/dashboard" in r.url, r.url)
for p in ["/admin/dashboard", "/admin/accounts", "/admin/programs", "/admin/ocr", "/admin/ai", "/admin/audit-logs", "/admin/classes",
          "/admin/curriculum", "/admin/course-rules", "/admin/match-filters", "/admin/project-types", "/admin/google-workspace",
          "/admin/storage", "/admin/agent"]:
    rr = ad.get(BASE + p)
    rec(f"管理員頁 {p}", rr.status_code == 200 and "Traceback" not in rr.text, title(rr.text))
rr = ad.get(BASE + "/admin/audit-logs")
rec("操作紀錄有批量獎狀", "batch" in rr.text or "批量" in text_of(rr.text), "")

fails = [r for r in results if not r[1]]
print(f"\n總計 {len(results)} 項，通過 {len(results) - len(fails)}，失敗 {len(fails)}")
for f in fails:
    print("失敗：", f[0], "|", f[2])
if server:
    server.terminate()
sys.exit(1 if fails else 0)

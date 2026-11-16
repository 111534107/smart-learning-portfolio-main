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
    # 腳本中途出錯也要把驗收站關掉，不然 5099 埠會被占住
    import atexit
    atexit.register(server.terminate)


def rec(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("通過 " if ok else "失敗 ") + name + (" | " + str(detail) if detail else ""), flush=True)


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
# 依地區找學校（B13–B16）：地圖、地區按鈕、學校卡片至少三個網站
rr = s.get(BASE + "/student/targets?region=中部")
rec("目標校系有台灣地圖與地區按鈕", rr.ok and rr.text.count('class="tw-county"') >= 19 and "中部（" in rr.text)
rr = s.get(BASE + "/student/targets?school=國立臺中科技大學&region=中部")
rec("學校卡片有官網、招生網站、科系介紹與 Google 地圖",
    all(x in rr.text for x in ("https://www.nutc.edu.tw/", "https://admission.nutc.edu.tw/", "https://im.nutc.edu.tw/", "在 Google 地圖開啟")))
rr = s.get(BASE + "/student/targets?q=資訊管理&major=home")
rec("搜尋＋切換同時使用", rr.ok and "資訊管理" in text_of(rr.text), str(rr.status_code))
# B22 篩選選單（2026-11-16）：選單選項來自校系資料；選「進修部」後沒隱藏的列都是進修部，且數字和列數一致
rr = s.get(BASE + "/student/targets?session=進修部&region=南部")
night_rows = re.findall(r'<li data-region="([^"]*)" data-school="[^"]+"([^>]*)>', rr.text)
night_shown = [(region, a) for region, a in night_rows if not a.endswith(" hidden")]
rec("目標校系篩選選單：日間或進修部＋地區",
    # 「加權資料」選單只在有校系缺加權資料時出現（示範資料每個都有），所以不列入必須出現的選單
    rr.ok and all(x in rr.text for x in ('name="channel"', 'name="session"', 'name="group"', 'name="school"'))
    and bool(night_shown) and all(region == "南部" and 'data-f-session="進修部"' in a for region, a in night_shown)
    and f"data-filter-shown>{len(night_shown)}<" in rr.text,
    f"顯示 {len(night_shown)} / {len(night_rows)} 列")

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

    gap = s.get(BASE + f"/student/targets/{pid}")
    rec("看還缺什麼頁", gap.ok and "Traceback" not in gap.text, title(gap.text))

# 學生其他頁
for p in ["/student/dashboard", "/student/learning-profile", "/student/learning-profile/upload", "/student/learning-profile/credentials",
          "/student/portfolio", "/student/portfolio/new", "/student/schedule", "/student/graduation-check", "/student/award-records",
          "/student/agent/issues", "/forms", "/notifications", "/help", "/account/two-factor"]:
    rr = s.get(BASE + p)
    rec(f"學生頁 {p}", rr.status_code == 200 and "Traceback" not in rr.text, title(rr.text))

# 畢業門檻工作台（2026-11-16）：總覽環與四條量表、四個可展開的門檻區塊、下一步、學期預警同一頁
grad = s.get(BASE + "/student/graduation-check").text
rec("畢業門檻工作台：總覽、四個門檻區塊、下一步與學期預警", "data-grad-dashboard" in grad and "data-gd-ring" in grad
    and grad.count('data-gd-block="') == 4 and "data-gd-steps" in grad and "data-semester-warning" in grad
    and 'id="gd-ask"' in grad, f"{grad.count('data-gd-block=')} 個區塊、{grad.count('gd-go')} 個下一步按鈕標記")

# 小助手待辦（B6）：規劃 → 同意 → 待辦頁；再規劃一次不會變兩份
def plan_and_approve(session):
    page = session.get(BASE + "/student/agent/issues").text
    r = session.post(BASE + "/student/agent/plan", data={"csrf_token": csrf(page)})
    plan = re.search(r"/student/agent/proposals/(\d+)", r.url)
    if not plan:
        return None
    return session.post(BASE + f"/student/agent/proposals/{plan.group(1)}/approve", data={"csrf_token": csrf(r.text)})


def todo_titles(page):
    return re.findall(r'aria-label="(?:標記完成|重新開啟)：([^"]+)"', page)


first = plan_and_approve(s)
rec("小助手規劃並同意後產生待辦", first is not None and bool(todo_titles(first.text)), todo_titles(first.text) if first else "")
second = plan_and_approve(s)
again = todo_titles(second.text) if second else []
rec("再規劃一次待辦不重複", bool(again) and len(again) == len(set(again)), again)

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

# ---------- 成績單上傳辨識（B7）：假成績單 → OCR → 比對正確答案 → 學生確認 → 寫入成績 ----------
def ocr_upload_check():
    import json
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    image = tmp / "fake_transcript.png"
    subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "make_fake_transcript.py"), str(image)], check=True)
    expected = json.loads(Path(str(image) + ".json").read_text(encoding="utf-8"))
    s3, _ = login("/login", "113534903")
    page = s3.get(BASE + "/student/learning-profile/upload").text
    r = s3.post(BASE + "/student/learning-profile/documents", data={"csrf_token": csrf(page), "document_type": "transcript"},
                files={"file": ("fake_transcript.png", image.read_bytes(), "image/png")}, allow_redirects=False)
    found = re.search(r"/documents/(\d+)/processing", r.headers.get("Location", ""))
    rec("成績單上傳後進入辨識中", found is not None, r.status_code)
    if not found:
        return
    doc = found.group(1)
    state = {}
    for _ in range(90):
        state = s3.get(BASE + f"/student/learning-profile/documents/{doc}/status").json()
        if state["state"] in ("done", "failed"):
            break
        time.sleep(2)
    rec("成績單辨識完成", state.get("state") == "done", state)
    review = s3.get(BASE + f"/student/learning-profile/documents/{doc}/review").text
    body = re.search(r'<form[^>]*action="[^"]*review/confirm[^"]*"[^>]*>(.*?)</form>', review, re.S)
    if not body:
        rec("確認頁有表單", False)
        return
    data = {}
    for tag in re.findall(r"<input[^>]*>", body.group(1)):
        name, value = re.search(r'name="([^"]+)"', tag), re.search(r'value="([^"]*)"', tag)
        if name and 'type="checkbox"' not in tag:
            data[name.group(1)] = html.unescape(value.group(1)) if value else ""
    for name, value in re.findall(r'<textarea[^>]*name="([^"]+)"[^>]*>(.*?)</textarea>', body.group(1), re.S):
        data[name] = html.unescape(value)
    # 確認頁上的欄位就是辨識結果：逐筆比對課名、年級、學期、學分、成績
    rows = {}
    for key in data:
        match = re.match(r"course_(\d+)_course_name$", key)
        if match:
            i = match.group(1)
            rows[(data[key], data.get(f"course_{i}_grade_level"), data.get(f"course_{i}_semester"))] = (
                data.get(f"course_{i}_credits"), data.get(f"course_{i}_score"))
    semester = {"上": "第一學期", "下": "第二學期"}
    right = sum(1 for e in expected
                if rows.get((e["name"], f"{e['grade']}年級", semester[e["semester"]])) == (str(e["credits"]), str(e["score"])))
    rec("OCR 課名、年級、學期、學分、成績全對", right == len(expected), f"{right}/{len(expected)}")
    r = s3.post(BASE + f"/student/learning-profile/documents/{doc}/review/confirm", data=data)
    rec("學生確認後成績出現在我的資料", r.ok and "物件導向程式設計" in s3.get(BASE + "/student/learning-profile").text, r.url)


ocr_upload_check()

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
# 2026-11-13：核准限主任、副主任。staff01 是科助，建立後是「待核准」；chief01（主任）勾選後一次核准
rec("科助批量建立後等主任核准", rr2.ok and "等主任或副主任核准" in t2, t2[:120])
chief, r = login("/staff/login", "chief01")
cert_page = chief.get(BASE + "/staff/certificates").text
pending_ids = re.findall(r'name="ids" value="(\d+)"[^>]*checked', cert_page)
rr3 = chief.post(BASE + "/staff/certificates/approve", data={"csrf_token": csrf(cert_page), "ids": pending_ids})
rec("主任一次核准科辦建立的獎狀", rr3.ok and f"已核准 {len(pending_ids)} 張" in text_of(rr3.text) and len(pending_ids) >= 2,
    f"{len(pending_ids)} 張")
rec("科助不能核准", st.post(BASE + "/staff/certificates/approve", data={"csrf_token": csrf(st.get(BASE + "/staff/certificates").text), "ids": pending_ids}).status_code == 403)
pr = st.get(BASE + "/staff/certificates/print?ids=" + ",".join(pending_ids))
rec("批量獎狀列印頁", pr.ok and "資管科資訊週程式競賽" in text_of(pr.text), f"{pr.status_code}")
act_chief = text_of(chief.get(BASE + "/staff/activity").text)
act_assistant = text_of(st.get(BASE + "/staff/activity").text)
rec("主任看得到科辦全部操作紀錄、科助只看自己的",
    "科辦操作紀錄" in act_chief and "林科助" in act_chief and "我的操作紀錄" in act_assistant and "陳主任" not in act_assistant)

# 表單代理：科助從學校網站抓 → 主任核准 → 學生看得到公假申請書（需要網路）
forms_page = st.get(BASE + "/staff/forms").text
sync = st.post(BASE + "/staff/forms/sync", data={"csrf_token": csrf(forms_page)}, timeout=300)
sync_text = text_of(sync.text)
found = re.search(r"新抓到 (\d+) 份", sync_text)
rec("表單代理從學校網站抓到表單", bool(found) and int(found.group(1)) >= 20, found.group(0) if found else sync_text[:120])
chief_forms = chief.get(BASE + "/staff/forms").text
approved = chief.post(BASE + "/staff/forms/approve-all", data={"csrf_token": csrf(chief_forms)})
rec("主任核准表單上架", "已核准上架" in text_of(approved.text))
rec("學生看得到學務處的公假申請書", "學生公假申請書" in s1.get(BASE + "/forms").text)
# 學生看到自己的獎狀
rr = s1.get(BASE + "/notifications")
rec("學生收到獎狀通知", "獎狀" in text_of(rr.text))

for p in ["/staff/dashboard", "/staff/certificates", "/staff/certificates/new", "/staff/forms", "/staff/forms/links",
          "/staff/activity"]:
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
for p in ["/admin/schools", "/admin/dashboard", "/admin/accounts", "/admin/programs", "/admin/ocr", "/admin/ai", "/admin/audit-logs", "/admin/classes",
          "/admin/curriculum", "/admin/course-rules", "/admin/match-filters", "/admin/project-types", "/admin/google-workspace",
          "/admin/storage", "/admin/agent"]:
    rr = ad.get(BASE + p)
    rec(f"管理員頁 {p}", rr.status_code == 200 and "Traceback" not in rr.text, title(rr.text))
rr = ad.get(BASE + "/admin/audit-logs")
rec("操作紀錄有批量獎狀", "batch" in rr.text or "批量" in text_of(rr.text), "")

# B30（2026-11-16）：沒有寄信帳號時，管理員核對後代為確認學生的備用信箱（信箱僅為測試資料）
bk, _ = login("/login", "113534902")
page = bk.get(BASE + "/account/password")
bk.post(BASE + "/account/backup-email", data={"csrf_token": csrf(page.text), "backup_email": "b30-check@example.test"})
page = ad.get(BASE + "/admin/accounts")
m = re.search(r'action="(/admin/accounts/\d+/backup-email/confirm)"[^>]*>(?:(?!</form>).)*?value="b30-check@example\.test"',
              page.text, flags=re.S)
rec("管理員看到等待確認的備用信箱", bool(m) and "等待確認的備用信箱" in text_of(page.text))
if m:
    ad.post(BASE + m.group(1), data={"csrf_token": csrf(page.text), "address": "b30-check@example.test"})
mine = text_of(bk.get(BASE + "/account/password").text)
rec("管理員代為確認後學生看到已確認", "b30-check@example.test 已確認" in mine, mine[mine.find("備用信箱"):][:120])

fails = [r for r in results if not r[1]]
print(f"\n總計 {len(results)} 項，通過 {len(results) - len(fails)}，失敗 {len(fails)}")
for f in fails:
    print("失敗：", f[0], "|", f[2])
if server:
    server.terminate()
sys.exit(1 if fails else 0)

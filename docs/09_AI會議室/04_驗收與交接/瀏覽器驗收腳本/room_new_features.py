"""GPT 新功能驗收：AI 最終確認、專案進度小助手、通知、本場搜尋、搜尋篩選、專案文件上傳。只用暫存區副本（8767）。"""
import base64
import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8767"
SHOTS = Path(sys.argv[1]); SHOTS.mkdir(parents=True, exist_ok=True)
ROOM = Path(sys.argv[2])            # 副本的會議室資料夾（project_documents 會在這裡）
results, dialogs, errors = [], [], []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("通過" if ok else "失敗"), name, detail)


def api(path, body=None):
    req = urllib.request.Request(BASE + path, method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "X-Meeting-Room": "1"})
    try:
        return json.loads(urllib.request.urlopen(req).read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"HTTP": exc.code, "error": exc.read().decode("utf-8")[:200]}


def more(pg, sel):
    if not pg.locator(sel).is_visible():
        pg.click("details.headMore > summary")
    pg.click(sel)


with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    ctx.add_init_script("localStorage.setItem('meetingRoomTourDone','1'); localStorage.setItem('meetingRoomMember','111534105')")
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("dialog", lambda d: (dialogs.append(f"{d.type}：{d.message[:60]}"), d.dismiss()))
    pg.goto(BASE); pg.wait_for_selector(".meeting")
    mid = "20261009-185407"
    pg.click(f".meeting[data-id='{mid}']"); pg.wait_for_selector("[data-confirm-ai]", state="attached"); pg.wait_for_timeout(1500)

    # 1. AI 最終確認
    btn = pg.locator("[data-confirm-ai]:visible").first   # 收合的發言裡的按鈕看不到，取看得到的
    agent, msg = btn.get_attribute("data-confirm-ai"), btn.get_attribute("data-confirm-message")
    before_version = api(f"/api/meetings/{mid}/history")["version"]
    btn.click(); pg.wait_for_timeout(800)
    meta = next(m for m in api("/api/meetings") if m["id"] == mid)
    check("按「確認」會記下哪位 AI 的哪則發言、哪位組員", (meta.get("final_confirmations") or {}).get(agent, {}).get("member") == "111534105",
          f"{agent} 第 {msg} 則")
    after = api(f"/api/meetings/{mid}/history")
    check("AI 確認不應該讓「編輯版本」變動（否則別人正在改名稱會被誤擋）", after["version"] == before_version,
          f"版本 {before_version} → {after['version']}")
    more(pg, "#historyMeeting"); pg.wait_for_selector("#historyDialog[open]")
    text = pg.text_content("#historyList")
    pg.screenshot(path=str(SHOTS / "新_編輯紀錄裡的確認.png"))
    check("編輯紀錄裡的 AI 確認要顯示得看得懂（不能出現 undefined）", "undefined" not in text, text[:120].replace("\n", " "))
    pg.click("#historyDialog button[value=close]")

    # 2. 專案進度小助手、通知
    pg.click("#progressAssistant"); pg.wait_for_timeout(1500)
    opened = pg.locator("#progressDialog[open]").count() == 1
    pg.screenshot(path=str(SHOTS / "新_專案進度小助手.png"))
    body = pg.text_content("#progressDialog") or ""
    check("專案進度小助手打得開", opened, body[:100].replace("\n", " "))
    pg.keyboard.press("Escape")
    pg.click("#noticeBell"); pg.wait_for_timeout(800)
    check("通知鈴鐺打得開", pg.locator("#noticeDialog[open]").count() == 1, (pg.text_content("#noticeList") or "")[:100].replace("\n", " "))
    pg.screenshot(path=str(SHOTS / "新_通知.png"))
    pg.keyboard.press("Escape")

    # 3. 本場搜尋
    pg.click("#conversationSearch"); pg.wait_for_timeout(300)
    if pg.locator("#conversationSearchInput").is_visible():
        pg.fill("#conversationSearchInput", "白話"); pg.keyboard.press("Enter"); pg.wait_for_timeout(600)
        check("本場搜尋找得到", "0" not in (pg.text_content("#conversationSearchCount") or "0")[:1], pg.text_content("#conversationSearchCount"))
    else:
        check("本場搜尋框打得開", False)

    # 4. 搜尋篩選（看會不會跳出舊式的輸入框）
    n = len(dialogs)
    pg.click("#meetingSearch"); pg.wait_for_timeout(400)
    if pg.locator("[data-search-filter='from']").count():
        pg.click("[data-search-filter='from']"); pg.wait_for_timeout(300)
    check("搜尋篩選不要用瀏覽器舊式輸入框（prompt）", len(dialogs) == n, "；".join(dialogs[n:]))
    pg.screenshot(path=str(SHOTS / "新_搜尋篩選.png"))
    browser.close()

# 5. 專案文件上傳（直接呼叫 API；檔案寫在暫存區副本）
def upload(name, content):
    return api("/api/project-documents", {"member": "111534105",
               "files": [{"name": name, "data": base64.b64encode(content.encode()).decode()}]})

upload("計畫.txt", "第一版內容")
upload("計畫.txt", "第二版內容")
docs = ROOM / "project_documents"
check("同名文件再上傳時，舊版要保留（不做刪除）", "第一版內容" in "".join(x.read_text(encoding="utf-8", errors="ignore") for x in docs.glob("*")),
      f"資料夾內：{[x.name for x in docs.glob('*')]}")
audit = ROOM / "project_documents_history.jsonl"
log_before = audit.read_text(encoding="utf-8")
upload("history.jsonl", "這不是紀錄")
log_after = audit.read_text(encoding="utf-8")
check("上傳名為 history.jsonl 的檔案不能蓋掉操作紀錄", log_before in log_after, log_after[:60])
check("不在名單上的學號不能上傳", "HTTP" in api("/api/project-documents", {"member": "999", "files": []}))

check("整個過程沒有網頁錯誤", not errors, "；".join(errors[:3]))
print(f"\n共 {len(results)} 項，失敗 {sum(1 for r in results if not r[1])} 項")

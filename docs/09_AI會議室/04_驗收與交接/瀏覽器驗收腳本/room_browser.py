"""ROOM-01 瀏覽器驗收：只測修改過的地方。測試伺服器 8767（隔離資料），不叫 AI。"""
import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8767"
SHOTS = Path(sys.argv[1])
SHOTS.mkdir(parents=True, exist_ok=True)
results, errors = [], []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("通過" if ok else "失敗"), name, detail)


def api(path):
    return json.loads(urllib.request.urlopen(BASE + path).read().decode("utf-8"))


def login(page, member="111534105"):
    page.goto(BASE)
    page.wait_for_selector("#memberLogin[open]", timeout=8000)
    page.fill("#memberIdInput", member)
    page.click("#memberLoginForm button")
    page.wait_for_selector(".meeting")


def click_more(pg, sel):
    if not pg.locator(sel).is_visible():
        pg.click("details.headMore > summary")
    pg.click(sel)


with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    ctx.add_init_script("try { localStorage.setItem('meetingRoomTourDone', '1'); } catch (e) {}")
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"網頁錯誤：{e}"))
    page.on("console", lambda m: m.type == "error" and errors.append(f"主控台：{m.text}"))
    page.on("dialog", lambda d: (errors.append(f"跳出瀏覽器對話框：{d.message[:80]}"), d.dismiss()))
    login(page)
    page.screenshot(path=str(SHOTS / "01_寬版.png"))

    # 右側兩區
    check("右側有「主持人」與「AI 與會者」兩個框", page.locator(".hostBox").count() == 1 and page.locator(".aiBox").count() == 1)
    overflow = page.evaluate("(() => { const a = document.querySelector('aside.right'); return a.scrollWidth - a.clientWidth; })()")
    check("右側沒有橫向溢出", overflow <= 1, f"多出 {overflow}px")
    wraps = page.evaluate("[...document.querySelectorAll('aside.right .member small')].filter(s => s.getClientRects().length > 1 || s.offsetHeight > 22).length")
    check("右側說明文字都只有一行", wraps == 0, f"{wraps} 個換行")

    # 資料夾：新增兩個
    for name, icon in (("小助手審查", "📝"), ("會議室開發", "📊")):
        page.click("#folderAdd")
        page.fill("#folderForm input[name=name]", name)
        page.click(f"#iconChoices [data-icon='{icon}']")
        page.click("#folderForm button[value=save]")
        page.wait_for_function(f"document.querySelector('#folderHead')?.textContent.includes('{name}')")
    folders = api("/api/folders")
    check("新增兩個資料夾（含圖示）", [f["name"] for f in folders] == ["小助手審查", "會議室開發"] and folders[0]["icon"] == "📝")
    check("資料夾記下建立者學號", all(f["created_by"] == "111534105" for f in folders))
    f1, f2 = folders[0]["id"], folders[1]["id"]

    # 拖曳會議到資料夾
    page.click("#folderBar [data-folder='']")
    page.wait_for_selector(".meeting")
    first = page.locator(".meeting").first
    first_id = first.get_attribute("data-id")
    first.drag_to(page.locator(f"#folderBar [data-folder='{f1}']"))
    page.wait_for_timeout(600)
    meta = next(m for m in api("/api/meetings") if m["id"] == first_id)
    check("把會議拖到資料夾就搬進去", meta.get("folder") == f1)

    # 用「移到資料夾」對話框搬另一場
    second_id = page.locator(".meeting").nth(1).get_attribute("data-id")
    page.click(f".meeting[data-id='{second_id}']")
    page.wait_for_timeout(500)
    page.click("#plusBtn")
    page.click("#moveMeeting")
    page.wait_for_selector("#moveDialog[open]")
    page.screenshot(path=str(SHOTS / "02_移到資料夾.png"))
    page.click(f"#moveChoices [data-move='{f2}']")
    page.wait_for_timeout(600)
    meta = next(m for m in api("/api/meetings") if m["id"] == second_id)
    check("「移到資料夾」用點選的就能搬（不用打代號）", meta.get("folder") == f2)

    # 切換資料夾只看到裡面的會議
    page.click(f"#folderBar [data-folder='{f1}']")
    page.wait_for_timeout(400)
    ids = page.eval_on_selector_all(".meeting", "els => els.map(e => e.dataset.id)")
    check("點資料夾只顯示裡面的會議", ids == [first_id], str(ids))
    page.click("#folderBar [data-folder='__none__']")
    page.wait_for_timeout(400)
    ids = page.eval_on_selector_all(".meeting", "els => els.map(e => e.dataset.id)")
    check("「未分類」只顯示沒有資料夾的會議", first_id not in ids and second_id not in ids and len(ids) == 1, str(ids))

    # 改資料夾名稱與圖示
    page.click(f"#folderBar [data-folder='{f1}']")
    page.click("#folderEdit")
    page.fill("#folderForm input[name=name]", "小助手審查（改）")
    page.click("#iconChoices [data-icon='💡']")
    page.click("#folderForm button[value=save]")
    page.wait_for_timeout(500)
    folders = api("/api/folders")
    check("資料夾可以改名、換圖示", folders[0]["name"] == "小助手審查（改）" and folders[0]["icon"] == "💡")
    history = Path(sys.argv[2]) / "folders_history.jsonl"
    lines = [json.loads(x) for x in history.read_text(encoding="utf-8").splitlines() if x.strip()]
    check("資料夾的新增／搬移／改名都有紀錄", [x["action"] for x in lines] == ["create", "create", "move", "move", "rename"],
          str([x["action"] for x in lines]))
    page.screenshot(path=str(SHOTS / "03_資料夾.png"))

    # 沒有刪除功能
    deletes = page.evaluate("[...document.querySelectorAll('aside.left button, #folderDialog button, #moveDialog button, #historyDialog button, #meetingDialog button')].filter(b => /刪除|移除|delete/i.test((b.textContent + b.title).replace('不能刪除', ''))).length")
    check("資料夾、會議、編輯相關畫面沒有刪除按鈕", deletes == 0)

    # 重新整理後還在
    page.reload()
    page.wait_for_selector(f"#folderBar [data-folder='{f1}']")
    check("重新整理後資料夾還在", page.locator(f"#folderBar [data-folder='{f2}']").count() == 1)

    # 編輯會議：取消不會存
    page.click(f".meeting[data-id='{first_id}']")
    page.wait_for_timeout(500)
    old_title = next(m for m in api("/api/meetings") if m["id"] == first_id)["title"]
    click_more(page, "#editMeeting")
    page.wait_for_selector("#meetingDialog[open]")
    page.fill("#meetingForm input[name=title]", "不應該被存起來")
    page.click("#meetingForm button[value=cancel]")
    page.wait_for_timeout(500)
    check("編輯視窗按「取消」不會存檔", next(m for m in api("/api/meetings") if m["id"] == first_id)["title"] == old_title)

    # 編輯會議：存檔＋編輯紀錄
    click_more(page, "#editMeeting")
    page.wait_for_selector("#meetingDialog[open]")
    page.wait_for_timeout(300)
    page.fill("#meetingForm input[name=title]", old_title + "（驗收改名）")
    page.fill("#meetingForm textarea[name=goal]", "驗收用的新目標")
    page.click("#meetingForm button[value=save]")
    page.wait_for_timeout(800)
    meta = next(m for m in api("/api/meetings") if m["id"] == first_id)
    check("改會議名稱與目標", meta["title"].endswith("（驗收改名）") and meta["goal"] == "驗收用的新目標")
    system = [m["text"] for m in api(f"/api/meetings/{first_id}/events?after=0")["messages"] if m["speaker"] == "system"][-2:]
    check("會議裡留下中文的系統訊息", all("田心于" in t for t in system) and any("會議名稱" in t for t in system), " / ".join(system))
    click_more(page, "#historyMeeting")
    page.wait_for_selector("#historyDialog[open]")
    items = page.locator(".histItem").count()
    who = page.locator(".histItem .histWho").first.text_content()
    page.screenshot(path=str(SHOTS / "04_編輯紀錄.png"))
    check("編輯紀錄顯示兩筆、寫出組員姓名與學號", items == 2 and "田心于" in who and "111534105" in who, who)
    check("編輯紀錄有改前改後並排", page.locator(".histCols .before").count() == 2 and page.locator(".histCols .after").count() == 2)
    page.click("#historyDialog button[value=close]")

    # 兩個人同時改：後存的被擋下，打的字還在
    page2 = ctx.new_page()
    page2.on("dialog", lambda d: d.dismiss())
    page2.goto(BASE)
    page2.wait_for_selector(".meeting")
    page2.click(f".meeting[data-id='{first_id}']")
    page2.wait_for_timeout(500)
    click_more(page2, "#editMeeting")
    page2.wait_for_selector("#meetingDialog[open]")
    page2.wait_for_timeout(300)
    click_more(page, "#editMeeting")
    page.wait_for_selector("#meetingDialog[open]")
    page.wait_for_timeout(300)
    page.fill("#meetingForm textarea[name=topic]", "第一個人先改的議題")
    page.click("#meetingForm button[value=save]")
    page.wait_for_timeout(600)
    page2.fill("#meetingForm textarea[name=topic]", "第二個人打的字")
    page2.click("#meetingForm button[value=save]")
    page2.wait_for_timeout(600)
    still_open = page2.locator("#meetingDialog[open]").count() == 1
    kept = page2.input_value("#meetingForm textarea[name=topic]")
    err = page2.text_content("#meetingError")
    page2.screenshot(path=str(SHOTS / "05_同時修改被擋.png"))
    check("同時修改：後存的被擋下、視窗不關、打的字還在", still_open and kept == "第二個人打的字" and "有人改過" in err, err)
    check("被擋下時資料沒有被覆蓋", next(m for m in api("/api/meetings") if m["id"] == first_id)["topic"] == "第一個人先改的議題")
    page2.close()

    # 搜尋
    page.fill("#meetingSearch", "白話")
    page.wait_for_selector("#searchPanel .searchResult", timeout=5000)
    count = page.locator("#searchPanel .searchResult").count()
    page.screenshot(path=str(SHOTS / "06_搜尋.png"))
    check("搜尋「白話」有結果且關鍵字有標亮", count > 0 and page.locator("#searchPanel mark").count() > 0, f"{count} 筆")
    target = page.locator("#searchPanel .searchResult[data-search-message]:not([data-search-message=''])").first
    mid, mmsg = target.get_attribute("data-search-meeting"), target.get_attribute("data-search-message")
    target.click()
    page.wait_for_function(f"document.getElementById('m-{mmsg}') !== null", timeout=8000)
    page.wait_for_timeout(900)
    visible = page.evaluate(f"(() => {{ const r = document.getElementById('m-{mmsg}').getBoundingClientRect(); return r.top < innerHeight && r.bottom > 0; }})()")
    check("點搜尋結果跳到那則發言", visible, f"會議 {mid} 第 {mmsg} 則")
    page.fill("#meetingSearch", "from:GPT 確認")
    page.wait_for_timeout(700)
    speakers = page.eval_on_selector_all("#searchPanel .searchResult small", "els => els.map(e => e.textContent)")
    check("from:GPT 只找 GPT 的發言", speakers and all("GPT" in s for s in speakers), f"{len(speakers)} 筆")
    page.fill("#meetingSearch", "in:會議室開發 審查")
    page.wait_for_timeout(700)
    metas = set(page.eval_on_selector_all("#searchPanel .searchResult", "els => els.map(e => e.dataset.searchMeeting)"))
    check("in:資料夾 只找那個資料夾裡的會議", metas == {second_id}, str(metas))
    page.fill("#meetingSearch", "完全不會出現的字串zzqq")
    page.wait_for_timeout(700)
    check("搜不到時顯示「找不到」", "找不到" in (page.text_content("#searchPanel") or ""))
    page.keyboard.press("Escape")
    check("按 Esc 關閉搜尋結果", page.locator("#searchPanel").is_hidden())

    # 右欄縮窄（像使用者截圖約 320px 寬的視窗）
    page.set_viewport_size({"width": 900, "height": 900})
    page.wait_for_timeout(300)
    page.screenshot(path=str(SHOTS / "07_窄視窗.png"))
    overflow = page.evaluate("(() => { const a = document.querySelector('aside.right'); return a.scrollWidth - a.clientWidth; })()")
    check("窄視窗時右側沒有橫向溢出", overflow <= 1, f"多出 {overflow}px")
    page.set_viewport_size({"width": 1400, "height": 900})

    # 網頁導覽：每一步指到的東西都存在
    page.click("#tourBtn")
    total = int(page.text_content("#tourCount").split("/")[1])
    missing = []
    for i in range(total):
        sel = page.evaluate("TOUR[tourStep].sel")
        exists = page.evaluate("(s => { const el = document.querySelector(s); return !!el && el.getClientRects().length > 0; })", sel)
        if sel and not exists:
            missing.append(f"{i + 1}:{sel}")
        if i < 3:
            page.screenshot(path=str(SHOTS / f"08_導覽第{i + 1}步.png"))
        page.click("#tourNext")
        page.wait_for_timeout(150)
    check("導覽每一步指到的元素都存在", not missing, f"共 {total} 步；缺：{missing}")

    # 沒有學號不能改
    ctx2 = browser.new_context(viewport={"width": 1400, "height": 900})
    ctx2.add_init_script("try { localStorage.setItem('meetingRoomTourDone', '1'); } catch (e) {}")
    p3 = ctx2.new_page()
    p3.goto(BASE)
    p3.wait_for_selector("#memberLogin[open]")
    p3.keyboard.press("Escape")
    p3.wait_for_timeout(300)
    check("沒有學號時進場視窗關不掉", p3.locator("#memberLogin[open]").count() == 1)
    req = urllib.request.Request(BASE + f"/api/meetings/{first_id}/edit", method="POST",
                                 data=json.dumps({"member": "999999999", "version": 0, "changes": {"title": "x"}}).encode(),
                                 headers={"Content-Type": "application/json", "X-Meeting-Room": "1"})
    try:
        urllib.request.urlopen(req)
        blocked = False
    except urllib.error.HTTPError as exc:
        blocked = exc.code in (400, 403)
    check("不在名單上的學號改不了會議", blocked)
    ctx2.close()
    browser.close()

real = [e for e in errors if "跳出瀏覽器對話框" not in e]
check("整個過程沒有網頁錯誤", not real, "；".join(real[:5]))
check("沒有跳出舊式的瀏覽器對話框（prompt／alert）", not [e for e in errors if "跳出瀏覽器對話框" in e],
      "；".join(e for e in errors if "跳出瀏覽器對話框" in e))
print(f"\n共 {len(results)} 項，失敗 {sum(1 for r in results if not r[1])} 項")

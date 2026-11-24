"""畫面過關檢查（docs/05_交接與專案管理/過關標準_畫面與動線_2026-11-20.md 的 A、B、C 項）。

用法：python -X utf8 scripts/check_layout_widths.py http://127.0.0.1:5097 [輸出資料夾]
對已經在跑的展示站，以手機 375×812、平板 768×1024、電腦 1280×800 × 淺色、深色，逐頁截圖並自動檢查：
A1 沒有左右捲動；A2 只允許指定的固定元件；A3 手機與平板可點元件 ≥44px；A4 文字對比；
A5 被切掉的文字；B1/B2 手機模擬鍵盤（可視高度 406px）時輸入框與儲存鈕可見、底部元件收起。
結果寫成 report.json 與 report.md，截圖放在同一資料夾。只讀畫面，不改資料。
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

SIZES = {"phone": (375, 812), "tablet": (768, 1024), "desktop": (1280, 800)}
THEMES = ("light", "dark")
ALLOWED_FIXED = ("sv2-tabbar", "assistant__toggle", "bg-squares", "skip-link", "masthead", "egg-", "batch-assistant-bubble")
# 頁首 .masthead 允許黏在頂端（填寫頁會在打字與閱讀時收起，由 B1 檢查）；彩蛋提示會自動消失。
# (角色帳號, 頁面路徑, 名稱, 打字測試的輸入框選擇器)
PAGES = [
    ("113534903", "/student/dashboard", "學生首頁", None),
    ("113534903", "/student/learning-profile", "我的資料", None),
    ("113534903", "/student/graduation-check", "畢業門檻", None),
    ("113534903", "/student/targets", "目標校系", None),
    ("113534903", "/student/targets/{program}", "備審資料", None),
    ("113534903", "/student/autobiography?program_id={program}", "寫自傳", "textarea[name^=paragraph_]"),
    ("113534903", "/student/portfolio-view/{program}", "預覽 A4", None),
    ("113534903", "/student/autobiography/batch", "批次生成", None),
    ("113534903", "/student/internship-resume", "實習履歷", "textarea[name^=text_]"),
    ("teacher01", "/teacher/dashboard", "導師工作台", None),
    ("teacher01", "/teacher/graduation", "導師畢業門檻", None),
    ("teacher01", "/teacher/roster", "導師學生名單", None),
    ("teacher01", "/teacher/targets", "導師目標校系", None),
    ("teacher01", "/teacher/autobiography/review/113534903", "導師審閱", None),
    ("chief01", "/staff/students", "主任學生名單", None),
    ("chief01", "/staff/students/113534903", "主任學生學習與畢業", None),
    ("chief01", "/staff/students/113534903/admissions", "主任學生升學與備審", None),
]

CHECK_JS = r"""
(allowed) => {
  const out = {};
  const de = document.documentElement;
  out.scrollWidth = de.scrollWidth; out.innerWidth = innerWidth;
  const vis = (e) => { const s = getComputedStyle(e); const r = e.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && parseFloat(s.opacity) > 0 && r.width > 0 && r.height > 0; };
  // fixed：一律檢查；sticky：只檢查「橫條」（寬度超過視窗 60%），側欄、表格固定欄不算
  out.fixed = [...document.querySelectorAll('body *')].filter(e => {
    const p = getComputedStyle(e).position; if (!vis(e)) return false;
    if (p === 'fixed') return true;
    return p === 'sticky' && e.getBoundingClientRect().width > innerWidth * 0.6;
  }).map(e => (e.className && e.className.toString() || e.tagName).slice(0, 60))
    .filter(c => !allowed.some(a => c.includes(a)));
  // 段落中的文字連結（inline）依 WCAG 2.5.8 例外；被 label 包住的勾選框以 label 高度為準
  out.small = [...document.querySelectorAll('a[href], button, input:not([type=hidden]), select, summary, label[for]')]
    .filter(e => vis(e) && e.getBoundingClientRect().height < 44 && !e.closest('[aria-hidden=true], .skip-link, .visually-hidden'))
    .filter(e => !(e.tagName === 'A' && getComputedStyle(e).display === 'inline'))
    .filter(e => !(['checkbox', 'radio'].includes(e.type) && e.closest('label') && e.closest('label').getBoundingClientRect().height >= 44))
    .slice(0, 40).map(e => ((e.innerText || e.value || e.getAttribute('aria-label') || e.tagName) + '').trim().slice(0, 24) + ' ' + Math.round(e.getBoundingClientRect().height) + 'px');
  const rgb = (s) => { const m = s.match(/rgba?\(([^)]+)\)/); if (!m) return null; const v = m[1].split(',').map(Number); return {r: v[0], g: v[1], b: v[2], a: v.length > 3 ? v[3] : 1}; };
  const lum = (c) => { const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const bgOf = (e) => { for (let n = e; n; n = n.parentElement) { const c = rgb(getComputedStyle(n).backgroundColor); if (c && c.a > 0.5) return c; } return rgb(getComputedStyle(document.body).backgroundColor) || {r: 255, g: 255, b: 255, a: 1}; };
  const low = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  while (walker.nextNode()) {
    const t = walker.currentNode; const e = t.parentElement;
    if (!e || seen.has(e) || !t.textContent.trim() || !vis(e)) continue; seen.add(e);
    if (e.closest('[aria-hidden=true], script, style, noscript, .skip-link, .visually-hidden')) continue;
    const box = e.getBoundingClientRect(); if (box.bottom < 0 || box.top > innerHeight * 3) continue;
    const s = getComputedStyle(e); const fg = rgb(s.color); if (!fg) continue;
    const bg = bgOf(e); const l1 = lum(fg), l2 = lum(bg);
    const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    const size = parseFloat(s.fontSize); const bold = parseInt(s.fontWeight) >= 700;
    const need = (size >= 24 || (bold && size >= 18.66)) ? 3 : 4.5;
    if (ratio < need) low.push(t.textContent.trim().slice(0, 20) + ' ' + ratio.toFixed(2));
    if (low.length >= 30) break;
  }
  out.lowContrast = low;
  out.clipped = [...document.querySelectorAll('body *')].filter(e => {
    if (e.closest('.visually-hidden, .skip-link')) return false;
    if (!vis(e) || !e.childNodes.length || ![...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return false;
    const s = getComputedStyle(e); if (s.textOverflow === 'ellipsis' && e.title) return false;
    return (s.overflow === 'hidden' || s.overflowX === 'hidden') && e.scrollWidth > e.clientWidth + 2;
  }).slice(0, 20).map(e => e.innerText.trim().slice(0, 24));
  out.testStrings = ['測試回答', '很長的回答', 'Lorem'].filter(w => document.body.innerText.includes(w));
  return out;
}
"""

TYPING_JS = r"""
async (sel) => {
  const box = document.querySelector(sel);
  if (!box) return {skipped: true};
  box.scrollIntoView({block: 'center'});
  box.dispatchEvent(new FocusEvent('focusin', {bubbles: true}));
  box.focus();
  await new Promise(r => setTimeout(r, 450));
  const vis = (e) => { if (!e) return false; const s = getComputedStyle(e); const r = e.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && parseFloat(s.opacity) > 0 && r.height > 0; };
  const kb = 406;
  const r = box.getBoundingClientRect();
  const save = [...document.querySelectorAll('button, [type=submit]')].find(b => /儲存/.test(b.textContent) && vis(b));
  const sr = save ? save.getBoundingClientRect() : null;
  let cur = box;
  const ancestors = [];
  while (cur) {
    const s = getComputedStyle(cur);
    if (s.overflowY !== 'visible' && s.overflowY !== '') {
      ancestors.push({tag: cur.tagName, class: (cur.className||'').toString().slice(0, 30), ofY: s.overflowY, sh: cur.scrollHeight, ch: cur.clientHeight, st: Math.round(cur.scrollTop)});
    }
    cur = cur.parentElement;
  }
  return {
    boxVisible: r.top >= 0 && r.top < kb - 40,
    saveVisible: !!sr && sr.top >= 0 && sr.bottom <= kb,
    bottomStillShown: ['.sv2-tabbar', '.assistant__toggle', '.tour-invite'].filter(s => vis(document.querySelector(s))),
    debug: {
      box: {top: Math.round(r.top), bottom: Math.round(r.bottom), height: Math.round(r.height)},
      save: save ? {tag: save.tagName, text: (save.innerText || save.value || '').trim().slice(0, 15), top: Math.round(sr.top), bottom: Math.round(sr.bottom)} : null,
      scrollParent: ancestors,
      winScroll: {y: Math.round(window.scrollY), h: document.documentElement.scrollHeight}
    }
  };
}
"""


def main():
    base = sys.argv[1].rstrip("/")
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else f"logs/layout-check/{datetime.now():%Y%m%d-%H%M%S}")
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        for user in sorted({p[0] for p in PAGES}):
            for theme in THEMES:
                for size_name, (w, h) in SIZES.items():
                    context = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1,
                                                  is_mobile=size_name == "phone", has_touch=size_name != "desktop")
                    context.add_init_script(f"try{{localStorage.setItem('ui-theme','{theme}')}}catch(e){{}}")
                    page = context.new_page()
                    login_path = "/login" if user.isdigit() else "/staff/login"
                    page.goto(base + login_path)
                    page.evaluate("""async ([path, u]) => { const t = document.querySelector('input[name=csrf_token]').value;
                        await fetch(path, {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'},
                        body: new URLSearchParams({csrf_token: t, username: u, password: 'demo1234'})}); }""", [login_path, user])
                    program = None
                    if user.isdigit():
                        page.goto(base + "/student/autobiography")
                        program = page.evaluate("(document.querySelector('input[name=program_id]')||{}).value || new URLSearchParams(location.search).get('program_id')")
                        if program:
                            # 備審資料頁只對已加入的目標校系開放；測試站資料若沒有目標，先加入，否則會量到「找不到這一頁」
                            page.evaluate("""async (pid) => { const t = document.querySelector('input[name=csrf_token]').value;
                                await fetch('/student/targets', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'},
                                body: new URLSearchParams({csrf_token: t, program_id: pid})}); }""", program)
                    for page_user, path, name, typing in PAGES:
                        if page_user != user:
                            continue
                        url = base + path.format(program=program or "")
                        response = page.goto(url)
                        page.wait_for_timeout(600)
                        shot = out_dir / f"{name}-{size_name}-{theme}.png"
                        page.screenshot(path=str(shot), full_page=False)
                        data = page.evaluate(CHECK_JS, list(ALLOWED_FIXED))
                        if typing and size_name == "phone":
                            page.set_viewport_size({"width": w, "height": h})
                            data["typing"] = page.evaluate(TYPING_JS, typing)
                        failures = []
                        if response is None or response.status >= 400:
                            failures.append(f"A0 頁面打不開（{response.status if response else '無回應'}）")
                        if data["scrollWidth"] > data["innerWidth"]:
                            failures.append(f"A1 左右捲動 {data['scrollWidth']}>{data['innerWidth']}")
                        if data["fixed"]:
                            failures.append("A2 多餘固定元件：" + "、".join(data["fixed"][:5]))
                        if size_name != "desktop" and data["small"]:
                            failures.append(f"A3 小於 44px：{len(data['small'])} 個，例如 " + "、".join(data["small"][:4]))
                        if data["lowContrast"]:
                            failures.append(f"A4 對比不足：{len(data['lowContrast'])} 處，例如 " + "、".join(data["lowContrast"][:4]))
                        if data["clipped"]:
                            failures.append("A5 文字被切：" + "、".join(data["clipped"][:4]))
                        if data["testStrings"]:
                            failures.append("E2 測試字串：" + "、".join(data["testStrings"]))
                        typing_result = data.get("typing") or {}
                        if typing_result and not typing_result.get("skipped"):
                            if not typing_result["boxVisible"] or not typing_result["saveVisible"]:
                                failures.append(f"B2 鍵盤開著時輸入框或儲存鈕看不到 (boxVisible={typing_result.get('boxVisible')}, saveVisible={typing_result.get('saveVisible')}, debug={typing_result.get('debug')})")
                            if typing_result["bottomStillShown"]:
                                failures.append("B1 打字時沒收起：" + "、".join(typing_result["bottomStillShown"]))
                        results.append({"page": name, "size": size_name, "theme": theme, "status": response.status if response else None,
                                        "screenshot": shot.name, "failures": failures})
                    context.close()
        browser.close()
    (out_dir / "report.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# 畫面過關檢查", "", f"網址：{base}　時間：{datetime.now():%Y-%m-%d %H:%M}", "",
             "| 頁面 | 裝置 | 外觀 | 結果 |", "| --- | --- | --- | --- |"]
    for row in results:
        verdict = "通過" if not row["failures"] else "；".join(row["failures"])
        lines.append(f"| {row['page']} | {row['size']} | {row['theme']} | {verdict} |")
    passed = sum(1 for row in results if not row["failures"])
    lines += ["", f"通過 {passed}／{len(results)}"]
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"通過 {passed}／{len(results)}；報告：{out_dir / 'report.md'}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
